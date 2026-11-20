/* Bolo Dukaan — shared helpers (window.BD) */
(function () {
  "use strict";
  const BD = {};

  // ---------- storage (never throws) ----------
  BD.store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
    del(k) { try { localStorage.removeItem(k); } catch (e) {} },
  };

  BD.deviceId = function () {
    let id = BD.store.get("bd_device");
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/-/g, "").slice(0, 32);
      BD.store.set("bd_device", id);
    }
    return id;
  };

  // ---------- reload after a server update ----------
  // The server sends its build id on every API response. If it changes, the page is running old code:
  // reload as soon as nobody is typing, recording, or looking at a sheet, game or dialog.
  let firstBuild = null, reloadWanted = false;
  BD.noteBuild = function (b) {
    if (!b) return;
    if (!firstBuild) { firstBuild = b; return; }
    if (b !== firstBuild && !reloadWanted) { reloadWanted = true; tryReload(); }
  };
  function busyNow() {
    const a = document.activeElement;
    if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT")) return true;
    return !!document.querySelector(".sheet.show, .modal.show, .drawer.show, .gx.show, .voice-orb.rec, .voice-orb.think");
  }
  function tryReload() {
    if (!busyNow()) {
      BD.toast("The app was updated. Refreshing…", "info", 1500);
      setTimeout(() => location.reload(), 900);
    } else setTimeout(tryReload, 3000);
  }

  // ---------- API ----------
  BD.api = async function (path, opts = {}) {
    const init = { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), headers: Object.assign({}, opts.headers), credentials: "same-origin" };
    if (opts.form) init.body = opts.form;
    else if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
    let res;
    try { res = await fetch(path, init); }
    catch (e) { const err = new Error("No connection. Check your internet."); err.status = 0; throw err; }
    BD.noteBuild(res.headers.get("X-App-Build"));
    let data = null;
    const type = res.headers.get("content-type") || "";
    if (type.includes("application/json")) { try { data = await res.json(); } catch (e) {} }
    if (!res.ok) {
      let msg = "Something went wrong";
      if (data && data.detail) {
        msg = typeof data.detail === "string" ? data.detail
          : Array.isArray(data.detail) ? data.detail.map(d => (d.loc ? d.loc[d.loc.length - 1] + ": " : "") + d.msg).join(", ") : msg;
      }
      const err = new Error(msg); err.status = res.status; err.data = data; throw err;
    }
    return data;
  };

  // ---------- format ----------
  const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
  BD.rupees = p => "₹" + inr.format((p || 0) / 100);
  BD.esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  BD.qs = k => new URLSearchParams(location.search).get(k);
  BD.ago = iso => {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    return Math.floor(s / 3600) + " h ago";
  };
  BD.sleep = ms => new Promise(r => setTimeout(r, ms));

  const EMOJI = [
    [/dosa|dose|uttapam|pesarattu/i, "🥞"], [/idli|idly/i, "🍚"], [/vada|bonda|bajji|pakora|samosa/i, "🥟"],
    [/coffee|kaapi|kapi/i, "☕"], [/chai|tea/i, "🍵"], [/lassi|milk|shake|buttermilk|majjige/i, "🥛"],
    [/juice|soda|lime|nimbu|cola|drink|beverage/i, "🧃"], [/water/i, "💧"], [/biryani|pulao|rice|bath|meals|thali/i, "🍛"],
    [/roti|naan|chapati|paratha|parotta|kulcha|bread/i, "🫓"], [/paneer/i, "🧀"], [/chicken|kebab|tikka|tandoor/i, "🍗"],
    [/mutton|lamb|goat/i, "🍖"], [/fish|prawn|seafood/i, "🐟"], [/egg|omelette/i, "🥚"], [/noodle|chowmein|hakka/i, "🍜"],
    [/soup|rasam|sambar/i, "🥣"], [/salad/i, "🥗"], [/burger/i, "🍔"], [/pizza/i, "🍕"], [/sandwich/i, "🥪"],
    [/fries|chips/i, "🍟"], [/ice ?cream|kulfi|sundae/i, "🍨"], [/cake|pastry/i, "🍰"],
    [/sweet|dessert|halwa|jamun|payasa|kheer|mysore pak|ladoo|jalebi/i, "🍮"], [/curry|masala|dal|gravy|sabzi/i, "🍲"],
    [/chaat|pani ?puri|bhel|pav/i, "🥙"],
  ];
  BD.foodEmoji = (name, cat) => {
    const s = (name || "") + " " + (cat || "");
    for (const [re, e] of EMOJI) if (re.test(s)) return e;
    return "🍽️";
  };
  BD.hueFor = s => { let h = 0; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };

  // ---------- toast ----------
  BD.toast = function (msg, kind = "info", ms = 3800) {
    let box = document.getElementById("toasts");
    if (!box) { box = document.createElement("div"); box.id = "toasts"; box.setAttribute("role", "status"); box.setAttribute("aria-live", "polite"); document.body.appendChild(box); }
    const el = document.createElement("div");
    el.className = "toast " + kind;
    const ic = { ok: "✓", bad: "!", info: "i", say: "🔊" }[kind] || "i";
    el.innerHTML = `<span class="ic">${ic}</span><span>${BD.esc(msg)}</span>`;
    box.appendChild(el);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 380); }, ms);
  };

  BD.busy = function (btn, on, label) {
    if (!btn) return;
    if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>${label ? " " + BD.esc(label) : ""}`; }
    else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
  };

  // ---------- 3D tilt ----------
  const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  BD.tilt = function (root = document) {
    if (!fine || still) return;
    root.querySelectorAll("[data-tilt]:not([data-tilt-on])").forEach(el => {
      el.dataset.tiltOn = "1";
      el.classList.add("tilt");
      const max = parseFloat(el.dataset.tilt) || 8;
      el.addEventListener("pointermove", e => {
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        el.style.setProperty("--ry", ((x - 0.5) * max * 2).toFixed(2) + "deg");
        el.style.setProperty("--rx", ((0.5 - y) * max * 2).toFixed(2) + "deg");
        el.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
        el.style.setProperty("--my", (y * 100).toFixed(1) + "%");
        el.classList.add("tilting");
      });
      el.addEventListener("pointerleave", () => {
        el.classList.remove("tilting");
        el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg");
      });
    });
  };

  // ---------- reveal on scroll ----------
  BD.reveal = function (root = document) {
    const els = root.querySelectorAll(".reveal:not(.in)");
    if (!("IntersectionObserver" in window)) { els.forEach(e => e.classList.add("in")); return; }
    const io = new IntersectionObserver(entries => entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } }), { threshold: 0.12 });
    els.forEach(e => io.observe(e));
  };

  // ---------- sound (Web Audio chimes, no files) ----------
  let actx = null;
  BD.sound = {
    unlock() {
      try {
        actx = actx || new (window.AudioContext || window.webkitAudioContext)();
        if (actx.state === "suspended") actx.resume();
        return true;
      } catch (e) { return false; }
    },
    get ready() { return !!actx && actx.state === "running"; },
    chime(kind = "order") {
      if (!actx) return;
      const notes = { order: [659, 880, 1175], paid: [523, 659, 784, 1047], waiter: [880, 660, 880, 660], start: [587, 784], tap: [900] }[kind] || [800];
      const t0 = actx.currentTime + 0.02;
      notes.forEach((f, i) => {
        const o = actx.createOscillator(), g = actx.createGain();
        o.type = kind === "waiter" ? "triangle" : "sine";
        o.frequency.value = f;
        const t = t0 + i * (kind === "tap" ? 0 : 0.14);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(kind === "tap" ? 0.08 : 0.25, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + (kind === "tap" ? 0.08 : 0.5));
        o.connect(g).connect(actx.destination);
        o.start(t); o.stop(t + 0.6);
      });
    },
  };

  // ---------- haptics ----------
  BD.buzz = ms => { try { navigator.vibrate && navigator.vibrate(ms || 12); } catch (e) {} };

  // ---------- confetti ----------
  BD.confetti = function (n = 160) {
    if (still) return;
    const c = document.createElement("canvas");
    c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:120";
    document.body.appendChild(c);
    const ctx = c.getContext("2d"), dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = innerWidth * dpr; c.height = innerHeight * dpr; ctx.scale(dpr, dpr);
    const colors = ["#ff9f1c", "#ffc145", "#ff4d6d", "#ff3d9a", "#2ee6a6", "#4cc9f0", "#9b5cff"];
    const P = Array.from({ length: n }, () => ({
      x: innerWidth / 2 + (Math.random() - .5) * 120, y: innerHeight * .45,
      vx: (Math.random() - .5) * 14, vy: -Math.random() * 16 - 4, s: 6 + Math.random() * 8,
      r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: colors[(Math.random() * colors.length) | 0], life: 0,
    }));
    let frame = 0;
    (function tick() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      P.forEach(p => {
        p.vy += .38; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c;
        ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2 * (0.4 + Math.abs(Math.sin(p.r * 2)))); ctx.restore();
      });
      if (++frame < 220) requestAnimationFrame(tick); else c.remove();
    })();
  };

  // ---------- owner chrome ----------
  BD.logoSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11h16"/><path d="M5 11a7 7 0 0 1 14 0"/><path d="M12 4V2.5"/><path d="M3 15h18"/><path d="M8 19h8"/></svg>`;
  BD.ownerNav = function (active) {
    const links = [["/dashboard", "Dashboard"], ["/owner/menu", "Menu"], ["/owner/qr", "QR codes"], ["/owner/setup", "Setup"]];
    const nav = document.getElementById("nav");
    if (!nav) return;
    nav.innerHTML = `<div class="container">
      <a class="brand" href="/dashboard"><span class="brand-mark">${BD.logoSvg}</span><span class="word">Bolo Dukaan</span></a>
      <nav class="nav-links">${links.map(([h, t]) => `<a href="${h}" class="${h === active ? "active" : ""}">${t}</a>`).join("")}
      <a href="#" id="logout">Log out</a></nav></div>`;
    nav.querySelector("#logout").addEventListener("click", async e => {
      e.preventDefault();
      try { await BD.api("/api/owner/logout", { method: "POST" }); } catch (_) {}
      location.href = "/owner/login";
    });
  };
  BD.requireOwner = async function () {
    try { return await BD.api("/api/owner/me"); }
    catch (e) { if (e.status === 401) location.href = "/owner/login?next=" + encodeURIComponent(location.pathname); throw e; }
  };

  // ---------- voice recorder (mic -> 16 kHz mono WAV), shared by the owner mic and the store pages ----------
  BD.canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder && window.isSecureContext);
  BD.recorder = function (onLevel) {
    let rec = null, stream = null, chunks = [], raf = 0, actx = null, timer = 0;
    const api = {
      get recording() { return !!rec && rec.state === "recording"; },
      async start(maxMs = 15000) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
        chunks = []; rec = new MediaRecorder(stream);
        rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        rec.start(250);
        try {
          actx = new (window.AudioContext || window.webkitAudioContext)();
          const an = actx.createAnalyser(); an.fftSize = 512; actx.createMediaStreamSource(stream).connect(an);
          const buf = new Uint8Array(an.fftSize);
          const loop = () => { an.getByteTimeDomainData(buf); let s = 0; for (const v of buf) s += ((v - 128) / 128) ** 2; onLevel && onLevel(Math.min(1, Math.sqrt(s / buf.length) * 4)); raf = requestAnimationFrame(loop); };
          loop();
        } catch (e) {}
        return new Promise(resolve => { timer = setTimeout(() => resolve(api.stop()), maxMs); api._resolveAuto = resolve; });
      },
      stop() {
        clearTimeout(timer); cancelAnimationFrame(raf); onLevel && onLevel(0);
        if (actx) { actx.close().catch(() => {}); actx = null; }
        return new Promise(resolve => {
          if (!rec || rec.state !== "recording") return resolve(null);
          rec.onstop = async () => {
            if (stream) stream.getTracks().forEach(t => t.stop());
            const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
            try { resolve(await BD.toWav(blob)); } catch (e) { resolve(blob); }
          };
          rec.stop();
        });
      },
    };
    return api;
  };
  BD.toWav = async function (blob) {
    const Ctx = window.AudioContext || window.webkitAudioContext, ctx = new Ctx();
    const audio = await ctx.decodeAudioData(await blob.arrayBuffer());
    ctx.close().catch(() => {});
    const rate = 16000, off = new OfflineAudioContext(1, Math.max(1, Math.ceil(audio.duration * rate)), rate);
    const src = off.createBufferSource(); src.buffer = audio; src.connect(off.destination); src.start();
    const pcm = (await off.startRendering()).getChannelData(0);
    const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
    const w = (o, s) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
    w(0, "RIFF"); out.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVE"); w(12, "fmt "); out.setUint32(16, 16, true);
    out.setUint16(20, 1, true); out.setUint16(22, 1, true); out.setUint32(24, rate, true); out.setUint32(28, rate * 2, true);
    out.setUint16(32, 2, true); out.setUint16(34, 16, true); w(36, "data"); out.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i++) { const s = Math.max(-1, Math.min(1, pcm[i])); out.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true); }
    return new Blob([out.buffer], { type: "audio/wav" });
  };
  BD.play = function (dataUrl) { if (!dataUrl) return; try { const a = new Audio(dataUrl); a.play().catch(() => {}); return a; } catch (e) {} };

  // ---------- Sign in with Google (owners) ----------
  // Renders Google's official button into `box`. mode: "signup" | "signin". getExtra() adds fields (restaurant name).
  BD.googleButton = async function (box, mode, getExtra, onError) {
    let cfg = {};
    try { cfg = await BD.api("/api/auth/config"); } catch (e) {}
    const G_ICON = `<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/><path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>`;
    if (!cfg.google_client_id) {
      box.innerHTML = `<button type="button" class="btn-ghost block g-off" disabled title="Add GOOGLE_CLIENT_ID to .env to turn this on">${G_ICON}<span>Continue with Google</span></button>
        <p class="faint small center" style="margin:6px 0 0">Google sign-in turns on when <span class="kbd">GOOGLE_CLIENT_ID</span> is in .env</p>`;
      return;
    }
    box.innerHTML = `<div class="g-wrap"><div class="g-btn"></div></div>`;
    await new Promise((ok, bad) => {
      if (window.google && google.accounts && google.accounts.id) return ok();
      const s = document.createElement("script"); s.src = "https://accounts.google.com/gsi/client"; s.async = true;
      s.onload = ok; s.onerror = bad; document.head.appendChild(s);
    }).catch(() => { box.innerHTML = `<p class="faint small center">Couldn't load Google sign-in (no internet?)</p>`; });
    if (!(window.google && google.accounts && google.accounts.id)) return;
    google.accounts.id.initialize({
      client_id: cfg.google_client_id,
      ux_mode: "popup",
      callback: async res => {
        try {
          const r = await BD.api("/api/owner/google", { body: Object.assign({ credential: res.credential }, getExtra ? getExtra() : {}) });
          const next = BD.qs("next");
          location.href = (next && next.startsWith("/") && !next.startsWith("//")) ? next : r.next;
        } catch (x) { (onError || BD.toast)(x.message, "bad"); }
      },
    });
    const width = Math.min(400, Math.max(220, box.clientWidth || 320));
    google.accounts.id.renderButton(box.querySelector(".g-btn"), {
      type: "standard", theme: "filled_black", size: "large", shape: "pill", logo_alignment: "left",
      text: mode === "signup" ? "signup_with" : "continue_with", width,
    });
  };

  // ---------- Kannada / Hindi / English alert phrases ----------
  BD.phrases = {
    "kn-IN": { start: n => `ಟೇಬಲ್ ${n}, ಹೊಸ ಗ್ರಾಹಕರು ಬಂದಿದ್ದಾರೆ`, order: n => `ಟೇಬಲ್ ${n}, ಹೊಸ ಆರ್ಡರ್`, waiter: n => `ಟೇಬಲ್ ${n}, ವೇಟರ್ ಬೇಕು`, bill: n => `ಟೇಬಲ್ ${n}, ಬಿಲ್ ಕೇಳುತ್ತಿದ್ದಾರೆ`, paid: n => `ಟೇಬಲ್ ${n}, ಬಿಲ್ ಪಾವತಿ ಆಗಿದೆ` },
    "hi-IN": { start: n => `टेबल ${n}, नए ग्राहक आए हैं`, order: n => `टेबल ${n}, नया ऑर्डर`, waiter: n => `टेबल ${n}, वेटर चाहिए`, bill: n => `टेबल ${n}, बिल माँगा है`, paid: n => `टेबल ${n}, बिल का भुगतान हो गया` },
    "en-IN": { start: n => `Table ${n}, new guests`, order: n => `Table ${n}, new order`, waiter: n => `Table ${n} needs help`, bill: n => `Table ${n} wants the bill`, paid: n => `Table ${n} has paid`, },
  };

  BD.boot = function () { BD.tilt(); BD.reveal(); };
  document.addEventListener("DOMContentLoaded", BD.boot);
  window.BD = BD;
})();
