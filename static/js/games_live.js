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

  // ---- revolver sound design (Web Audio, no files): crack + boom + room echo, cocking, ratchet, dry click, heartbeat
  const SFX = {
    ctx() { ac = ac || new (window.AudioContext || window.webkitAudioContext)(); if (ac.state === "suspended") ac.resume(); return ac; },
    out() {
      const a = this.ctx();
      if (!this._bus) {
        const comp = a.createDynamicsCompressor();   // loud, but never clipping
        comp.threshold.value = -6; comp.knee.value = 4; comp.ratio.value = 12; comp.attack.value = 0.001; comp.release.value = 0.2;
        const master = a.createGain(); master.gain.value = 1.0;
        comp.connect(master).connect(a.destination);
        const rev = a.createConvolver(), len = a.sampleRate * 2.2, ir = a.createBuffer(2, len, a.sampleRate);
        for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3.2); }
        rev.buffer = ir; const wet = a.createGain(); wet.gain.value = 0.55; rev.connect(wet).connect(comp);
        this._bus = { dry: comp, rev };
      }
      return this._bus;
    },
    noise(dur) { const a = this.ctx(), b = a.createBuffer(1, Math.ceil(a.sampleRate * dur), a.sampleRate), d = b.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1; const s = a.createBufferSource(); s.buffer = b; return s; },
    env(node, t, peak, attack, decay) { node.gain.setValueAtTime(0.0001, t); node.gain.exponentialRampToValueAtTime(peak, t + attack); node.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay); },
    gunshot() {
      try {
        const a = this.ctx(), bus = this.out(), t = a.currentTime + 0.01;
        // 1. supersonic crack: very short bright noise
        const crack = this.noise(0.12), hp = a.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 1800;
        const cg = a.createGain(); this.env(cg, t, 2.4, 0.0008, 0.08); crack.connect(hp).connect(cg); cg.connect(bus.dry); cg.connect(bus.rev); crack.start(t);
        // 2. muzzle blast: broadband noise through a closing low-pass
        const blast = this.noise(0.9), lp = a.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.setValueAtTime(5200, t); lp.frequency.exponentialRampToValueAtTime(180, t + 0.6);
        const bg = a.createGain(); this.env(bg, t, 2.8, 0.002, 0.7); blast.connect(lp).connect(bg); bg.connect(bus.dry); bg.connect(bus.rev); blast.start(t);
        // 3. chest thump: falling sine
        const th = a.createOscillator(); th.type = "sine"; th.frequency.setValueAtTime(140, t); th.frequency.exponentialRampToValueAtTime(38, t + 0.35);
        const tg = a.createGain(); this.env(tg, t, 2.2, 0.002, 0.4); th.connect(tg).connect(bus.dry); th.start(t); th.stop(t + 0.5);
        // 4. distant echo off the walls
        const echo = this.noise(0.5), el = a.createBiquadFilter(); el.type = "lowpass"; el.frequency.value = 900;
        const eg = a.createGain(); this.env(eg, t + 0.22, 0.5, 0.01, 0.45); echo.connect(el).connect(eg).connect(bus.rev); echo.start(t + 0.22);
      } catch (e) {}
    },
    tick(freq = 3200, vol = 0.5, when = 0, dur = 0.025) {
      try {
        const a = this.ctx(), bus = this.out(), t = a.currentTime + when;
        const n = this.noise(dur + 0.02), bp = a.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = freq; bp.Q.value = 6;
        const g = a.createGain(); this.env(g, t, vol, 0.0005, dur); n.connect(bp).connect(g).connect(bus.dry); n.start(t);
      } catch (e) {}
    },
    cock() { this.tick(1600, 0.7, 0, 0.03); this.tick(2600, 0.9, 0.14, 0.03); this.tick(900, 0.5, 0.16, 0.05); },
    ratchet(steps, total) { for (let i = 0; i < steps; i++) this.tick(4200, 0.35, total * (1 - Math.pow(1 - i / steps, 1.8)), 0.015); },
    dry() { this.tick(2200, 1.1, 0, 0.02); this.tick(5200, 0.6, 0.004, 0.012); },
    heartbeat(when = 0) {
      try {
        const a = this.ctx(), bus = this.out();
        [0, 0.22].forEach((o, i) => { const t = a.currentTime + when + o, s = a.createOscillator(); s.type = "sine"; s.frequency.setValueAtTime(70, t); s.frequency.exponentialRampToValueAtTime(40, t + 0.15);
          const g = a.createGain(); this.env(g, t, i ? 0.6 : 0.9, 0.005, 0.18); s.connect(g).connect(bus.dry); s.start(t); s.stop(t + 0.25); });
      } catch (e) {}
    },
  };

  // ---- the revolver drawing (side view). Steel gradients, fluted cylinder, wooden checkered grip.
  const REVOLVER = `<svg class="rv" viewBox="0 0 440 210" aria-hidden="true">
    <defs>
      <linearGradient id="rvSteel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9edf3"/><stop offset=".25" stop-color="#9aa3b2"/><stop offset=".55" stop-color="#4b5363"/><stop offset=".8" stop-color="#2a2f39"/><stop offset="1" stop-color="#5e6676"/></linearGradient>
      <linearGradient id="rvDark" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7d8696"/><stop offset=".5" stop-color="#30353f"/><stop offset="1" stop-color="#14171d"/></linearGradient>
      <linearGradient id="rvWood" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b4a24"/><stop offset=".5" stop-color="#5e2e12"/><stop offset="1" stop-color="#3a1a08"/></linearGradient>
      <pattern id="rvCheck" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0 H7 M0 0 V7" stroke="rgba(0,0,0,.35)" stroke-width="1.2"/></pattern>
      <pattern id="rvFlute" width="60" height="16" patternUnits="userSpaceOnUse"><rect width="60" height="16" fill="url(#rvSteel)"/><rect y="5" width="60" height="6" rx="3" fill="#20242c" opacity=".75"/><rect y="5" width="60" height="1.5" fill="#cfd5de" opacity=".5"/></pattern>
      <clipPath id="rvCylClip"><rect x="150" y="62" width="74" height="56" rx="12"/></clipPath>
      <radialGradient id="rvFlash" cx=".2" cy=".5" r=".8"><stop offset="0" stop-color="#fff"/><stop offset=".25" stop-color="#fff3b0"/><stop offset=".55" stop-color="#ff9a1f"/><stop offset="1" stop-color="#ff3d00" stop-opacity="0"/></radialGradient>
    </defs>
    <!-- grip -->
    <path d="M118 104 C 112 140, 100 172, 92 196 L 140 200 C 150 172, 160 142, 166 112 Z" fill="url(#rvWood)" stroke="#2a1205" stroke-width="2"/>
    <path d="M118 104 C 112 140, 100 172, 92 196 L 140 200 C 150 172, 160 142, 166 112 Z" fill="url(#rvCheck)" opacity=".9"/>
    <circle cx="132" cy="150" r="5" fill="url(#rvSteel)" stroke="#222" stroke-width="1"/>
    <!-- frame -->
    <path d="M110 60 L 236 56 L 246 66 L 246 112 L 214 124 L 172 124 L 164 112 L 116 110 Z" fill="url(#rvSteel)" stroke="#1d2027" stroke-width="2"/>
    <!-- trigger guard + trigger -->
    <path d="M172 122 C 170 150, 214 152, 214 124" fill="none" stroke="url(#rvDark)" stroke-width="7" stroke-linecap="round"/>
    <path class="rv-trigger" d="M190 120 C 186 132, 190 140, 198 142" fill="none" stroke="#c9ced8" stroke-width="5" stroke-linecap="round"/>
    <!-- barrel with top rib and front sight -->
    <rect x="240" y="64" width="186" height="30" rx="5" fill="url(#rvSteel)" stroke="#1d2027" stroke-width="2"/>
    <rect x="240" y="58" width="186" height="9" rx="3" fill="url(#rvDark)"/>
    <rect x="240" y="94" width="150" height="16" rx="4" fill="url(#rvDark)"/>
    <path d="M412 58 L 418 46 L 424 58 Z" fill="#2a2f39"/>
    <circle cx="427" cy="79" r="5" fill="#0b0c10"/>
    <!-- cylinder: flutes scroll while it turns -->
    <g clip-path="url(#rvCylClip)"><rect class="rv-flutes" x="150" y="30" width="74" height="140" fill="url(#rvFlute)"/></g>
    <rect x="150" y="62" width="74" height="56" rx="12" fill="none" stroke="#14171d" stroke-width="2.5"/>
    <rect x="150" y="64" width="74" height="8" rx="4" fill="#fff" opacity=".18"/>
    <!-- hammer (pivots at its base) -->
    <g class="rv-hammer"><path d="M112 66 L 104 40 C 102 34, 110 30, 116 34 L 128 60 Z" fill="url(#rvDark)" stroke="#111" stroke-width="1.5"/><path d="M106 38 L 116 35" stroke="#888" stroke-width="2"/></g>
    <!-- muzzle flash + smoke (hidden until BANG) -->
    <g class="rv-flash"><ellipse cx="460" cy="79" rx="70" ry="34" fill="url(#rvFlash)"/>
      <path d="M430 79 L 470 62 L 462 76 L 500 70 L 466 82 L 498 92 L 460 86 L 470 100 Z" fill="#fff6c9"/></g>
  </svg>`;

  // =================================================================== 1. Bill Roulette
  const roulette = {
    id: "roulette", name: "Bill Roulette", icon: "🎯", hue: 350, live: true, scroll: true,
    desc: "A six-shooter with one chamber loaded with the bill. Everyone takes a turn: cock, spin, pull. Whoever gets the BANG pays for the whole table!",
    tag: "Decide who pays · 2-12 players",
    enabled: o => !!(o.features && o.features.roulette),
    start(stage, api, opts) {
      const s = sess(opts);
      if (!s) return needTable(stage, "🎯", "Bill Roulette decides who pays, so it opens once your table is ordering.");
      let names = JSON.parse(BD.store.get("bd_roulette_names") || "[]"), round = null, busy = false, cylA = 0, alive = true;
      stage.innerHTML = `<div class="rl"></div>`;
      const box = stage.querySelector(".rl");
      const save = () => BD.store.set("bd_roulette_names", JSON.stringify(names));
      function setup() {
        api.setScore(null);
        box.innerHTML = `<div class="lv-msg"><div class="rv-wrap rv-idle">${REVOLVER}</div><h3>Who's playing?</h3>
          <p class="muted small">Add everyone at the table. The server loads one chamber with the bill before anyone pulls, so nobody can rig it.</p>
          <div class="rl-names">${names.map((n, i) => `<span class="chip rl-chip">${esc(n)}<button data-rm="${i}" aria-label="Remove ${esc(n)}">✕</button></span>`).join("")}</div>
          <form class="row rl-add" style="gap:8px;width:100%"><input class="input grow" maxlength="16" placeholder="Name (e.g. Ravi)" aria-label="Player name"><button class="btn-ghost">Add</button></form>
          <button class="btn lg block" data-go ${names.length < 2 ? "disabled" : ""}>Load the revolver (${names.length} players)</button>
          <p class="faint small">🔊 Turn your volume up</p></div>`;
        box.querySelector(".rl-add").onsubmit = e => { e.preventDefault(); const v = e.target.querySelector("input").value.trim(); if (v && names.length < 12 && !names.some(n => n.toLowerCase() === v.toLowerCase())) { names.push(v); save(); setup(); box.querySelector(".rl-add input").focus(); } };
        box.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { names.splice(Number(b.dataset.rm), 1); save(); setup(); });
        box.querySelector("[data-go]").onclick = load;
      }
      async function load() {
        SFX.ctx();
        try { round = await BD.api(`/api/session/${s.sid}/roulette`, { body: { players: names }, headers: H(s) }); }
        catch (e) { BD.toast(e.message, "bad"); return; }
        cylA = 0; drawGame();
        // loading: open the gate, drop the round in, spin the cylinder, snap shut
        SFX.tick(1200, 0.6); SFX.tick(2400, 0.8, 0.35, 0.02); SFX.ratchet(18, 1.1); SFX.tick(1400, 0.9, 1.25, 0.04);
        spinCyl(2 * 360 + 360 / round.chambers * 3, 1.3);
      }
      function chambersHtml() {
        const n = round.chambers;
        return Array.from({ length: n }, (_, i) => {
          const used = round.pulls[i], a = i / n * 360;
          return `<i class="rl-ch ${used ? (used.bang ? "bang" : "safe") : ""}" style="--r:${a}deg"><b>${used ? (used.bang ? "💥" : "✓") : ""}</b></i>`;
        }).join("");
      }
      function drawGame(last) {
        const turn = round.done ? null : round.players[round.turn];
        box.innerHTML = `<div class="rv-stage"><div class="rv-wrap">${REVOLVER}</div>
            <div class="rl-front"><div class="rl-cyl" style="--a:${cylA}deg">${chambersHtml()}<span class="rl-hub"></span></div><div class="rl-pin"></div></div></div>
          <div class="rl-turn">${round.done ? `<div class="rl-loser">💸 <b>${esc(round.loser)}</b> pays the bill!</div>`
            : `<div class="eyebrow">Chamber ${round.pulls.length + 1} of ${round.chambers}</div><div class="rl-name">${esc(turn)}</div>`}</div>
          <div class="rl-row">${round.players.map(p => { const pl = round.pulls.find(x => x.player === p); return `<span class="chip ${pl ? (pl.bang ? "rl-bang" : "rl-safe") : ""} ${p === turn ? "rl-now" : ""}">${pl ? (pl.bang ? "💥 " : "✓ ") : ""}${esc(p)}</span>`; }).join("")}</div>
          ${round.done ? `<div class="row" style="gap:8px;justify-content:center;flex-wrap:wrap"><button class="btn" data-again>Play again</button>
              <a class="btn-ghost" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(`🎯 Bill Roulette: ${round.loser} pays the bill today! 😄`)}">Share on WhatsApp</a></div>
              <p class="faint small center" style="margin-top:8px">It's on your bill screen too.</p>`
            : `<button class="btn lg block rl-pull" data-pull ${busy ? "disabled" : ""}>Pass the phone to ${esc(turn)} · Pull the trigger</button>`}`;
        const b = box.querySelector("[data-pull]"); if (b) b.onclick = pull;
        const a = box.querySelector("[data-again]"); if (a) a.onclick = setup;
        if (last && last.bang) box.querySelector(".rv-wrap").classList.add("fired");
      }
      function spinCyl(deg, secs) {
        cylA += deg;
        const cyl = box.querySelector(".rl-cyl"), fl = box.querySelector(".rv-flutes");
        if (cyl) { cyl.style.transition = `transform ${secs}s cubic-bezier(.16,.84,.24,1)`; cyl.style.setProperty("--a", cylA + "deg"); }
        if (fl) { fl.classList.add("turning"); clearTimeout(spinCyl.t); spinCyl.t = setTimeout(() => fl.classList.remove("turning"), secs * 1000); }
      }
      const wait = ms => new Promise(r => setTimeout(r, ms));
      async function pull() {
        if (busy) return; busy = true; SFX.ctx();
        box.querySelector("[data-pull]").disabled = true;
        const req = BD.api(`/api/session/${s.sid}/roulette/${round.id}/pull`, { body: {}, headers: H(s) });
        const gun = box.querySelector(".rv-wrap");
        // 1. cock the hammer: the cylinder turns one chamber
        gun.classList.add("cocked"); SFX.cock(); spinCyl(360 / round.chambers, 0.35); BD.buzz(15);
        await wait(450);
        // 2. a slow spin for suspense, then the heartbeat
        SFX.ratchet(10, 1.2); spinCyl(360, 1.25);
        await wait(1300);
        gun.classList.add("aim"); SFX.heartbeat(0); SFX.heartbeat(0.75); BD.buzz([10, 220, 10]);
        let res; try { res = await req; } catch (e) { BD.toast(e.message, "bad"); busy = false; gun.classList.remove("cocked", "aim"); drawGame(); return; }
        await wait(1300);
        if (!alive) return;
        // 3. the trigger: the hammer falls
        gun.classList.add("fire"); gun.classList.remove("cocked");
        if (res.last.bang) {
          SFX.gunshot(); BD.buzz([300, 60, 200]);
          gun.classList.add("bang");
          stage.classList.add("rl-shake"); const fl = document.createElement("div"); fl.className = "rl-whiteout"; stage.appendChild(fl);
          for (let i = 0; i < 7; i++) { const p = document.createElement("i"); p.className = "rv-smoke"; p.style.setProperty("--dx", (40 + Math.random() * 80) + "px"); p.style.setProperty("--dy", (-30 - Math.random() * 70) + "px"); p.style.animationDelay = i * 60 + "ms"; gun.appendChild(p); }
          await wait(900);
          stage.classList.remove("rl-shake"); fl.remove();
          BD.confetti(140); BD.toast(`💸 ${res.last.player} pays the bill!`, "ok", 5000);
        } else {
          SFX.dry(); BD.buzz(20); gun.classList.add("safe-flash");
          await wait(650);
        }
        round = res; busy = false;
        drawGame(res.last);
      }
      setup();
      return () => { alive = false; stage.innerHTML = ""; };
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
