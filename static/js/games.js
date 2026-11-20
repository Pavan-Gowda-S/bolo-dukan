/* Bolo Dukaan games for guests waiting on their food: Dosa Flip, Chai Catch, Spice Match.
   BD.Games.open({ tableToken, session: () => ({ sid, token }) | null }) */
(function () {
  "use strict";
  const esc = s => BD.esc(s);
  const best = id => Number(BD.store.get("bd_best_" + id) || 0);
  const setBest = (id, v) => BD.store.set("bd_best_" + id, String(v));
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------ shared canvas helper
  function makeCanvas(stage) {
    const c = document.createElement("canvas");
    c.className = "gx-canvas";
    stage.appendChild(c);
    const ctx = c.getContext("2d");
    const fit = () => {
      const r = stage.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      c.width = Math.max(1, Math.round(r.width * dpr)); c.height = Math.max(1, Math.round(r.height * dpr));
      c.style.width = r.width + "px"; c.style.height = r.height + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return { w: r.width, h: r.height };
    };
    return { c, ctx, fit };
  }
  function loop(fn) {
    let alive = true, last = performance.now();
    const step = now => { if (!alive) return; const dt = Math.min(0.05, (now - last) / 1000); last = now; fn(dt, now / 1000); requestAnimationFrame(step); };
    requestAnimationFrame(step);
    return () => { alive = false; };
  }
  function floatText(list, x, y, text, color) { list.push({ x, y, text, color, t: 0 }); }
  function drawFloats(ctx, list, dt) {
    for (let i = list.length - 1; i >= 0; i--) {
      const f = list[i]; f.t += dt;
      if (f.t > 1) { list.splice(i, 1); continue; }
      ctx.globalAlpha = 1 - f.t; ctx.fillStyle = f.color; ctx.font = "800 20px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "center";
      ctx.fillText(f.text, f.x, f.y - f.t * 50); ctx.globalAlpha = 1;
    }
  }

  // ------------------------------------------------------------ 1. Dosa Flip
  const dosaFlip = {
    id: "dosa", name: "Dosa Flip", icon: "🥞", hue: 32,
    desc: "Tap a tawa when its dosa turns golden. Too early is raw, too late burns. 3 burns and you're out.",
    start(stage, api) {
      const { ctx, fit } = makeCanvas(stage);
      let size = fit();
      const ro = new ResizeObserver(() => { size = fit(); }); ro.observe(stage);
      const N = 3, tawas = Array.from({ length: N }, (_, i) => ({ i, p: -1, wait: 0.4 + i * 0.5, speed: 0.3, flip: 0, smoke: 0 }));
      let score = 0, strikes = 0, served = 0, over = false;
      const floats = [];
      const level = () => 1 + Math.floor(served / 5);
      const pos = t => {
        const { w, h } = size, cols = w > h * 1.1 ? N : 1;
        const r = Math.min(cols === N ? w / (N * 2.4) : w / 3.2, cols === N ? h / 3 : h / (N * 2.5));
        return cols === N ? { x: w * (t.i + 0.5) / N, y: h * 0.55, r } : { x: w / 2, y: h * (t.i + 0.5) / N + 10, r };
      };
      const pour = t => { t.p = 0; t.speed = (0.22 + level() * 0.035) * (0.8 + Math.random() * 0.45); t.flip = 0; };
      function hit(t) {
        if (over) return;
        if (t.p < 0) return;
        const { x, y } = pos(t), p = t.p;
        if (p < 0.55) { floatText(floats, x, y - 20, "Raw!", "#ffc2cd"); BD.buzz(25); t.p = -1; t.wait = 0.6; return; }
        let pts = p >= 0.68 && p <= 0.82 ? 25 : 10;
        if (p > 0.95) pts = 3;
        score += pts * level(); served++;
        floatText(floats, x, y - 20, pts === 25 ? "Perfect! +" + pts * level() : "+" + pts * level(), pts === 25 ? "#2ee6a6" : "#ffc145");
        BD.buzz(pts === 25 ? [10, 20, 10] : 10); BD.sound.chime("tap");
        t.flip = 1; t.p = -1; t.wait = 0.35 + Math.random() * 0.9;
        api.setScore(score);
      }
      const onDown = e => {
        const r = stage.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
        let bestT = null, bd = 1e9;
        tawas.forEach(t => { const q = pos(t), d = Math.hypot(mx - q.x, my - q.y); if (d < q.r * 1.5 && d < bd) { bd = d; bestT = t; } });
        if (bestT) hit(bestT);
      };
      stage.addEventListener("pointerdown", onDown);
      const onKey = e => { const k = "123".indexOf(e.key); if (k >= 0) hit(tawas[k]); };
      addEventListener("keydown", onKey);
      api.setScore(0); api.setLives(3);
      const stop = loop((dt, now) => {
        const { w, h } = size;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#e7dccb"; ctx.font = "700 13px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "center";
        ctx.fillText(`Level ${level()}  ·  tap or press 1 2 3`, w / 2, 22);
        tawas.forEach(t => {
          const { x, y, r } = pos(t);
          if (!over) {
            if (t.p < 0) { t.wait -= dt; if (t.wait <= 0) pour(t); }
            else {
              t.p += t.speed * dt;
              if (t.p > 1.12) { strikes++; t.smoke = 1; floatText(floats, x, y - 20, "Burnt!", "#ff6b6b"); BD.buzz(80); BD.sound.chime("waiter"); t.p = -1; t.wait = 0.9; api.setLives(3 - strikes); if (strikes >= 3) { over = true; setTimeout(() => api.end(score), 700); } }
            }
          }
          // tawa
          const g = ctx.createRadialGradient(x - r * .3, y - r * .3, r * .1, x, y, r * 1.15);
          g.addColorStop(0, "#3b3646"); g.addColorStop(1, "#0d0b12");
          ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.beginPath(); ctx.ellipse(x, y + r * 0.18, r * 1.15, r * 1.0, 0, 0, 7); ctx.fill();
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 1.1, 0, 7); ctx.fill();
          ctx.strokeStyle = "rgba(255,255,255,.1)"; ctx.lineWidth = 2; ctx.stroke();
          // heat glow
          ctx.fillStyle = `rgba(255,100,40,${0.07 + 0.05 * Math.sin(now * 3 + t.i)})`; ctx.beginPath(); ctx.arc(x, y, r * 1.05, 0, 7); ctx.fill();
          // progress ring with the golden window
          const a0 = -Math.PI / 2, full = Math.PI * 2;
          ctx.lineWidth = 6; ctx.lineCap = "round";
          ctx.strokeStyle = "rgba(255,255,255,.08)"; ctx.beginPath(); ctx.arc(x, y, r * 1.28, 0, full); ctx.stroke();
          ctx.strokeStyle = "rgba(46,230,166,.55)"; ctx.beginPath(); ctx.arc(x, y, r * 1.28, a0 + full * 0.55, a0 + full * 0.95); ctx.stroke();
          ctx.strokeStyle = "#2ee6a6"; ctx.beginPath(); ctx.arc(x, y, r * 1.28, a0 + full * 0.68, a0 + full * 0.82); ctx.stroke();
          if (t.p >= 0) {
            const p = Math.min(1.12, t.p);
            ctx.strokeStyle = p > 0.95 ? "#ff4d6d" : "#ffc145"; ctx.beginPath(); ctx.arc(x, y, r * 1.28, a0, a0 + full * Math.min(1, p)); ctx.stroke();
            // the dosa
            const col = p < 0.55 ? mix([245, 232, 200], [236, 196, 120], p / 0.55) : p < 0.85 ? mix([236, 196, 120], [214, 140, 48], (p - 0.55) / 0.3) : mix([214, 140, 48], [50, 30, 18], Math.min(1, (p - 0.85) / 0.27));
            const pourScale = Math.min(1, p * 8);
            ctx.save(); ctx.translate(x, y); ctx.scale(pourScale, pourScale);
            ctx.fillStyle = `rgb(${col})`; ctx.beginPath();
            for (let k = 0; k <= 24; k++) { const a = k / 24 * full, rr = r * (0.88 + 0.05 * Math.sin(a * 5 + t.i)); ctx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); }
            ctx.fill();
            ctx.fillStyle = `rgba(120,60,20,${0.15 + Math.max(0, p - 0.4) * 0.5})`;
            for (let k = 0; k < 14; k++) { const a = k * 2.4 + t.i, d = r * (0.2 + (k % 5) * 0.14); ctx.beginPath(); ctx.arc(Math.cos(a) * d, Math.sin(a) * d, r * 0.045, 0, 7); ctx.fill(); }
            ctx.restore();
            if (p > 0.9) { ctx.fillStyle = `rgba(200,200,200,${(p - 0.9) * 1.6})`; for (let k = 0; k < 3; k++) { ctx.beginPath(); ctx.arc(x + (k - 1) * r * .35, y - r * (0.8 + ((now * 0.8 + k * .3) % 1) * 0.9), r * .18, 0, 7); ctx.fill(); } }
          }
          if (t.flip > 0) { t.flip -= dt * 2.5; ctx.save(); ctx.translate(x, y - (1 - t.flip) * r * 1.4); ctx.scale(1, Math.cos((1 - t.flip) * Math.PI)); ctx.globalAlpha = Math.max(0, t.flip); ctx.fillStyle = "#d68c30"; ctx.beginPath(); ctx.arc(0, 0, r * 0.85, 0, 7); ctx.fill(); ctx.restore(); ctx.globalAlpha = 1; }
          if (t.smoke > 0) { t.smoke -= dt; ctx.fillStyle = `rgba(90,90,90,${t.smoke * .6})`; ctx.beginPath(); ctx.arc(x, y - (1 - t.smoke) * r * 1.6, r * (0.5 + (1 - t.smoke)), 0, 7); ctx.fill(); }
        });
        drawFloats(ctx, floats, dt);
      });
      return () => { stop(); ro.disconnect(); stage.removeEventListener("pointerdown", onDown); removeEventListener("keydown", onKey); };
    },
  };
  function mix(a, b, t) { t = Math.max(0, Math.min(1, t)); return a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(","); }

  // ------------------------------------------------------------ 2. Chai Catch
  const chaiCatch = {
    id: "chai", name: "Chai Catch", icon: "☕", hue: 200,
    desc: "Slide the plate to catch snacks. Dodge the chillies 🌶️. Miss a snack or catch a chilli and you lose a life.",
    start(stage, api) {
      const { ctx, fit } = makeCanvas(stage);
      let size = fit();
      const ro = new ResizeObserver(() => { size = fit(); }); ro.observe(stage);
      const GOOD = [["🥟", 10], ["☕", 10], ["🍮", 15], ["🥭", 10], ["🍩", 15], ["🫓", 10]];
      let plateX = size.w / 2, target = plateX, items = [], spawn = 0.6, t0 = 0, score = 0, lives = 3, combo = 0, over = false, shake = 0;
      const floats = [];
      const move = e => { const r = stage.getBoundingClientRect(); target = e.clientX - r.left; };
      stage.addEventListener("pointermove", move); stage.addEventListener("pointerdown", move);
      const keys = {};
      const kd = e => { keys[e.key] = true; }, ku = e => { keys[e.key] = false; };
      addEventListener("keydown", kd); addEventListener("keyup", ku);
      api.setScore(0); api.setLives(3);
      const loseLife = (x, y, why) => {
        lives--; combo = 0; shake = 0.35; api.setLives(lives); BD.buzz(70); BD.sound.chime("waiter");
        floatText(floats, x, y, why, "#ff6b6b");
        if (lives <= 0 && !over) { over = true; setTimeout(() => api.end(score), 600); }
      };
      const stop = loop((dt, now) => {
        const { w, h } = size;
        t0 += dt;
        const speedUp = 1 + t0 / 40;
        if (keys.ArrowLeft) target -= 520 * dt; if (keys.ArrowRight) target += 520 * dt;
        const plateW = Math.max(70, Math.min(120, w * 0.24));
        target = Math.max(plateW / 2, Math.min(w - plateW / 2, target));
        plateX += (target - plateX) * Math.min(1, dt * 18);
        if (!over) {
          spawn -= dt;
          if (spawn <= 0) {
            spawn = Math.max(0.32, 0.95 - t0 / 60) * (0.7 + Math.random() * 0.6);
            const r = Math.random();
            const kind = r < 0.22 + Math.min(0.12, t0 / 300) ? ["🌶️", -1] : r > 0.97 ? ["⭐", 50] : GOOD[(Math.random() * GOOD.length) | 0];
            items.push({ e: kind[0], v: kind[1], x: 24 + Math.random() * (w - 48), y: -30, vy: (110 + Math.random() * 70) * speedUp, rot: Math.random() * 6, vr: (Math.random() - .5) * 3 });
          }
        }
        ctx.clearRect(0, 0, w, h);
        ctx.save();
        if (shake > 0) { shake -= dt; ctx.translate((Math.random() - .5) * 10, 0); }
        const plateY = h - 46;
        for (let i = items.length - 1; i >= 0; i--) {
          const it = items[i];
          if (!over) { it.y += it.vy * dt; it.rot += it.vr * dt; }
          if (it.y > plateY - 20 && it.y < plateY + 12 && Math.abs(it.x - plateX) < plateW / 2 + 6) {
            items.splice(i, 1);
            if (it.v < 0) loseLife(it.x, plateY - 30, "Spicy! 🔥");
            else { combo++; const mult = Math.min(5, 1 + Math.floor(combo / 5)); score += it.v * mult; api.setScore(score); floatText(floats, it.x, plateY - 30, `+${it.v * mult}${mult > 1 ? " x" + mult : ""}`, it.v >= 50 ? "#ffc145" : "#2ee6a6"); BD.sound.chime("tap"); BD.buzz(8); }
            continue;
          }
          if (it.y > h + 30) { items.splice(i, 1); if (it.v > 0 && !over) loseLife(it.x, h - 70, "Dropped!"); continue; }
          ctx.save(); ctx.translate(it.x, it.y); ctx.rotate(it.rot * 0.3); ctx.font = "34px serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(it.e, 0, 0); ctx.restore();
        }
        // plate
        ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.beginPath(); ctx.ellipse(plateX, plateY + 16, plateW * .55, 9, 0, 0, 7); ctx.fill();
        const pg = ctx.createLinearGradient(0, plateY - 10, 0, plateY + 12); pg.addColorStop(0, "#ffffff"); pg.addColorStop(1, "#d9cfc2");
        ctx.fillStyle = pg; ctx.beginPath(); ctx.ellipse(plateX, plateY, plateW / 2, 13, 0, 0, 7); ctx.fill();
        ctx.strokeStyle = "#c9b79f"; ctx.lineWidth = 2; ctx.beginPath(); ctx.ellipse(plateX, plateY - 1, plateW * .36, 8, 0, 0, 7); ctx.stroke();
        if (combo >= 5) { ctx.fillStyle = "#ffc145"; ctx.font = "800 13px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "center"; ctx.fillText(`COMBO x${Math.min(5, 1 + Math.floor(combo / 5))}`, plateX, plateY + 32); }
        drawFloats(ctx, floats, dt);
        ctx.restore();
      });
      return () => { stop(); ro.disconnect(); stage.removeEventListener("pointermove", move); stage.removeEventListener("pointerdown", move); removeEventListener("keydown", kd); removeEventListener("keyup", ku); };
    },
  };

  // ------------------------------------------------------------ 3. Spice Match (memory)
  const spiceMatch = {
    id: "memory", name: "Spice Match", icon: "🌶️", hue: 340,
    desc: "Flip cards to find the 8 matching pairs. Fewer moves and less time = more points.",
    start(stage, api) {
      const POOL = ["🥞", "☕", "🍛", "🥟", "🍮", "🌶️", "🥭", "🍵", "🧄", "🍋", "🥥", "🫓"];
      const pick = POOL.slice().sort(() => Math.random() - 0.5).slice(0, 8);
      const deck = pick.concat(pick).sort(() => Math.random() - 0.5);
      stage.innerHTML = `<div class="mem-grid">${deck.map((e, i) => `<button class="mem-card" data-i="${i}" aria-label="Hidden card"><span class="mem-in"><span class="mem-back"></span><span class="mem-front">${e}</span></span></button>`).join("")}</div>`;
      let first = null, lock = false, moves = 0, found = 0, startT = 0, done = false;
      api.setScore(0, "moves"); api.setLives(null);
      const timer = setInterval(() => { if (startT && !done) api.setExtra(Math.floor((Date.now() - startT) / 1000) + "s"); }, 500);
      const onClick = e => {
        const b = e.target.closest(".mem-card"); if (!b || lock || b.classList.contains("up") || done) return;
        if (!startT) startT = Date.now();
        b.classList.add("up"); BD.buzz(6); BD.sound.chime("tap");
        if (!first) { first = b; return; }
        moves++; api.setScore(moves, "moves");
        const a = first; first = null;
        if (deck[a.dataset.i] === deck[b.dataset.i]) {
          a.classList.add("got"); b.classList.add("got"); found++; BD.buzz([10, 20, 10]);
          if (found === 8) {
            done = true;
            const secs = (Date.now() - startT) / 1000;
            const score = Math.max(50, Math.round(1000 - (moves - 8) * 22 - secs * 4));
            setTimeout(() => api.end(score), 650);
          }
        } else {
          lock = true;
          setTimeout(() => { a.classList.remove("up"); b.classList.remove("up"); lock = false; }, reduced ? 350 : 750);
        }
      };
      stage.addEventListener("click", onClick);
      return () => { clearInterval(timer); stage.removeEventListener("click", onClick); stage.innerHTML = ""; };
    },
  };

  const GAMES = [dosaFlip, chaiCatch, spiceMatch];

  // ------------------------------------------------------------ overlay UI
  let el = null, stopGame = null, opts = {};
  function build() {
    el = document.createElement("div");
    el.className = "gx"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-label", "Games");
    el.innerHTML = `<div class="gx-top">
        <button class="btn-ghost icon-btn gx-back" aria-label="Back">←</button>
        <div class="gx-title grow"><b>Play while you wait</b><span class="gx-sub"></span></div>
        <div class="gx-hud"><span class="gx-lives"></span><span class="gx-score mono"></span></div>
        <button class="btn-ghost icon-btn gx-close" aria-label="Close games">✕</button>
      </div>
      <div class="gx-body"></div>`;
    document.body.appendChild(el);
    el.querySelector(".gx-close").onclick = close;
    el.querySelector(".gx-back").onclick = () => (el.querySelector(".gx-pick") ? close() : picker());
    addEventListener("keydown", e => { if (e.key === "Escape" && el.classList.contains("show")) close(); });
  }
  function hud(score, lives, label, extra) {
    el.querySelector(".gx-score").textContent = score == null ? "" : (label ? `${score} ${label}` : `${score}`) + (extra ? ` · ${extra}` : "");
    el.querySelector(".gx-lives").textContent = lives == null ? "" : "❤️".repeat(Math.max(0, lives)) + "🖤".repeat(Math.max(0, 3 - lives));
  }
  function stopCurrent() { if (stopGame) { stopGame(); stopGame = null; } }
  function picker() {
    stopCurrent(); hud(null, null);
    el.querySelector(".gx-title b").textContent = "Play while you wait";
    el.querySelector(".gx-sub").textContent = "Your food is on its way 🍳";
    el.querySelector(".gx-body").innerHTML = `<div class="gx-pick">${GAMES.map((g, i) => `
      <button class="glass gx-card" data-g="${g.id}" data-tilt="8" style="--h:${g.hue};animation-delay:${i * 0.08}s">
        <span class="gx-ico">${g.icon}</span>
        <span class="gx-name">${g.name}</span>
        <span class="gx-desc">${esc(g.desc)}</span>
        <span class="gx-best">${best(g.id) ? `Your best: <b>${best(g.id)}</b>` : "Not played yet"}</span>
      </button>`).join("")}</div>`;
    el.querySelectorAll(".gx-card").forEach(b => b.onclick = () => play(GAMES.find(g => g.id === b.dataset.g)));
    BD.tilt(el);
  }
  function play(game) {
    stopCurrent();
    BD.sound.unlock();
    el.querySelector(".gx-title b").textContent = game.name;
    el.querySelector(".gx-sub").textContent = "";
    const body = el.querySelector(".gx-body");
    body.innerHTML = `<div class="gx-stage ${game.id === "memory" ? "dom" : ""}"></div>`;
    const stage = body.querySelector(".gx-stage");
    let lastScore = 0, lastLives = null, label = "", extra = "";
    const api = {
      setScore(s, l) { lastScore = s; label = l || ""; hud(lastScore, lastLives, label, extra); },
      setLives(n) { lastLives = n; hud(lastScore, lastLives, label, extra); },
      setExtra(x) { extra = x; hud(lastScore, lastLives, label, extra); },
      end(score) { gameOver(game, score); },
    };
    stopGame = game.start(stage, api);
  }
  async function gameOver(game, score) {
    stopCurrent();
    const prevBest = best(game.id), isBest = score > prevBest;
    if (isBest) setBest(game.id, score);
    const sess = opts.session && opts.session();
    const player = BD.store.get("bd_player") || "";
    const body = el.querySelector(".gx-body");
    body.innerHTML = `<div class="gx-over">
      <div class="gx-big">${game.icon}</div>
      <div class="eyebrow">${isBest ? "New personal best!" : "Game over"}</div>
      <div class="gx-final hot-text">${score}</div>
      <div class="muted small">Best: ${Math.max(score, prevBest)}</div>
      ${sess ? `<form class="row gx-post" style="gap:8px;margin-top:16px"><input class="input grow" maxlength="16" placeholder="Your name" value="${esc(player)}" aria-label="Your name"><button class="btn">Post score</button></form>` : `<p class="faint small" style="margin-top:12px">Start ordering at your table to post scores to the restaurant's board.</p>`}
      <div class="gx-board glass"><div class="row spread"><b>Today's top players</b><span class="faint small">this restaurant</span></div><div class="gx-rows"><p class="faint small">Loading…</p></div></div>
      <div class="row" style="margin-top:16px;justify-content:center"><button class="btn cool gx-again">Play again</button><button class="btn-ghost gx-menu">Other games</button></div>
    </div>`;
    if (isBest && score > 0) BD.confetti(90);
    body.querySelector(".gx-again").onclick = () => play(game);
    body.querySelector(".gx-menu").onclick = picker;
    const board = async () => {
      try {
        const r = await BD.api(`/api/t/${encodeURIComponent(opts.tableToken)}/leaderboard?game=${game.id}`);
        body.querySelector(".gx-rows").innerHTML = r.top.length ? r.top.map((p, i) => `<div class="gx-row"><span>${["🥇", "🥈", "🥉", "4", "5"][i]}</span><span class="grow">${esc(p.player)} <span class="faint small">· table ${p.table_number}</span></span><b class="mono">${p.score}</b></div>`).join("") : `<p class="faint small">No scores yet today. Be the first!</p>`;
      } catch (e) { body.querySelector(".gx-rows").innerHTML = `<p class="faint small">Board unavailable.</p>`; }
    };
    board();
    const form = body.querySelector(".gx-post");
    if (form) form.onsubmit = async e => {
      e.preventDefault();
      const name = form.querySelector("input").value.trim() || "Guest";
      BD.store.set("bd_player", name);
      const btn = form.querySelector("button"); BD.busy(btn, true);
      try {
        await BD.api(`/api/session/${sess.sid}/score`, { body: { game: game.id, score, player: name }, headers: { "X-Guest-Token": sess.token } });
        form.innerHTML = `<p class="small" style="color:var(--mint);font-weight:700;margin:0">Posted ✓</p>`; board();
      } catch (x) { BD.toast(x.message, "bad"); BD.busy(btn, false); }
    };
  }
  function close() { stopCurrent(); if (el) el.classList.remove("show"); document.documentElement.classList.remove("gx-open"); }

  BD.Games = {
    open(o) {
      opts = o || {};
      if (!el) build();
      picker();
      el.classList.add("show"); document.documentElement.classList.add("gx-open");
    },
    close,
  };
})();
