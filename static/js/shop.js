/* Customer shop: home, product grid, cart, voice add, checkout, order status. The planner lives in planner.js.
   Prices and totals always come from the server; the page only shows them. Nothing is ordered without a tap on Pay. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const parts = location.pathname.split("/").filter(Boolean); // ["s", slug] or ["s", slug, "order", id]
  const SLUG = decodeURIComponent(parts[1] || "");
  const ORDER_ID = parts[2] === "order" ? Number(parts[3]) : null;
  const API = "/api/s/" + encodeURIComponent(SLUG);
  const S = window.SHOP = { slug: SLUG, api: API, info: null, products: [], byId: new Map(), cart: new Map() };

  // ---------- helpers ----------
  S.emoji = BD.groceryEmoji;
  S.packLabel = p => {
    const n = Number(p.pack_size), u = p.pack_unit;
    if (u === "g" && n >= 1000) return (n / 1000).toLocaleString("en-IN") + " kg";
    if (u === "ml" && n >= 1000) return (n / 1000).toLocaleString("en-IN") + " L";
    return n.toLocaleString("en-IN") + " " + (u === "pcs" ? (n === 1 ? "pc" : "pcs") : u);
  };
  S.pic = (url, fallback, credit) => url
    ? `<img src="${BD.esc(url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=&quot;e&quot;>${fallback}</span>'">${credit ? `<span class="credit" title="${BD.esc(credit)}">© ${BD.esc(credit)}</span>` : ""}`
    : `<span class="e">${fallback}</span>`;
  // Sarvam / AI calls: give up after 15 s and let the shopper tap instead.
  S.timed = (p, ms = 15000) => Promise.race([p, new Promise((_, bad) => setTimeout(() => { const e = new Error("That took too long. Please tap instead."); e.status = 408; bad(e); }, ms))]);
  S.openSheet = id => { document.querySelectorAll(".sheet.show").forEach(s => s.classList.remove("show")); $(id).classList.add("show"); $("ov").classList.add("show"); };
  S.closeSheets = () => { document.querySelectorAll(".sheet.show").forEach(s => s.classList.remove("show")); $("ov").classList.remove("show"); S.onClose && S.onClose(); };
  $("ov").addEventListener("click", S.closeSheets);
  document.addEventListener("click", e => { if (e.target.closest("[data-close]")) S.closeSheets(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") S.closeSheets(); });
  S.countUp = (el, to, ms = 600) => {
    const from = Number(el.dataset.v || 0); el.dataset.v = to;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || from === to) { el.textContent = BD.rupees(to); return; }
    const t0 = performance.now();
    const step = t => { const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3); el.textContent = BD.rupees(Math.round(from + (to - from) * e)); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };

  // ---------- views ----------
  const VIEWS = { home: "vHome", shop: "vShop", plan: "vPlan", recipes: "vRecipes", pcart: "vPCart", order: "vOrder" };
  S.show = function (name) {
    if (document.querySelector(".sheet.show")) S.closeSheets();
    Object.values(VIEWS).forEach(v => $(v).classList.add("hidden"));
    $(VIEWS[name] || "vHome").classList.remove("hidden");
    document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", a.dataset.nav === name || (name !== "home" && name !== "shop" && a.dataset.nav === "plan")));
    const directCart = name === "home" || name === "shop";
    $("cartFab").style.display = directCart ? "" : "none";
    $("micFab").style.display = directCart ? "" : "none";
    BD.reveal(); BD.tilt();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  S.go = name => { if (location.hash !== "#" + name) location.hash = name; else route(); };
  document.addEventListener("click", e => { const g = e.target.closest("[data-go]"); if (g) { e.preventDefault(); S.go(g.dataset.go); } });
  function route() {
    const h = (location.hash || "#home").slice(1);
    if (h === "shop") { S.show("shop"); renderGrid(); }
    else if (["plan", "recipes", "pcart"].includes(h) && S.info.features.meal_planner && window.PLANNER) window.PLANNER.route(h);
    else S.show("home");
  }
  window.addEventListener("hashchange", () => { if (S.info && !ORDER_ID) route(); });

  // ---------- boot ----------
  async function boot() {
    $("mark").innerHTML = BD.logoSvg;
    try { S.info = await BD.api(API); }
    catch (e) { $("loading").classList.add("hidden"); $("fatal").classList.remove("hidden"); $("fatal").innerHTML = `<div class="big-ic">🏪</div><h2 style="margin:10px 0">Store not found</h2><p class="muted">${BD.esc(e.message)}</p>`; return; }
    $("loading").classList.add("hidden");
    document.title = S.info.store.name;
    $("sname").textContent = S.info.store.name; $("heroName").textContent = S.info.store.name;
    S.products = S.info.products; S.byId = new Map(S.products.map(p => [p.id, p]));
    if (S.info.features.meal_planner) { $("navPlan").classList.remove("hidden"); $("modePlan").classList.remove("hidden"); }
    if (S.info.features.voice) $("micFab").classList.remove("hidden");
    if (S.info.features.aisle_finder) $("findBtn").classList.remove("hidden");
    loadCart();
    if (ORDER_ID) { S.show("order"); $("cartFab").style.display = "none"; $("micFab").style.display = "none"; return orderPage(); }
    renderCats(); route(); updateFab();
  }

  // ---------- product grid ----------
  let cat = "", q = "";
  function renderCats() {
    $("cats").innerHTML = [`<button class="pill ${cat ? "" : "active"}" data-cat="">All</button>`]
      .concat(S.info.categories.map(c => `<button class="pill ${c === cat ? "active" : ""}" data-cat="${BD.esc(c)}">${S.emoji(c)} ${BD.esc(c)}</button>`)).join("");
  }
  $("cats").addEventListener("click", e => { const b = e.target.closest("[data-cat]"); if (!b) return; cat = b.dataset.cat; renderCats(); renderGrid(); });
  let qT; $("q").addEventListener("input", e => { clearTimeout(qT); qT = setTimeout(() => { q = e.target.value.trim().toLowerCase(); renderGrid(); }, 120); });
  function cardCtl(p) {
    const k = S.cart.get(p.id) || 0;
    return k ? `<div class="stepper"><button data-dec="${p.id}" aria-label="One less">−</button><span class="val">${k}</span><button data-inc="${p.id}" aria-label="One more">+</button></div>`
             : `<button class="add-btn" data-inc="${p.id}" aria-label="Add ${BD.esc(p.name)}">+</button>`;
  }
  function renderGrid() {
    const list = S.products.filter(p => (!cat || p.category === cat) && (!q || (p.name + " " + p.brand + " " + p.category).toLowerCase().includes(q)));
    if (!S.products.length) { $("pgrid").innerHTML = `<div class="glass card center" style="grid-column:1/-1"><p class="muted">This store hasn't added products yet.</p></div>`; return; }
    if (!list.length) { $("pgrid").innerHTML = `<div class="glass card center" style="grid-column:1/-1"><p class="muted">Nothing matches “${BD.esc(q)}”.</p></div>`; return; }
    $("pgrid").innerHTML = list.slice(0, 240).map((p, i) => `<div class="glass pcard ${S.cart.get(p.id) ? "in-cart" : ""}" data-tilt="7" data-pid="${p.id}" style="--h:${BD.hueFor(p.category)};animation-delay:${Math.min(i, 16) * .03}s">
      <div class="ph"><i class="diet-dot diet-${p.diet || "veg"}" title="${BD.esc(p.diet || "veg")}"></i>${S.pic(p.image_url, S.emoji(p.name, p.category), p.image_credit)}</div>
      <div class="nm">${BD.esc(p.name)}</div>
      <div class="meta">${BD.esc(p.brand || p.category)} · ${S.packLabel(p)}${p.stock <= 5 ? ` · <span style="color:var(--marigold)">only ${p.stock} left</span>` : ""}</div>
      <div class="foot"><span class="pr">${BD.rupees(p.price_paise)}</span>${S.info.features.aisle_finder ? `<button class="pin-btn" data-find="${p.id}" title="Where is it?" aria-label="Find ${BD.esc(p.name)} in the store">📍</button>` : ""}<span class="ctl">${cardCtl(p)}</span></div></div>`).join("");
    BD.tilt($("pgrid"));
  }
  document.addEventListener("click", e => {
    const inc = e.target.closest("[data-inc]"), dec = e.target.closest("[data-dec]");
    if (!inc && !dec) return;
    const id = Number((inc || dec).dataset.inc || (inc || dec).dataset.dec);
    const p = S.byId.get(id); if (!p) return;
    const k = Math.max(0, Math.min(Math.min(50, p.stock), (S.cart.get(id) || 0) + (inc ? 1 : -1)));
    if (inc && k === (S.cart.get(id) || 0)) BD.toast(`Only ${p.stock} of ${p.name} available`, "info");
    if (k) S.cart.set(id, k); else S.cart.delete(id);
    if (inc) flyToCart(inc, S.emoji(p.name, p.category));
    BD.buzz(); saveCart(); refreshCard(id); updateFab();
    if ($("cartSheet").classList.contains("show")) renderCart();
  });
  function refreshCard(id) {
    const el = document.querySelector(`.pcard[data-pid="${id}"]`); if (!el) return;
    el.classList.toggle("in-cart", !!S.cart.get(id)); el.querySelector(".ctl").innerHTML = cardCtl(S.byId.get(id));
  }
  function flyToCart(fromEl, emoji) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const a = fromEl.getBoundingClientRect(), b = $("cartFab").getBoundingClientRect();
    const f = document.createElement("div"); f.className = "flyer"; f.textContent = emoji;
    f.style.left = a.left + "px"; f.style.top = a.top + "px"; document.body.appendChild(f);
    requestAnimationFrame(() => { f.style.transform = `translate(${b.left + 20 - a.left}px, ${b.top - a.top}px) scale(.4) rotate(360deg)`; f.style.opacity = ".2"; });
    setTimeout(() => { f.remove(); $("cartFab").classList.remove("bump"); void $("cartFab").offsetWidth; $("cartFab").classList.add("bump"); }, 760);
  }

  // ---------- cart ----------
  const CK = "bd_cart_" + SLUG;
  function loadCart() {
    try { const raw = JSON.parse(BD.store.get(CK) || "{}"); for (const [id, k] of Object.entries(raw)) { const p = S.byId.get(Number(id)); if (p && k > 0) S.cart.set(p.id, Math.min(k, p.stock, 50)); } } catch (e) {}
  }
  function saveCart() { BD.store.set(CK, JSON.stringify(Object.fromEntries(S.cart))); }
  S.cartTotal = () => [...S.cart].reduce((s, [id, k]) => s + (S.byId.get(id) ? S.byId.get(id).price_paise * k : 0), 0);
  function updateFab() {
    const n = [...S.cart.values()].reduce((a, b) => a + b, 0);
    $("cartN").textContent = n; $("cartT").textContent = BD.rupees(S.cartTotal());
    $("cartFab").classList.toggle("show", n > 0);
  }
  $("cartFab").addEventListener("click", () => { renderCart(); S.openSheet("cartSheet"); });
  function renderCart() {
    if (!S.cart.size) { $("cartLines").innerHTML = `<p class="muted center" style="padding:20px 0">Your cart is empty.</p>`; return; }
    $("cartLines").innerHTML = [...S.cart].map(([id, k]) => { const p = S.byId.get(id); return `<div class="cline"><div class="th">${S.pic(p.image_url, S.emoji(p.name, p.category))}</div>
      <div><b>${BD.esc(p.name)}</b><div class="faint small">${S.packLabel(p)} · ${BD.rupees(p.price_paise)} each</div></div>
      <div style="text-align:right"><div class="stepper"><button data-dec="${id}" aria-label="One less">−</button><span class="val">${k}</span><button data-inc="${id}" aria-label="One more">+</button></div><div class="mono small" style="margin-top:4px">${BD.rupees(p.price_paise * k)}</div></div></div>`; }).join("")
      + `<div class="total-row"><span class="muted">Total</span><b>${BD.rupees(S.cartTotal())}</b></div>
         <button class="btn lg block" id="checkout" style="margin-top:12px" ${S.info.features.online_payment ? "" : "disabled"}>Checkout →</button>
         ${S.info.features.online_payment ? "" : `<p class="faint small center">Online payment isn't set up for this store yet.</p>`}`;
  }
  document.addEventListener("click", e => { if (e.target.closest("#checkout")) S.checkout([...S.cart].map(([id, k]) => ({ product_id: id, packs: k })), S.cartTotal(), "direct"); });

  // ---------- checkout (shared with the planner) ----------
  let pending = null;
  S.checkout = function (items, totalPaise, source, plan) {
    pending = { items, source, plan };
    $("payTotal").textContent = BD.rupees(totalPaise); $("payErr").textContent = "";
    $("pPhone").value = BD.store.get("bd_phone") || ""; $("pName").value = BD.store.get("bd_name") || "";
    S.openSheet("paySheet"); setTimeout(() => $("pPhone").focus(), 400);
  };
  $("payGo").addEventListener("click", async () => {
    const phone = $("pPhone").value.replace(/\D/g, "");
    if (!/^[6-9]\d{9}$/.test(phone)) { $("payErr").textContent = "Enter a valid 10-digit mobile number"; return; }
    BD.busy($("payGo"), true, "Opening payment…");
    try {
      const r = await BD.api(API + "/checkout", { body: { items: pending.items, phone, name: $("pName").value.trim(), source: pending.source, plan: pending.plan } });
      BD.store.set("bd_phone", phone); BD.store.set("bd_name", $("pName").value.trim());
      BD.store.set("bd_last_order_" + SLUG, JSON.stringify({ id: r.order_id, t: r.token }));
      if (pending.source === "direct") { S.cart.clear(); saveCart(); }
      location.href = r.link_url;
    } catch (x) {
      $("payErr").textContent = x.message; BD.busy($("payGo"), false);
      if (x.status === 409) { try { S.info = await BD.api(API); S.products = S.info.products; S.byId = new Map(S.products.map(p => [p.id, p])); } catch (e) {} }
    }
  });

  // ---------- voice add (shown before anything goes in the cart) ----------
  let rec = null;
  $("micFab").addEventListener("click", () => { $("vOut").innerHTML = ""; $("vHeard").textContent = BD.canRecord ? "Tap the mic and speak" : "Type what you need below (the mic needs HTTPS)."; S.openSheet("voiceSheet"); });
  S.onClose = () => { if (rec && rec.recording) rec.stop(); $("vOrb").classList.remove("rec", "think"); };
  $("vOrb").addEventListener("click", async () => {
    if (!BD.canRecord) { $("vText").focus(); return; }
    if (rec && rec.recording) { rec.stop(); return; }
    rec = BD.recorder(l => $("vOrb").style.setProperty("--lvl", l.toFixed(3)));
    $("vOrb").classList.add("rec"); $("vHeard").textContent = "Listening… tap again when done";
    let blob;
    try { blob = await rec.start(15000); } catch (e) { $("vOrb").classList.remove("rec"); $("vHeard").textContent = "Microphone blocked. Type instead."; return; }
    $("vOrb").classList.remove("rec");
    if (!blob) return;
    const fd = new FormData(); fd.append("audio", blob, "voice.wav"); sendVoice(fd);
  });
  $("vForm").addEventListener("submit", e => { e.preventDefault(); const t = $("vText").value.trim(); if (!t) return; const fd = new FormData(); fd.append("text", t); sendVoice(fd); });
  async function sendVoice(fd) {
    $("vOrb").classList.add("think"); $("vHeard").textContent = "Finding it in the store…"; $("vOut").innerHTML = "";
    try {
      const r = await S.timed(BD.api(API + "/voice", { form: fd }));
      $("vHeard").textContent = r.transcript ? `“${r.transcript}”` : "";
      if (r.reply_audio) BD.play(r.reply_audio);
      if (!r.lines.length) { $("vOut").innerHTML = `<div class="notice">${BD.esc(r.reply_text)}</div>`; return; }
      $("vOut").innerHTML = `<div class="glass" style="padding:6px 14px;border-radius:16px">${r.lines.map(l => `<div class="cline"><div class="th">${S.pic(l.image_url, S.emoji(l.name))}</div>
        <div><b>${l.packs} × ${BD.esc(l.name)}</b><div class="faint small">${BD.rupees(l.unit_price_paise)} each</div></div><span class="mono">${BD.rupees(l.line_total_paise)}</span></div>`).join("")}
        <div class="total-row"><span class="muted">Adds</span><b>${BD.rupees(r.total_paise)}</b></div></div>
        ${r.missing.length ? `<p class="faint small" style="margin:8px 0 0">Not found: ${BD.esc(r.missing.join(", "))}</p>` : ""}
        <div class="row" style="margin-top:12px"><button class="btn grow" id="vAdd">Add to cart</button><button class="btn-ghost" data-close>Cancel</button></div>`;
      $("vAdd").onclick = () => {
        for (const l of r.lines) { const p = S.byId.get(l.product_id); if (p) S.cart.set(p.id, Math.min(p.stock, 50, (S.cart.get(p.id) || 0) + l.packs)); }
        saveCart(); updateFab(); renderGrid(); S.closeSheets(); BD.toast("Added to your cart", "ok"); BD.confetti(60);
      };
    } catch (x) { $("vOut").innerHTML = `<div class="notice bad">${BD.esc(x.message)} You can search and tap products instead.</div>`; }
    finally { $("vOrb").classList.remove("think"); }
  }

  // ---------- 3D aisle finder ----------
  function findList(q) {
    q = q.trim().toLowerCase();
    const words = q.split(/\s+/).filter(Boolean);
    const hits = !words.length ? [] : S.products.filter(p => words.every(w => (p.name + " " + p.brand + " " + p.category).toLowerCase().includes(w))).slice(0, 30);
    $("fList").innerHTML = !q ? `<p class="faint small">Try “chips”, “atta” or “ghee”.</p>` : hits.length
      ? `<p class="faint small" style="margin:10px 0 6px">${hits.length} type${hits.length === 1 ? "" : "s"} found. Pick yours:</p>` + hits.map(p => `<button class="find-row" data-pick="${p.id}"><span class="th">${S.pic(p.image_url, S.emoji(p.name, p.category))}</span>
          <span class="grow"><b>${BD.esc(p.name)}</b><span class="faint small" style="display:block">${BD.esc(p.brand || p.category)} · ${S.packLabel(p)} · ${BD.rupees(p.price_paise)}</span></span><span class="chip">📍 Show</span></button>`).join("")
      : `<p class="muted small" style="margin-top:10px">This store doesn't stock “${BD.esc(q)}”. Ask at the billing counter.</p>`;
  }
  let fT; $("fQ").addEventListener("input", e => { clearTimeout(fT); fT = setTimeout(() => findList(e.target.value), 120); });
  $("findBtn").onclick = () => { $("fQ").value = $("q").value; findList($("fQ").value); S.openSheet("findSheet"); setTimeout(() => $("fQ").focus(), 350); };
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-find],[data-pick]"); if (!b) return;
    e.stopPropagation(); showMap(S.byId.get(Number(b.dataset.find || b.dataset.pick)));
  });
  let map3d = null;
  async function showMap(p) {
    if (!p) return;
    S.closeSheets();
    $("mapOv").classList.remove("hidden"); document.documentElement.style.overflow = "hidden";
    $("mapCard").innerHTML = `<div class="loader-orb" style="width:50px;height:50px"><i></i><i></i><i></i><b></b></div>`;
    try { map3d = map3d || await import("/static/js/store3d.js?v=1").then(() => window.Store3D); }
    catch (e) { $("mapCard").innerHTML = `<p class="muted">The 3D map needs internet (Three.js).</p>`; return; }
    const where = map3d.open($("mapMount"), S.products, S.info.categories, p);
    $("mapCard").innerHTML = where ? `<div class="row" style="gap:12px;align-items:center"><span class="map-aisle"><small>AISLE</small>${where.aisle}</span>
        <span class="grow"><b>${BD.esc(p.name)}</b><span class="muted small" style="display:block">${BD.esc(where.category)} · ${where.side} side · bay ${where.bay + 1} · ${["bottom", "middle", "top"][where.level]} shelf</span>
        <span class="small" style="color:var(--mint)">Follow the green path from the entrance</span></span></div>
        <div class="row" style="gap:8px;margin-top:10px"><span class="pr mono">${BD.rupees(p.price_paise)}</span><span class="grow"></span><button class="btn sm" data-inc="${p.id}">Add to cart</button></div>`
      : `<p class="muted">Couldn't place this product on the map.</p>`;
  }
  $("mapClose").onclick = () => { $("mapOv").classList.add("hidden"); document.documentElement.style.overflow = ""; if (map3d) map3d.close(); };

  // ---------- order status ----------
  async function orderPage() {
    const t = BD.qs("t") || "";
    let tries = 0, o;
    const draw = () => {
      const st = o.status, paid = ["PAID", "PACKED", "DONE"].includes(st);
      const steps = [["PAID", "Paid"], ["PACKED", "Packed"], ["DONE", "Picked up"]];
      const idx = { PAID: 0, PACKED: 1, DONE: 2 }[st] ?? -1;
      $("oCard").innerHTML = `<div class="big-ic">${paid ? (st === "DONE" ? "🎉" : "🛍️") : "⏳"}</div>
        <h2 style="margin:10px 0 4px">${paid ? "Order confirmed" : "Waiting for payment"}</h2>
        <p class="muted">Order #${o.id} · ${BD.esc(S.info.store.name)}</p>
        ${paid ? `<div class="track">${steps.map(([k, l], i) => `<div class="${i <= idx ? "on" : ""}"><i></i>${l}</div>`).join("")}</div>
          <p class="muted small">${st === "PAID" ? "The store is packing your order. Show this screen at the counter." : st === "PACKED" ? "Your bag is ready at the counter!" : "Thank you for shopping!"}</p>`
        : `<p class="muted small" style="margin:12px 0">We'll confirm as soon as Cashfree tells us the payment succeeded.</p>
           ${o.link_url ? `<a class="btn" href="${BD.esc(o.link_url)}">Open payment page</a>` : `<button class="btn" id="repay">Pay again</button>`}`}
        <div class="glass" style="padding:6px 14px;border-radius:16px;margin-top:18px;text-align:left">${o.items.map(i => `<div class="cline" style="grid-template-columns:1fr auto"><span>${i.packs} × ${BD.esc(i.name)}</span><span class="mono">${BD.rupees(i.line_total_paise)}</span></div>`).join("")}
        <div class="total-row"><span class="muted">${paid ? "Paid" : "Total"}</span><b>${BD.rupees(o.total_paise)}</b></div></div>
        <a class="btn-ghost" style="margin-top:16px;display:inline-block" href="/s/${encodeURIComponent(SLUG)}#shop">Shop again</a>`;
      const rp = $("repay"); if (rp) rp.onclick = async () => { BD.busy(rp, true); try { const r = await BD.api(`${API}/orders/${ORDER_ID}/repay`, { body: { t } }); if (r.paid) return load(); location.href = r.link_url; } catch (x) { BD.toast(x.message, "bad"); BD.busy(rp, false); } };
      if (paid && !draw.celebrated) { draw.celebrated = true; BD.confetti(); BD.sound.unlock(); BD.sound.chime("paid"); }
    };
    const load = async () => {
      try { o = await BD.api(`${API}/orders/${ORDER_ID}?t=${encodeURIComponent(t)}`); draw(); }
      catch (x) { $("oCard").innerHTML = `<div class="big-ic">🔎</div><h2 style="margin:10px 0">Order not found</h2><p class="muted">${BD.esc(x.message)}</p>`; return; }
      if (o.status === "PENDING_PAYMENT" && tries++ < 40) setTimeout(load, tries < 10 ? 3000 : 8000);
      else if (o.status === "PAID" || o.status === "PACKED") setTimeout(load, 15000);
    };
    load();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
