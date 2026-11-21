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

  // ------------------------------------------------------------ 4. Rickshaw Rush (3-lane runner)
  const rickshawRush = {
    id: "runner", name: "Rickshaw Rush", icon: "🛺", hue: 50,
    desc: "Race your auto through the neon city. Swipe ← → to change lanes, ↑ to jump barricades, ↓ to duck banners. Chain ₹ coins for combos, grab 🧲 🛡 ⭐ power-ups!",
    start(stage, api) {
      const { ctx, fit } = makeCanvas(stage);
      let size = fit();
      const ro = new ResizeObserver(() => { size = fit(); }); ro.observe(stage);
      const LANES = [-1, 0, 1], PLAYER_Z = 0.045, BEST = best("runner");
      let lane = 0, laneX = 0, tilt = 0, jumpT = 0, land = 0, slideT = 0, speed = 0.42, dist = 0, coins = 0, score = 0, over = false, spawnIn = 0.8, shake = 0, t0 = 0, flash = 0;
      let combo = 0, comboT = 0, mult = 1, magnetT = 0, shieldT = 0, starT = 0, nextMile = 500, banner = null, passedBest = false, puIn = 9;
      const objs = [], floats = [], parts = [], trail = [];
      const stars = Array.from({ length: 60 }, () => ({ x: Math.random(), y: Math.random() * 0.6, r: Math.random() * 1.4 + 0.3, p: Math.random() * 6 }));
      const NEON = ["DOSA", "CHAI", "ಕಾಫಿ", "JUICE", "BIRYANI", "ತಿಂಡಿ", "SWEETS", "PAN"];
      const city = (n, seed) => Array.from({ length: n }, (_, i) => ({ w: 0.05 + ((i * seed) % 7) / 90, h: 0.28 + ((i * seed * 3) % 11) / 22, sign: (i * seed) % 3 === 0 ? NEON[(i * seed) % NEON.length] : null, hue: (i * seed * 47) % 360 }));
      const far = city(26, 7), near = city(16, 11);
      const proj = z => { const k = 7; return (1 / (1 + z * k) - 1 / (1 + k)) / (1 - 1 / (1 + k)); };
      const geom = () => { const { w, h } = size, horizon = h * 0.34, bottom = h * 0.98; return { w, h, horizon, bottom, cx: w / 2, halfNear: Math.min(w * 0.62, h * 0.55), halfFar: w * 0.05 }; };
      const toScreen = (z, laneOff) => {
        const g = geom(), p = proj(z), y = g.horizon + (g.bottom - g.horizon) * p, half = g.halfFar + (g.halfNear - g.halfFar) * p;
        return { x: g.cx + laneOff * half * 0.66, y, s: half / g.halfNear };
      };
      const sfx = (f, d = 0.08, type = "sine", v = 0.06) => { try { const a = sfx.ac = sfx.ac || new (window.AudioContext || window.webkitAudioContext)(); const o = a.createOscillator(), gn = a.createGain(); o.type = type; o.frequency.value = f; gn.gain.setValueAtTime(v, a.currentTime); gn.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + d); o.connect(gn).connect(a.destination); o.start(); o.stop(a.currentTime + d + 0.02); } catch (e) {} };
      const move = d => { if (over) return; const n = Math.max(-1, Math.min(1, lane + d)); if (n !== lane) { tilt = d * 0.22; lane = n; BD.buzz(6); sfx(420 + d * 60, 0.06, "triangle"); } };
      const jump = () => { if (!over && jumpT <= 0 && slideT <= 0) { jumpT = 0.62; sfx(520, 0.18, "square", 0.04); } };
      const slide = () => { if (!over && jumpT <= 0) { slideT = 0.62; sfx(180, 0.15, "sawtooth", 0.03); } };
      let sx = 0, sy = 0;
      const down = e => { sx = e.clientX; sy = e.clientY; };
      const up = e => {
        const dx = e.clientX - sx, dy = e.clientY - sy;
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 24) { const r = stage.getBoundingClientRect(), fx = (e.clientX - r.left) / r.width; return fx < 0.33 ? move(-1) : fx > 0.67 ? move(1) : jump(); }
        if (Math.abs(dx) > Math.abs(dy)) move(dx > 0 ? 1 : -1); else if (dy < 0) jump(); else slide();
      };
      stage.addEventListener("pointerdown", down); stage.addEventListener("pointerup", up);
      const key = e => {
        if (["ArrowLeft", "a"].includes(e.key)) move(-1); else if (["ArrowRight", "d"].includes(e.key)) move(1);
        else if (["ArrowUp", "w", " "].includes(e.key)) jump(); else if (["ArrowDown", "s"].includes(e.key)) slide(); else return;
        e.preventDefault();
      };
      addEventListener("keydown", key);
      api.setScore(0); api.setLives(null);
      function burst(x, y, color, n = 12, spd = 220) { for (let i = 0; i < n; i++) { const a = Math.random() * 6.28, v = spd * (0.4 + Math.random()); parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 80, t: 0, c: color, r: 2 + Math.random() * 3 }); } }
      function spawnRow() {
        const blocked = new Set(), n = Math.random() < Math.min(0.55, 0.3 + t0 / 200) ? 2 : 1;
        while (blocked.size < n) blocked.add(LANES[(Math.random() * 3) | 0]);
        blocked.forEach(l => { const r = Math.random(); objs.push({ type: r < 0.32 ? "barrier" : r < 0.55 ? "banner" : r < 0.8 ? "cow" : "bus", lane: l, z: 1 }); });
        LANES.filter(l => !blocked.has(l)).forEach(l => {
          if (Math.random() < 0.6) { const arc = Math.random() < 0.3; for (let k = 0; k < 5; k++) objs.push({ type: "coin", lane: l, z: 1 + k * 0.045, hy: arc ? Math.sin(k / 4 * Math.PI) * 70 : 0 }); }
        });
        puIn -= 1;
        if (puIn <= 0) { const free = LANES.filter(l => !blocked.has(l)); objs.push({ type: ["magnet", "shield", "star"][(Math.random() * 3) | 0], lane: free[(Math.random() * free.length) | 0], z: 1.12 }); puIn = 8 + ((Math.random() * 6) | 0); }
      }
      function crash() {
        if (over) return;
        if (shieldT > 0) { shieldT = 0; flash = 0.4; shake = 0.25; BD.buzz(40); sfx(220, 0.3, "triangle", 0.08); const p = toScreen(PLAYER_Z, laneX); burst(p.x, p.y - 50, "#4cc9f0", 30, 300); floatText(floats, p.x, p.y - 110, "Shield saved you!", "#4cc9f0"); return; }
        over = true; shake = 0.55; flash = 0.5; BD.buzz([60, 40, 90]); sfx(90, 0.6, "sawtooth", 0.12);
        const p = toScreen(PLAYER_Z, laneX); burst(p.x, p.y - 40, "#ffb84d", 40, 340);
        setTimeout(() => api.end(score), 1000);
      }
      const stop = loop((dt, now) => {
        const g = geom(), T = now / 1000;
        if (!over) {
          t0 += dt; speed = Math.min(1.35, 0.42 + t0 / 65); dist += speed * dt * 10;
          spawnIn -= dt; if (spawnIn <= 0) { spawnRow(); spawnIn = Math.max(0.5, 1.25 - t0 / 50) * (0.85 + Math.random() * 0.3); }
          jumpT = Math.max(0, jumpT - dt); slideT = Math.max(0, slideT - dt);
          magnetT = Math.max(0, magnetT - dt); starT = Math.max(0, starT - dt); shieldT = Math.max(0, shieldT - dt);
          comboT -= dt; if (comboT <= 0 && combo) { combo = 0; mult = 1; }
          score = Math.round(dist * 10) + coins * 25;
          api.setScore(score); api.setExtra(mult > 1 ? `x${mult} combo` : "");
          if (dist >= nextMile) { banner = { text: `${nextMile} m!`, sub: "Speeding up", t: 0 }; nextMile += 500; sfx(660, 0.15); sfx(990, 0.25, "sine", 0.05); }
          if (!passedBest && BEST > 0 && score > BEST) { passedBest = true; banner = { text: "NEW BEST!", sub: "keep going", t: 0 }; BD.confetti(60); }
        }
        laneX += (lane - laneX) * Math.min(1, dt * 14); tilt *= Math.pow(0.02, dt);
        if (jumpT === 0 && land > 0) land = Math.max(0, land - dt * 4);
        ctx.save();
        if (shake > 0) { shake -= dt; ctx.translate((Math.random() - .5) * 14, (Math.random() - .5) * 9); }
        // --- sky: sunset gradient, twinkling stars, glowing sun
        const sky = ctx.createLinearGradient(0, 0, 0, g.horizon);
        sky.addColorStop(0, "#120626"); sky.addColorStop(0.55, "#4a1460"); sky.addColorStop(1, "#ff7a3d");
        ctx.fillStyle = sky; ctx.fillRect(0, 0, g.w, g.horizon + 2);
        for (const s of stars) { ctx.globalAlpha = 0.35 + 0.65 * Math.abs(Math.sin(T * 1.3 + s.p)); ctx.fillStyle = "#fff"; ctx.fillRect(s.x * g.w, s.y * g.horizon, s.r, s.r); }
        ctx.globalAlpha = 1;
        const sunG = ctx.createRadialGradient(g.cx, g.horizon, 4, g.cx, g.horizon, g.horizon * 0.55);
        sunG.addColorStop(0, "rgba(255,220,120,1)"); sunG.addColorStop(0.35, "rgba(255,140,60,.8)"); sunG.addColorStop(1, "rgba(255,90,60,0)");
        ctx.fillStyle = sunG; ctx.fillRect(0, 0, g.w, g.horizon + 2);
        // --- parallax skyline: far silhouettes with lit windows, near buildings with neon signs
        const drawCity = (list, scroll, base, col, winA) => {
          let x = -((scroll % 1) * g.w);
          for (let rep = 0; rep < 2; rep++) for (const b of list) {
            const bw = b.w * g.w, bh = b.h * g.horizon * base;
            ctx.fillStyle = col; ctx.fillRect(x, g.horizon - bh, bw - 2, bh);
            ctx.fillStyle = `rgba(255,210,120,${winA})`;
            for (let wy = g.horizon - bh + 6; wy < g.horizon - 6; wy += 9) for (let wx = x + 4; wx < x + bw - 6; wx += 8) if (((wx * 13 + wy * 7) | 0) % 5 === 0) ctx.fillRect(wx, wy, 3, 4);
            if (b.sign && winA > 0.5) { const sw = Math.min(bw - 6, 60); ctx.save(); ctx.shadowColor = `hsl(${b.hue},100%,60%)`; ctx.shadowBlur = 12; ctx.fillStyle = `hsl(${b.hue},100%,70%)`; ctx.font = "800 10px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "center"; ctx.fillText(b.sign, x + bw / 2, g.horizon - bh + 14); ctx.restore(); ctx.strokeStyle = `hsla(${b.hue},100%,65%,.7)`; ctx.strokeRect(x + bw / 2 - sw / 2, g.horizon - bh + 3, sw, 15); }
            x += bw;
          }
        };
        drawCity(far, dist * 0.0012, 0.75, "#2a1048", 0.35);
        drawCity(near, dist * 0.003, 1.05, "#1a0a2e", 0.8);
        // --- ground, sidewalks, glowing road
        ctx.fillStyle = "#1c1428"; ctx.fillRect(0, g.horizon, g.w, g.h - g.horizon);
        const pave = (sgn) => { ctx.fillStyle = "#2c2238"; ctx.beginPath(); ctx.moveTo(g.cx + sgn * g.halfFar, g.horizon); ctx.lineTo(g.cx + sgn * g.halfFar * 1.6, g.horizon); ctx.lineTo(g.cx + sgn * g.halfNear * 1.45, g.bottom); ctx.lineTo(g.cx + sgn * g.halfNear, g.bottom); ctx.fill(); };
        pave(-1); pave(1);
        const road = ctx.createLinearGradient(0, g.horizon, 0, g.bottom); road.addColorStop(0, "#2a2438"); road.addColorStop(1, "#3c344c");
        ctx.fillStyle = road; ctx.beginPath();
        ctx.moveTo(g.cx - g.halfFar, g.horizon); ctx.lineTo(g.cx + g.halfFar, g.horizon); ctx.lineTo(g.cx + g.halfNear, g.bottom); ctx.lineTo(g.cx - g.halfNear, g.bottom); ctx.fill();
        // glowing road edges
        ctx.save(); ctx.shadowColor = "#ff3d9a"; ctx.shadowBlur = 14; ctx.strokeStyle = "#ff5fae"; ctx.lineWidth = 3;
        for (const sgn of [-1, 1]) { ctx.beginPath(); ctx.moveTo(g.cx + sgn * g.halfFar, g.horizon); ctx.lineTo(g.cx + sgn * g.halfNear, g.bottom); ctx.stroke(); }
        ctx.restore();
        const phase = (dist * 0.35) % 1;
        for (let k = 0; k < 16; k++) {
          const z1 = (k + 1 - phase) / 16, z2 = z1 - 0.028;
          if (z2 < 0) continue;
          for (const off of [-0.5, 0.5]) { const a = toScreen(z1, off), b = toScreen(z2, off); ctx.strokeStyle = "rgba(255,240,200,.75)"; ctx.lineWidth = Math.max(1, 5 * b.s); ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
          if (k % 2 === 0) for (const side of [-1.9, 1.9]) {   // street lamps with light cones
            const p = toScreen(z1, side), hgt = 90 * p.s;
            ctx.fillStyle = "#4a3d5e"; ctx.fillRect(p.x - 2 * p.s, p.y - hgt, 4 * p.s, hgt);
            const cone = ctx.createRadialGradient(p.x, p.y - hgt, 1, p.x, p.y - hgt, 60 * p.s); cone.addColorStop(0, "rgba(255,214,120,.55)"); cone.addColorStop(1, "rgba(255,214,120,0)");
            ctx.fillStyle = cone; ctx.beginPath(); ctx.arc(p.x, p.y - hgt, 60 * p.s, 0, 7); ctx.fill();
            ctx.fillStyle = "#fff3c4"; ctx.beginPath(); ctx.arc(p.x, p.y - hgt, 5 * p.s, 0, 7); ctx.fill();
          } else for (const side of [-2.4, 2.4]) { const p = toScreen(z1, side); ctx.font = `${Math.max(6, 70 * p.s)}px serif`; ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText("🌴", p.x, p.y); }
        }
        // speed streaks at high speed
        if (speed > 0.8 && !over) { ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 2; for (let i = 0; i < 10; i++) { const y = g.horizon + Math.random() * (g.h - g.horizon), x = Math.random() < 0.5 ? Math.random() * g.w * 0.18 : g.w - Math.random() * g.w * 0.18, l = 30 + Math.random() * 60 * speed; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + l); ctx.stroke(); } }
        // --- objects: move, collide, collect
        objs.sort((a, b) => b.z - a.z);
        for (let i = objs.length - 1; i >= 0; i--) {
          const o = objs[i];
          if (!over) o.z -= speed * dt * 0.55;
          if (o.type === "coin" && magnetT > 0 && o.z < 0.35 && o.z > 0) o.lane += (laneX - o.lane) * Math.min(1, dt * 10);
          if (o.z < -0.08) { objs.splice(i, 1); continue; }
          const inLane = o.type === "coin" ? Math.abs(o.lane - laneX) < 0.45 : o.lane === lane;
          if (!over && Math.abs(o.z - PLAYER_Z) < 0.022 && inLane) {
            const p = toScreen(PLAYER_Z, laneX);
            if (o.type === "coin") {
              if (o.hy > 30 && jumpT <= 0.1) continue;   // arc coins are up in the air: jump for them
              const val = (starT > 0 ? 2 : 1); coins += val; combo++; comboT = 1.2; mult = Math.min(5, 1 + Math.floor(combo / 8));
              objs.splice(i, 1); sfx(1200 + Math.min(combo, 20) * 40, 0.07, "triangle", 0.05); burst(p.x, p.y - 60, "#ffd36b", 8, 180);
              floatText(floats, p.x, p.y - 100, mult > 1 ? `+${25 * val} x${mult}` : `+${25 * val}`, "#ffc145");
              if (mult > 1) dist += 0.4 * mult;   // combos add bonus distance (score)
              continue;
            }
            if (["magnet", "shield", "star"].includes(o.type)) {
              objs.splice(i, 1); BD.buzz([20, 30, 20]); sfx(880, 0.12); sfx(1320, 0.2, "sine", 0.05);
              if (o.type === "magnet") magnetT = 7; if (o.type === "shield") shieldT = 12; if (o.type === "star") starT = 8;
              burst(p.x, p.y - 60, { magnet: "#ff5fae", shield: "#4cc9f0", star: "#ffd36b" }[o.type], 24, 260);
              banner = { text: { magnet: "🧲 MAGNET", shield: "🛡 SHIELD", star: "⭐ DOUBLE COINS" }[o.type], sub: { magnet: "coins come to you", shield: "survive one crash", star: "every coin counts twice" }[o.type], t: 0 };
              continue;
            }
            if (o.type === "barrier" && jumpT > 0.12) { if (!o.cleared) { o.cleared = true; floatText(floats, p.x, p.y - 140, "Nice jump!", "#2ee6a6"); dist += 2; } }
            else if (o.type === "banner" && slideT > 0) { if (!o.cleared) { o.cleared = true; floatText(floats, p.x, p.y - 140, "Ducked!", "#2ee6a6"); dist += 2; } }
            else if (!o.hit) { o.hit = true; crash(); }
          }
          if (!over && !o.near && o.type !== "coin" && !["magnet", "shield", "star"].includes(o.type) && Math.abs(o.z - PLAYER_Z) < 0.02 && Math.abs(o.lane - lane) === 1) {
            o.near = true; dist += 1.5; const p = toScreen(PLAYER_Z, laneX); floatText(floats, p.x + (o.lane - lane) * 60, p.y - 120, "Near miss +15", "#ff8fd0");
          }
        }
        for (const o of objs) {
          if (o.z > 1.05 || o.z < -0.05) continue;
          const p = toScreen(Math.max(0, o.z), o.lane), s = p.s;
          ctx.save(); ctx.textAlign = "center"; ctx.textBaseline = "bottom";
          if (o.type === "coin") {
            const bob = Math.sin(T * 6 + o.z * 30) * 4 * s, spinW = Math.abs(Math.cos(T * 5 + o.z * 20)), cy = p.y - (34 + (o.hy || 0)) * s + bob, r = 14 * s;
            const cg = ctx.createLinearGradient(p.x - r, cy - r, p.x + r, cy + r); cg.addColorStop(0, "#fff1a8"); cg.addColorStop(0.5, "#ffc145"); cg.addColorStop(1, "#b87700");
            ctx.shadowColor = "#ffcc33"; ctx.shadowBlur = 10 * s; ctx.fillStyle = cg; ctx.beginPath(); ctx.ellipse(p.x, cy, r * (0.25 + 0.75 * spinW), r, 0, 0, 7); ctx.fill();
            if (spinW > 0.5) { ctx.shadowBlur = 0; ctx.fillStyle = "#8a5600"; ctx.font = `800 ${Math.max(6, 15 * s)}px sans-serif`; ctx.textBaseline = "middle"; ctx.fillText("₹", p.x, cy + 1); }
          } else if (["magnet", "shield", "star"].includes(o.type)) {
            const cy = p.y - 50 * s + Math.sin(T * 4) * 6 * s, col = { magnet: "#ff5fae", shield: "#4cc9f0", star: "#ffd36b" }[o.type];
            const halo = ctx.createRadialGradient(p.x, cy, 2, p.x, cy, 40 * s); halo.addColorStop(0, col); halo.addColorStop(1, "rgba(0,0,0,0)");
            ctx.globalAlpha = 0.7 + 0.3 * Math.sin(T * 8); ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(p.x, cy, 40 * s, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
            ctx.font = `${Math.max(8, 40 * s)}px serif`; ctx.textBaseline = "middle"; ctx.fillText({ magnet: "🧲", shield: "🛡️", star: "⭐" }[o.type], p.x, cy);
          } else if (o.type === "banner") {
            const bg = ctx.createLinearGradient(0, p.y - 118 * s, 0, p.y - 88 * s); bg.addColorStop(0, "#ff5fae"); bg.addColorStop(1, "#c2185b");
            ctx.fillStyle = "#4a3d5e"; ctx.fillRect(p.x - 56 * s, p.y - 120 * s, 5 * s, 120 * s); ctx.fillRect(p.x + 51 * s, p.y - 120 * s, 5 * s, 120 * s);
            ctx.shadowColor = "#ff3d9a"; ctx.shadowBlur = 14 * s; ctx.fillStyle = bg; ctx.fillRect(p.x - 54 * s, p.y - 120 * s, 108 * s, 32 * s);
            ctx.shadowBlur = 0; ctx.fillStyle = "#fff"; ctx.font = `800 ${Math.max(6, 15 * s)}px sans-serif`; ctx.textBaseline = "middle"; ctx.fillText("SALE ↓ DUCK", p.x, p.y - 104 * s);
          } else {
            const em = { barrier: "🚧", cow: "🐄", bus: "🚌" }[o.type], fs = { barrier: 58, cow: 80, bus: 104 }[o.type];
            ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.beginPath(); ctx.ellipse(p.x, p.y, 38 * s, 8 * s, 0, 0, 7); ctx.fill();
            if (o.z < 0.3 && o.lane === lane && !over) { ctx.fillStyle = `rgba(255,60,90,${0.25 + 0.2 * Math.sin(T * 20)})`; ctx.beginPath(); ctx.ellipse(p.x, p.y - 2, 44 * s, 10 * s, 0, 0, 7); ctx.fill(); }
            ctx.font = `${Math.max(8, fs * s)}px serif`; ctx.fillText(em, p.x, p.y + 4 * s);
          }
          ctx.restore();
        }
        // --- the auto-rickshaw: tilt, jump arc, squash on landing, headlight, trail
        const pp = toScreen(PLAYER_Z, laneX), js = jumpT > 0 ? Math.sin((1 - jumpT / 0.62) * Math.PI) : 0;
        if (jumpT > 0 && jumpT < 0.05) land = 1;
        if (!over && Math.random() < 0.6) trail.push({ x: pp.x + (Math.random() - .5) * 30, y: pp.y - 6, t: 0 });
        for (let i = trail.length - 1; i >= 0; i--) { const d = trail[i]; d.t += dt * 1.8; d.y += 40 * dt; if (d.t > 1) { trail.splice(i, 1); continue; } ctx.fillStyle = starT > 0 ? `rgba(255,211,107,${0.5 * (1 - d.t)})` : `rgba(200,180,220,${0.35 * (1 - d.t)})`; ctx.beginPath(); ctx.arc(d.x, d.y, 4 + d.t * 10, 0, 7); ctx.fill(); }
        ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.beginPath(); ctx.ellipse(pp.x, pp.y - 2, 46 * (1 - js * 0.4), 11, 0, 0, 7); ctx.fill();
        const head = ctx.createRadialGradient(pp.x, pp.y - 30, 4, pp.x, pp.y - 120, 120); head.addColorStop(0, "rgba(255,245,200,.35)"); head.addColorStop(1, "rgba(255,245,200,0)");
        ctx.fillStyle = head; ctx.beginPath(); ctx.moveTo(pp.x - 18, pp.y - 30); ctx.lineTo(pp.x - 80, pp.y - 200); ctx.lineTo(pp.x + 80, pp.y - 200); ctx.lineTo(pp.x + 18, pp.y - 30); ctx.fill();
        ctx.save(); ctx.translate(pp.x, pp.y - js * 125); ctx.rotate(tilt);
        if (slideT > 0) ctx.scale(1.18, 0.58); else if (land > 0) ctx.scale(1 + land * 0.18, 1 - land * 0.15);
        if (shieldT > 0) { ctx.strokeStyle = `rgba(76,201,240,${0.5 + 0.3 * Math.sin(T * 10)})`; ctx.lineWidth = 4; ctx.beginPath(); ctx.ellipse(0, -40, 62, 56, 0, 0, 7); ctx.stroke(); }
        if (starT > 0) { ctx.shadowColor = "#ffd36b"; ctx.shadowBlur = 24; }
        ctx.font = "88px serif"; ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText("🛺", 0, 8);
        ctx.restore();
        // particles
        for (let i = parts.length - 1; i >= 0; i--) { const d = parts[i]; d.t += dt; d.vy += 500 * dt; d.x += d.vx * dt; d.y += d.vy * dt; if (d.t > 0.9) { parts.splice(i, 1); continue; } ctx.globalAlpha = 1 - d.t / 0.9; ctx.fillStyle = d.c; ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, 7); ctx.fill(); }
        ctx.globalAlpha = 1;
        drawFloats(ctx, floats, dt);
        // --- HUD: coins, metres, combo meter, power-up timers, milestone banner
        ctx.fillStyle = "rgba(10,6,20,.55)"; ctx.beginPath(); ctx.roundRect(10, 10, 168, 34, 12); ctx.fill();
        ctx.fillStyle = "#ffc145"; ctx.font = "800 15px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
        ctx.fillText(`₹ ${coins}`, 22, 27); ctx.fillStyle = "#fff"; ctx.fillText(`${Math.round(dist)} m`, 92, 27);
        if (mult > 1) { ctx.save(); ctx.translate(g.w - 70, 30); ctx.scale(1 + 0.1 * Math.sin(T * 10), 1 + 0.1 * Math.sin(T * 10)); ctx.fillStyle = "#ff5fae"; ctx.font = "900 26px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "center"; ctx.shadowColor = "#ff3d9a"; ctx.shadowBlur = 16; ctx.fillText(`x${mult}`, 0, 0); ctx.restore(); }
        let py = 56;
        for (const [t, max, ic, col] of [[magnetT, 7, "🧲", "#ff5fae"], [shieldT, 12, "🛡️", "#4cc9f0"], [starT, 8, "⭐", "#ffd36b"]]) {
          if (t <= 0) continue;
          ctx.font = "16px serif"; ctx.textAlign = "left"; ctx.fillText(ic, 14, py + 2);
          ctx.fillStyle = "rgba(255,255,255,.15)"; ctx.fillRect(38, py - 4, 90, 8); ctx.fillStyle = col; ctx.fillRect(38, py - 4, 90 * t / max, 8); py += 22;
        }
        if (banner) {
          banner.t += dt; const a = banner.t < 0.25 ? banner.t / 0.25 : banner.t > 1.6 ? Math.max(0, 1 - (banner.t - 1.6) / 0.4) : 1;
          if (banner.t > 2) banner = null; else {
            ctx.save(); ctx.globalAlpha = a; ctx.translate(g.w / 2, g.h * 0.42); const sc = 0.8 + 0.2 * Math.min(1, banner.t * 4); ctx.scale(sc, sc);
            ctx.textAlign = "center"; ctx.fillStyle = "#fff"; ctx.shadowColor = "#ff9f1c"; ctx.shadowBlur = 24; ctx.font = "900 36px 'Plus Jakarta Sans', sans-serif"; ctx.fillText(banner.text, 0, 0);
            ctx.shadowBlur = 0; ctx.fillStyle = "#ffd36b"; ctx.font = "700 15px 'Plus Jakarta Sans', sans-serif"; ctx.fillText(banner.sub, 0, 28); ctx.restore();
          }
        }
        if (BEST > 0 && !passedBest) { ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.font = "700 12px 'Plus Jakarta Sans', sans-serif"; ctx.textAlign = "right"; ctx.fillText(`BEST ${BEST}`, g.w - 14, g.h - 14); }
        if (t0 < 3.5 && !over) { ctx.textAlign = "center"; ctx.globalAlpha = Math.min(1, 3.5 - t0); ctx.fillStyle = "#fff"; ctx.font = "800 15px 'Plus Jakarta Sans', sans-serif"; ctx.fillText("Swipe ← → · ↑ jump 🚧 · ↓ duck banners · chain coins for combos", g.w / 2, g.h * 0.55); ctx.globalAlpha = 1; }
        if (flash > 0) { flash -= dt; ctx.fillStyle = `rgba(255,255,255,${flash})`; ctx.fillRect(-20, -20, g.w + 40, g.h + 40); }
        ctx.restore();
      });
      return () => { stop(); ro.disconnect(); stage.removeEventListener("pointerdown", down); stage.removeEventListener("pointerup", up); removeEventListener("keydown", key); };
    },
  };

  // ------------------------------------------------------------ 5. Table Quiz (live, between tables)
  const tableQuiz = {
    id: "quiz", name: "Table Quiz", icon: "🏆", hue: 140, live: true,
    desc: "Live quiz against the other tables. 8 questions, 15 seconds each. The winning table gets a FREE TEA ☕",
    start(stage, api) {
      const sess = opts.session && opts.session();
      stage.innerHTML = `<div class="qz"></div>`;
      const box = stage.querySelector(".qz");
      if (!sess) { box.innerHTML = `<div class="qz-msg"><div class="qz-big">🏆</div><h3>Start ordering to play</h3><p class="muted">The Table Quiz is for tables that are ordering. Tap “Start ordering” first, then come back.</p></div>`; return () => {}; }
      let st = null, key = "", deadline = 0, busy = false, timer = 0, alive = true;
      const H = { "X-Guest-Token": sess.token };
      const fmt = s => s >= 60 ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : `${Math.ceil(s)}s`;
      async function load() {
        if (!alive || busy) return;
        try { show(await BD.api(`/api/t/${encodeURIComponent(opts.tableToken)}/quiz?session=${sess.sid}`, { headers: H })); }
        catch (e) { box.innerHTML = `<div class="qz-msg"><p class="muted">${BD.esc(e.message)}</p></div>`; }
      }
      async function join() {
        busy = true;
        try { show(await BD.api(`/api/session/${sess.sid}/quiz/join`, { method: "POST", body: {}, headers: H })); BD.buzz(15); }
        catch (e) { BD.toast(e.message, "bad"); }
        busy = false;
      }
      async function answer(i) {
        if (!st || st.phase !== "question" || !st.joined || st.my_answer) return;
        st.my_answer = { choice: i };
        box.querySelectorAll(".qz-opt").forEach((b, k) => { b.disabled = true; b.classList.toggle("picked", k === i); });
        box.querySelector(".qz-note").textContent = "Locked in for your table. Waiting for the answer…";
        BD.buzz(10); BD.sound.chime("tap");
        try { await BD.api(`/api/session/${sess.sid}/quiz/answer`, { body: { round_id: st.round_id, q_index: st.q_index, choice: i }, headers: H }); }
        catch (e) { BD.toast(e.message, "bad"); }
      }
      const board = players => `<div class="qz-board">${players.length ? players.map((p, i) => `<div class="qz-row ${p.me ? "me" : ""}"><span>${["🥇", "🥈", "🥉"][i] || i + 1}</span><span class="grow">Table ${p.table}${p.me ? " (you)" : ""}</span><b class="mono">${p.score}</b></div>`).join("") : `<p class="faint small">No tables yet</p>`}</div>`;
      function show(s) {
        st = s;
        const me = (s.players || []).find(p => p.me);
        api.setScore(me ? me.score : 0, "pts");
        deadline = Date.now() + ((s.phase === "lobby" ? s.starts_in : s.time_left) || 0) * 1000;
        const k = `${s.phase}|${s.round_id}|${s.q_index}|${s.joined}|${(s.players || []).length}|${JSON.stringify(s.my_answer || null)}|${s.reward_status || ""}`;
        if (k === key) return tick();
        key = k;
        let h = "";
        if (s.phase === "none") {
          h = `<div class="qz-msg"><div class="qz-big float">🏆</div><h3>Challenge the other tables!</h3>
            <p class="muted">A round starts 30 seconds after the first table joins, so others can join too. 8 questions, 15 seconds each. Faster right answers score more.</p>
            <p class="qz-prize">☕ Winning table gets a free tea<br><span class="faint small">(needs at least ${s.min_tables} tables playing)</span></p>
            <button class="btn lg" data-join>Join the quiz</button></div>`;
        } else if (s.phase === "lobby") {
          h = `<div class="qz-msg"><div class="eyebrow">Next quiz starts in</div><div class="qz-count mono" data-count>${fmt(s.starts_in)}</div>
            ${s.joined ? `<p class="muted">Your table is in! Tell the other tables to join on their phones 📣</p>` : `<button class="btn lg" data-join>Join the quiz</button>`}
            <p class="qz-prize">☕ Winning table gets a free tea</p>${board(s.players)}</div>`;
        } else if (s.phase === "question" || s.phase === "reveal") {
          const q = s.question, mine = s.my_answer, rev = s.phase === "reveal";
          h = `<div class="qz-q"><div class="row spread"><span class="eyebrow">Question ${s.q_index + 1} of ${s.q_total}</span><span class="mono qz-time" data-count>${fmt(s.time_left)}</span></div>
            <div class="qz-bar"><i data-bar></i></div>
            <h3 class="qz-text">${BD.esc(q.text)}</h3>
            <div class="qz-opts">${q.options.map((o, i) => {
              let cls = "";
              if (rev) cls = i === s.correct ? "right" : (mine && mine.choice === i ? "wrong" : "dim");
              else if (mine && mine.choice === i) cls = "picked";
              return `<button class="qz-opt ${cls}" data-opt="${i}" ${rev || mine || !s.joined ? "disabled" : ""}><span class="qz-l">${"ABCD"[i]}</span>${BD.esc(o)}</button>`;
            }).join("")}</div>
            <p class="qz-note muted small">${!s.joined ? "Watching. Join the next round to play." : rev ? (mine ? (mine.correct ? `✅ Correct! +${mine.points} points` : "❌ Not this time") : "⏱ Your table didn't answer") : mine ? "Locked in for your table. Waiting for the answer…" : "One answer per table. Be quick!"}</p>
            ${rev ? board(s.players) : ""}</div>`;
          if (rev && mine && mine.correct) BD.buzz([10, 30, 10]);
        } else if (s.phase === "done") {
          const w = s.winner;
          h = `<div class="qz-msg"><div class="qz-big">${w && w.me ? "🎉" : "🏁"}</div>
            <h3>${w ? (w.me ? "Your table won!" : `Table ${w.table} wins!`) : "Quiz over"}</h3>
            ${w && w.me && s.reward_status === "pending" ? `<p class="qz-prize">☕ Your free tea is on its way. The cashier has been told.</p>` : ""}
            ${w && w.me && s.reward_status === "given" ? `<p class="qz-prize">☕ Free tea added to your table at ₹0. Enjoy!</p>` : ""}
            ${w && w.me && s.reward_status === "none" ? `<p class="faint small">Free tea needs at least ${s.min_tables} tables. Get another table to play next time!</p>` : ""}
            ${board(s.players)}<button class="btn" data-join style="margin-top:14px">Play the next round</button></div>`;
          if (w && w.me && show._celebrated !== s.round_id) { show._celebrated = s.round_id; BD.confetti(140); }
        }
        box.innerHTML = h;
        box.querySelectorAll("[data-join]").forEach(b => b.onclick = join);
        box.querySelectorAll("[data-opt]").forEach(b => b.onclick = () => answer(Number(b.dataset.opt)));
        tick();
      }
      function tick() {
        if (!st) return;
        const left = Math.max(0, (deadline - Date.now()) / 1000);
        const c = box.querySelector("[data-count]"); if (c) c.textContent = fmt(left);
        const bar = box.querySelector("[data-bar]"); if (bar) bar.style.width = (st.phase === "question" ? (left / 15) * 100 : 0) + "%";
      }
      load();
      timer = setInterval(() => { tick(); if (Date.now() >= deadline - 200 || Math.random() < 0.34) load(); }, 1000);
      return () => { alive = false; clearInterval(timer); stage.innerHTML = ""; };
    },
  };

  const GAMES = [rickshawRush, dosaFlip, chaiCatch, spiceMatch];

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
    const extra = (window.BD_LIVE_GAMES || []).filter(g => g.enabled(opts));  // Bill Roulette, Housie, Lucky Spin
    const list = (opts.quizEnabled ? [tableQuiz] : []).concat(extra, GAMES);
    const room = opts.roomsEnabled ? `<div class="gx-modes">
        <button class="glass gx-mode" data-mode="all"><span class="gx-ico">🏆</span><b>Play with all tables</b><span class="muted small">${opts.quizEnabled ? "Live restaurant quiz + leaderboard" : "Games + today's leaderboard"}</span></button>
        <button class="glass gx-mode" data-mode="room"><span class="gx-ico">👨‍👩‍👧</span><b>Play with my table</b><span class="muted small">A private trivia room just for your group</span></button></div>` : "";
    el.querySelector(".gx-body").innerHTML = room + `<div class="gx-pick">${list.map((g, i) => `
      <button class="glass gx-card ${g.live ? "live" : ""}" data-g="${g.id}" data-tilt="8" style="--h:${g.hue};animation-delay:${i * 0.08}s">
        <span class="gx-ico">${g.icon}</span>
        <span class="gx-name">${g.name}${g.live ? ` <span class="live-tag">LIVE</span>` : ""}</span>
        <span class="gx-desc">${esc(g.desc)}</span>
        <span class="gx-best">${g.tag ? g.tag : g.live ? "Play against other tables · win a free tea" : best(g.id) ? `Your best: <b>${best(g.id)}</b>` : "Not played yet"}</span>
      </button>`).join("")}</div>`;
    el.querySelectorAll(".gx-card").forEach(b => b.onclick = () => play(list.find(g => g.id === b.dataset.g)));
    el.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => {
      if (b.dataset.mode === "room") return roomPanel();
      if (opts.quizEnabled) play(tableQuiz); else el.querySelector(".gx-pick").scrollIntoView({ behavior: "smooth" });
    });
    BD.tilt(el);
  }
  function play(game) {
    stopCurrent();
    BD.sound.unlock();
    el.querySelector(".gx-title b").textContent = game.name;
    el.querySelector(".gx-sub").textContent = "";
    const body = el.querySelector(".gx-body");
    body.innerHTML = `<div class="gx-stage ${game.id === "memory" ? "dom" : ""} ${game.id === "quiz" || game.scroll ? "quiz" : ""}"></div>`;
    const stage = body.querySelector(".gx-stage");
    let lastScore = 0, lastLives = null, label = "", extra = "";
    const api = {
      setScore(s, l) { lastScore = s; label = l || ""; hud(lastScore, lastLives, label, extra); },
      setLives(n) { lastLives = n; hud(lastScore, lastLives, label, extra); },
      setExtra(x) { extra = x; hud(lastScore, lastLives, label, extra); },
      end(score) { gameOver(game, score); },
    };
    stopGame = game.start(stage, api, opts);
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
  // private game room for this table: its own QR + link; the link opens only the game
  async function roomPanel() {
    stopCurrent(); hud(null, null);
    el.querySelector(".gx-title b").textContent = "Play with my table";
    el.querySelector(".gx-sub").textContent = "";
    const body = el.querySelector(".gx-body");
    const sess = opts.session && opts.session();
    if (!sess) { body.innerHTML = `<div class="gx-over"><div class="gx-big">👨‍👩‍👧</div><p class="muted">Start ordering at your table first, then make a private game room.</p><button class="btn-ghost gx-menu">Back</button></div>`; body.querySelector(".gx-menu").onclick = picker; return; }
    body.innerHTML = `<div class="gx-over"><div class="loader-orb" style="width:60px;height:60px"><i></i><i></i><i></i><b></b></div></div>`;
    let r;
    try { r = await BD.api(`/api/session/${sess.sid}/game-room`, { body: {}, headers: { "X-Guest-Token": sess.token } }); }
    catch (x) { body.innerHTML = `<div class="gx-over"><p class="muted">${esc(x.message)}</p><button class="btn-ghost gx-menu">Back</button></div>`; body.querySelector(".gx-menu").onclick = picker; return; }
    body.innerHTML = `<div class="gx-over"><div class="eyebrow">Private trivia room</div><h3 style="margin:6px 0 4px">Scan to join</h3>
      <p class="muted small">Everyone at your table scans this (or opens the link). It opens only the game.</p>
      <div style="background:#fff;border-radius:16px;padding:10px;width:200px;margin:12px auto"><img src="${esc(r.qr)}" alt="Game room QR code" style="width:100%"></div>
      <div class="row" style="gap:8px;justify-content:center;flex-wrap:wrap"><a class="btn" href="${esc(r.url)}" target="_blank" rel="noopener">Open the game ↗</a>
        <a class="btn-ghost" href="https://wa.me/?text=${encodeURIComponent("Join our table trivia: " + r.url)}" target="_blank" rel="noopener">Share on WhatsApp</a></div>
      <button class="btn-ghost gx-menu" style="margin-top:12px">Other games</button></div>`;
    body.querySelector(".gx-menu").onclick = picker;
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
