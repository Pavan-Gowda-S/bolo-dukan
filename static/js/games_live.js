/* Games that matter to the bill. Results are always drawn on the server; this file only shows them.
   1. Bill Roulette: the table finds out who pays.     2. Housie: live tambola for the whole restaurant.
   3. Lucky Spin: spend to unlock a spin, win a free item. Prizes are added to the bill at ₹0 when staff serve them. */
(function () {
  "use strict";
  const esc = s => BD.esc(s);
  const sess = opts => opts.session && opts.session();
  const H = s => ({ "X-Guest-Token": s.token });
  const needTable = (stage, icon, text) => { stage.innerHTML = `<div class="lv-msg"><div class="lv-big">${icon}</div><h3>Start ordering to play</h3><p class="muted">${text}</p></div>`; return () => {}; };

  // tiny Web Audio effects (no files)
  let ac = null;
  function tone(freq, dur, type = "sine", vol = 0.15, when = 0) {
    try {
      ac = ac || new (window.AudioContext || window.webkitAudioContext)();
      const t = ac.currentTime + when, o = ac.createOscillator(), g = ac.createGain();
      o.type = type; o.frequency.setValueAtTime(freq, t);
      g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(ac.destination); o.start(t); o.stop(t + dur + 0.05);
    } catch (e) {}
  }
  const click = () => tone(1800, 0.05, "square", 0.08);
  const boom = () => { tone(90, 0.6, "sawtooth", 0.3); tone(55, 0.9, "triangle", 0.3, 0.05); };

  // =================================================================== 1. Bill Roulette
  const roulette = {
    id: "roulette", name: "Bill Roulette", icon: "🎯", hue: 350, live: true, scroll: true,
    desc: "Everyone takes a turn at the lucky cylinder. One chamber is loaded with the bill. Whoever hits it pays for the whole table!",
    tag: "Decide who pays · 2-12 players",
    enabled: o => !!(o.features && o.features.roulette),
    start(stage, api, opts) {
      const s = sess(opts);
      if (!s) return needTable(stage, "🎯", "Bill Roulette decides who pays, so it opens once your table is ordering.");
      let names = JSON.parse(BD.store.get("bd_roulette_names") || "[]"), round = null, spinning = false, angle = 0;
      stage.innerHTML = `<div class="rl"></div>`;
      const box = stage.querySelector(".rl");
      function setup() {
        api.setScore(null);
        box.innerHTML = `<div class="lv-msg"><div class="lv-big rl-spin-ico">🎯</div><h3>Who's playing?</h3>
          <p class="muted small">Add everyone at the table. The server loads one chamber with the bill before anyone pulls. Nobody can rig it.</p>
          <div class="rl-names">${names.map((n, i) => `<span class="chip rl-chip">${esc(n)}<button data-rm="${i}" aria-label="Remove ${esc(n)}">✕</button></span>`).join("")}</div>
          <form class="row rl-add" style="gap:8px;width:100%"><input class="input grow" maxlength="16" placeholder="Name (e.g. Ravi)" aria-label="Player name"><button class="btn-ghost">Add</button></form>
          <button class="btn lg block" data-go ${names.length < 2 ? "disabled" : ""}>🎯 Load the cylinder (${names.length})</button></div>`;
        box.querySelector(".rl-add").onsubmit = e => { e.preventDefault(); const v = e.target.querySelector("input").value.trim(); if (v && names.length < 12 && !names.some(n => n.toLowerCase() === v.toLowerCase())) { names.push(v); save(); setup(); box.querySelector(".rl-add input").focus(); } };
        box.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { names.splice(Number(b.dataset.rm), 1); save(); setup(); });
        box.querySelector("[data-go]").onclick = load;
      }
      const save = () => BD.store.set("bd_roulette_names", JSON.stringify(names));
      async function load() {
        try { round = await BD.api(`/api/session/${s.sid}/roulette`, { body: { players: names }, headers: H(s) }); }
        catch (e) { BD.toast(e.message, "bad"); return; }
        for (let i = 0; i < 6; i++) tone(400 + i * 60, 0.08, "triangle", 0.08, i * 0.07);
        drawGame();
      }
      function cylinder() {
        const n = round.chambers;
        return `<div class="rl-stage"><div class="rl-cyl" style="--a:${angle}deg">${Array.from({ length: n }, (_, i) => {
          const a = i / n * 360, used = round.pulls[i];
          return `<i class="rl-ch ${used ? (used.bang ? "bang" : "safe") : ""}" style="--r:${a}deg"><b>${used ? (used.bang ? "💥" : "✓") : ""}</b></i>`;
        }).join("")}<span class="rl-hub"></span></div><div class="rl-pin"></div></div>`;
      }
      function drawGame(last) {
        const turn = round.done ? null : round.players[round.turn];
        box.innerHTML = `${cylinder()}
          <div class="rl-turn">${round.done ? `<div class="rl-loser">💸 <b>${esc(round.loser)}</b> pays the bill!</div>`
            : `<div class="eyebrow">Turn ${round.pulls.length + 1} of ${round.chambers}</div><div class="rl-name">${esc(turn)}</div>`}</div>
          <div class="rl-row">${round.players.map((p, i) => { const pl = round.pulls.find(x => x.player === p); return `<span class="chip ${pl ? (pl.bang ? "rl-bang" : "rl-safe") : ""} ${p === turn ? "rl-now" : ""}">${pl ? (pl.bang ? "💥 " : "✓ ") : ""}${esc(p)}</span>`; }).join("")}</div>
          ${round.done ? `<div class="row" style="gap:8px;justify-content:center;flex-wrap:wrap"><button class="btn" data-again>Play again</button>
              <a class="btn-ghost" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(`🎯 Bill Roulette: ${round.loser} pays the bill today! 😄`)}">Share on WhatsApp</a></div>
              <p class="faint small center" style="margin-top:8px">It's on your bill screen too.</p>`
            : `<button class="btn lg block rl-pull" data-pull ${spinning ? "disabled" : ""}>Pass the phone to ${esc(turn)} · Pull</button>`}`;
        const b = box.querySelector("[data-pull]"); if (b) b.onclick = pull;
        const a = box.querySelector("[data-again]"); if (a) a.onclick = setup;
        if (last && last.bang) { stage.classList.add("rl-shake"); setTimeout(() => stage.classList.remove("rl-shake"), 700); }
      }
      async function pull() {
        if (spinning) return;
        spinning = true; drawGame();
        const cyl = box.querySelector(".rl-cyl");
        angle += 720 + 360 / round.chambers;
        cyl.style.setProperty("--a", angle + "deg"); cyl.classList.add("spinning");
        for (let i = 0; i < 14; i++) setTimeout(click, i * (60 + i * 12));      // the cylinder clicking round
        const req = BD.api(`/api/session/${s.sid}/roulette/${round.id}/pull`, { body: {}, headers: H(s) });
        await new Promise(r => setTimeout(r, 2100));
        let res; try { res = await req; } catch (e) { BD.toast(e.message, "bad"); spinning = false; drawGame(); return; }
        round = res; spinning = false;
        if (res.last.bang) { boom(); BD.buzz([200, 80, 300]); BD.confetti(160); BD.toast(`💸 ${res.last.player} pays the bill!`, "ok", 5000); }
        else { tone(880, 0.12, "sine", 0.12); tone(1320, 0.18, "sine", 0.1, 0.1); BD.buzz(25); }
        drawGame(res.last);
      }
      setup();
      return () => { stage.innerHTML = ""; };
    },
  };

  // =================================================================== 2. Housie (whole restaurant)
  const housie = {
    id: "housie", name: "Housie", icon: "🎱", hue: 45, live: true, scroll: true,
    desc: "Live tambola with every table in the restaurant. Numbers are called every few seconds. First line wins a free juice, full house wins a free starter!",
    tag: "Whole restaurant · win free juice or a starter",
    enabled: o => !!(o.features && o.features.housie),
    start(stage, api, opts) {
      const s = sess(opts);
      if (!s) return needTable(stage, "🎱", "Housie is for tables that are ordering. Tap “Start ordering” first.");
      stage.innerHTML = `<div class="hs"></div>`;
      const box = stage.querySelector(".hs");
      let st = null, alive = true, timer = 0, lastNum = null, dabbed = new Set(JSON.parse(BD.store.get("bd_dab_" + s.sid) || "[]")), auto = BD.store.get("bd_autodab") !== "0";
      const saveDab = () => BD.store.set("bd_dab_" + s.sid, JSON.stringify([...dabbed]));
      const fmt = x => { const t = Math.ceil(x); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
      async function load() {
        if (!alive) return;
        try { show(await BD.api(`/api/session/${s.sid}/housie`, { headers: H(s) })); } catch (e) { box.innerHTML = `<div class="lv-msg"><p class="muted">${esc(e.message)}</p></div>`; }
      }
      async function join() {
        try { show(await BD.api(`/api/session/${s.sid}/housie/join`, { body: {}, headers: H(s) })); BD.buzz(15); } catch (e) { BD.toast(e.message, "bad"); }
      }
      async function claim(prize) {
        try { const r = await BD.api(`/api/session/${s.sid}/housie/claim`, { body: { prize }, headers: H(s) }); BD.confetti(180); boomWin(); BD.toast(`🎉 ${r.won}! Your free item is on its way.`, "ok", 6000); show(r); }
        catch (e) { BD.toast(e.message, "bad", 4000); }
      }
      function boomWin() { [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.25, "triangle", 0.12, i * 0.12)); }
      function show(x) {
        st = x;
        const called = new Set(x.called || []);
        if (auto && x.ticket) x.called.forEach(n => dabbed.add(n));
        const cur = (x.called || []).slice(-1)[0];
        if (cur && cur !== lastNum && lastNum !== null) { tone(660, 0.1, "sine", 0.1); BD.buzz(10); }
        const newBall = cur !== lastNum; lastNum = cur;
        if (!x.round || (x.ended && !x.ticket)) {
          box.innerHTML = `<div class="lv-msg"><div class="lv-big hs-float">🎱</div><h3>Housie with the whole restaurant</h3>
            <p class="muted">Every table gets a ticket. Numbers are called every 7 seconds. Mark them off and claim before anyone else!</p>
            <div class="hs-prizes"><span>🥤 First line → free juice</span><span>🍢 Full house → free starter</span></div>
            <button class="btn lg" data-join>Get my ticket</button></div>`;
          box.querySelector("[data-join]").onclick = join; return;
        }
        const g = x.ticket;
        const lineReady = g && g.some(r => r.every(n => !n || (called.has(n) && dabbed.has(n))));
        const fullReady = g && g.every(r => r.every(n => !n || (called.has(n) && dabbed.has(n))));
        const won = k => (x.claims || []).find(c => c.prize === k);
        const lobby = !x.called.length && !x.ended;
        box.innerHTML = `<div class="hs-top">
            <div class="hs-ball ${newBall ? "roll" : ""}"><span>${lobby ? "…" : cur || "–"}</span></div>
            <div class="grow"><div class="eyebrow">${x.ended ? "Game over" : lobby ? "Starts in" : `Number ${x.called.length} of 90`}</div>
              <div class="hs-big mono">${x.ended ? "🏁" : lobby ? fmt(x.starts_in) : `next in ${Math.ceil(x.next_in || 0)}s`}</div>
              <div class="hs-last">${(x.called || []).slice(-6, -1).reverse().map(n => `<i>${n}</i>`).join("")}</div>
              <div class="faint small">${x.tables} table${x.tables === 1 ? "" : "s"} playing</div></div></div>
          ${g ? `<div class="hs-ticket">${g.map(r => `<div class="hs-r">${r.map(n => n ? `<button class="hs-c ${dabbed.has(n) && called.has(n) ? "dab" : ""} ${called.has(n) ? "called" : ""}" data-n="${n}">${n}</button>` : `<span class="hs-c blank"></span>`).join("")}</div>`).join("")}</div>
            <label class="row small muted" style="gap:6px;justify-content:center;margin:6px 0"><input type="checkbox" data-auto ${auto ? "checked" : ""}> Auto-mark called numbers</label>
            <div class="hs-claims">
              <button class="btn ${won("line") ? "" : "mint"}" data-claim="line" ${won("line") || !lineReady || x.ended ? "disabled" : ""}>${won("line") ? `Line: Table ${won("line").table_number} ✓` : "🥤 Claim first line"}</button>
              <button class="btn ${won("full") ? "" : "violet"}" data-claim="full" ${won("full") || !fullReady || x.ended ? "disabled" : ""}>${won("full") ? `Full house: Table ${won("full").table_number} ✓` : "🍢 Claim full house"}</button></div>`
            : `<button class="btn lg block" data-join ${x.ended ? "disabled" : ""}>Get my ticket</button>`}
          ${x.ended ? `<button class="btn-ghost block" data-join style="margin-top:10px">New game</button>` : ""}`;
        box.querySelectorAll("[data-join]").forEach(b => b.onclick = join);
        box.querySelectorAll("[data-claim]").forEach(b => b.onclick = () => claim(b.dataset.claim));
        box.querySelectorAll("[data-n]").forEach(b => b.onclick = () => {
          const n = Number(b.dataset.n);
          if (!called.has(n)) { BD.toast(`${n} hasn't been called yet`, "info", 1500); return; }
          dabbed.has(n) ? dabbed.delete(n) : dabbed.add(n); saveDab(); tone(1100, 0.05, "square", 0.06); show(st);
        });
        const a = box.querySelector("[data-auto]"); if (a) a.onchange = () => { auto = a.checked; BD.store.set("bd_autodab", auto ? "1" : "0"); show(st); };
        saveDab();
        api.setScore(g ? [...dabbed].filter(n => called.has(n) && g.flat().includes(n)).length : 0, "/15");
      }
      load();
      timer = setInterval(load, 1500);
      return () => { alive = false; clearInterval(timer); stage.innerHTML = ""; };
    },
  };

  // =================================================================== 3. Lucky Spin
  const spin = {
    id: "spin", name: "Lucky Spin", icon: "🎡", hue: 280, live: true, scroll: true,
    desc: "Spend a little more, spin the wheel once: free chai, juice, dessert or a starter!",
    tag: "Unlocks when your table orders enough",
    enabled: o => !!(o.features && o.features.lucky_spin),
    start(stage, api, opts) {
      const s = sess(opts);
      if (!s) return needTable(stage, "🎡", "The Lucky Spin unlocks once your table has ordered.");
      stage.innerHTML = `<div class="sp"></div>`;
      const box = stage.querySelector(".sp");
      let st = null, rot = 0, busy = false;
      const COLORS = ["#ff9f1c", "#3b1d6e", "#2ee6a6", "#5a2a8c", "#ff3d9a", "#3b1d6e", "#ffc145", "#5a2a8c"];
      function wheel(segs) {
        const n = segs.length, step = 360 / n;
        const grad = segs.map((_, i) => `${COLORS[i % COLORS.length]} ${i * step}deg ${(i + 1) * step}deg`).join(", ");
        return `<div class="sp-stage"><div class="sp-pointer"></div><div class="sp-wheel" style="--rot:${rot}deg;background:conic-gradient(from -${step / 2}deg, ${grad})">
          ${segs.map((t, i) => `<span class="sp-lab" style="--a:${i * step}deg">${esc(t)}</span>`).join("")}
          ${Array.from({ length: 24 }, (_, i) => `<i class="sp-bulb" style="--a:${i * 15}deg;--d:${(i % 2) * 0.5}s"></i>`).join("")}
          <span class="sp-hub">🎡</span></div></div>`;
      }
      async function load() {
        try { st = await BD.api(`/api/session/${s.sid}/spin`, { headers: H(s) }); } catch (e) { box.innerHTML = `<div class="lv-msg"><p class="muted">${esc(e.message)}</p></div>`; return; }
        if (st.result) rot = 360 * 6 - st.result.segment * (360 / st.segments.length);
        draw();
      }
      function draw(result) {
        const pct = Math.min(100, st.bill_paise / Math.max(1, st.min_paise) * 100);
        box.innerHTML = wheel(st.segments) + (st.spun
          ? `<div class="sp-res">${(result || st.result) && st.result && !/try|close|luck|next/i.test(st.result.label) ? `🎉 <b>${esc(st.result.label)}!</b><br><span class="muted small">Your waiter has been told. It's added to your bill at ₹0.</span>` : `<b>${esc(st.result ? st.result.label : "")}</b><br><span class="muted small">Thanks for playing! One spin per visit.</span>`}</div>`
          : st.unlocked
            ? `<button class="btn lg block sp-go" data-spin>🎡 Spin the wheel</button><p class="faint small center">One spin per table visit</p>`
            : `<div class="sp-lock"><div class="row spread"><b>🔒 Order ${BD.rupees(st.more_paise)} more to unlock</b><span class="mono small">${BD.rupees(st.bill_paise)} / ${BD.rupees(st.min_paise)}</span></div>
               <div class="sp-meter"><i style="width:${pct}%"></i></div><p class="faint small" style="margin:6px 0 0">Only accepted orders count.</p></div>`);
        const b = box.querySelector("[data-spin]"); if (b) b.onclick = go;
      }
      async function go() {
        if (busy) return; busy = true;
        box.querySelector("[data-spin]").disabled = true;
        let r; try { r = await BD.api(`/api/session/${s.sid}/spin`, { body: {}, headers: H(s) }); } catch (e) { BD.toast(e.message, "bad"); busy = false; load(); return; }
        const n = r.segments.length;
        rot = rot - (rot % 360) + 360 * 6 + (360 - r.landed * (360 / n));      // 6 turns, then stop on the server's segment
        const w = box.querySelector(".sp-wheel"); w.style.setProperty("--rot", rot + "deg"); w.classList.add("go");
        for (let i = 0; i < 40; i++) setTimeout(click, 4800 * (1 - Math.pow(1 - i / 40, 2.2)));
        await new Promise(res => setTimeout(res, 5200));
        st = r; busy = false;
        if (r.prize) { BD.confetti(200); [523, 659, 784, 1047, 1319].forEach((f, i) => tone(f, 0.3, "triangle", 0.12, i * 0.1)); }
        else tone(300, 0.3, "sine", 0.1);
        draw(true);
      }
      load();
      return () => { stage.innerHTML = ""; };
    },
  };

  window.BD_LIVE_GAMES = [roulette, housie, spin];
})();
