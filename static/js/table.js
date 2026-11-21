/* Guest table page: start/join, menu + cart, voice ordering, order tracking, bill and payment. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const TOKEN = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  const KEY = "bd_t_" + TOKEN;
  let info = null, me = null, sess = null, cart = new Map(), tab = "menu", cat = "", query = "";
  let prevOrders = new Map(), prevStatus = null, busyPoll = false, menuById = new Map();
  let preview = false;  // item 1: read-only menu before the table is approved (the server also refuses orders: 409)

  // ---------------------------------------------------------------- utils
  const screens = ["sLoading", "sError", "sWelcome", "sWaiting", "sRejected", "sClosed", "sMain"];
  function show(id) { screens.forEach(s => $(s).classList.toggle("hidden", s !== id)); if (id !== "sMain") closeSheets(); BD.reveal(); }
  function guestApi(path, opts = {}) { return BD.api(path, Object.assign({}, opts, { headers: Object.assign({ "X-Guest-Token": me ? me.token : "" }, opts.headers) })); }
  function saveMe() { me ? BD.store.set(KEY, JSON.stringify(me)) : BD.store.del(KEY); }
  function loadMe() { try { return JSON.parse(BD.store.get(KEY) || "null"); } catch (e) { return null; } }
  function cartKey() { return me ? "bd_cart_" + me.sid : null; }
  function saveCart() { if (cartKey()) BD.store.set(cartKey(), JSON.stringify([...cart])); }
  function loadCart() { try { cart = new Map(JSON.parse(BD.store.get(cartKey()) || "[]").filter(([id]) => menuById.has(id))); } catch (e) { cart = new Map(); } }
  function forget() { if (cartKey()) BD.store.del(cartKey()); if (me) BD.store.set("bd_g_" + me.sid, ""); me = null; sess = null; cart = new Map(); saveMe(); }

  function openSheet(id) { $("ov").classList.add("show"); $(id).classList.add("show"); }
  function closeSheets() { $("ov").classList.remove("show"); document.querySelectorAll(".sheet.show").forEach(s => s.classList.remove("show")); stopRecording(true); }
  $("ov").onclick = closeSheets;
  document.querySelectorAll("[data-close]").forEach(b => b.onclick = closeSheets);
  addEventListener("keydown", e => { if (e.key === "Escape") closeSheets(); });

  // ---------------------------------------------------------------- boot
  async function boot() {
    try {
      info = await BD.api("/api/t/" + encodeURIComponent(TOKEN));
    } catch (x) { $("errText").textContent = x.message; return show("sError"); }
    menuById = new Map(info.menu.map(m => [m.id, m]));
    document.title = `${info.restaurant.name} · Table ${info.table.number}`;
    me = loadMe();
    if (me) { await fetchSession(); loadCart(); }
    document.querySelectorAll(".preview-btn").forEach(b => b.classList.toggle("hidden", !info_feature("menu_preview")));
    route();
    setInterval(tick, 2500);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
  }

  async function fetchSession() {
    try { sess = await guestApi("/api/session/" + me.sid); if (sess && sess.id !== me.sid) { me.sid = sess.id; saveMe(); BD.toast("Your table was joined with another table. Same order, one bill.", "info", 5000); } }
    catch (x) { if (x.status === 401 || x.status === 404) { forget(); } }
  }

  let welcomeTicks = 0;
  async function tick() {
    if (busyPoll || document.hidden) return;
    busyPoll = true;
    try {
      if (me) { await fetchSession(); route(); }
      else if (++welcomeTicks % 2 === 0) {
        const fresh = await BD.api("/api/t/" + encodeURIComponent(TOKEN)).catch(() => null);
        if (fresh) {
          const changed = fresh.active_status !== info.active_status;
          info = fresh; menuById = new Map(info.menu.map(m => [m.id, m]));
          if (changed && !$("sWelcome").classList.contains("hidden")) renderWelcome(false);
        }
      }
    } finally { busyPoll = false; }
  }

  function route() {
    if (!sess) { if (preview) return; if ($("sWelcome").classList.contains("hidden")) renderWelcome(true); prevStatus = null; return; }
    const st = sess.status;
    if (st !== prevStatus) onStatusChange(prevStatus, st);
    prevStatus = st;
    if (st === "WAITING_APPROVAL") { $("waitTable").textContent = info.table.number; if (preview) return; return show("sWaiting"); }
    if (preview) { setPreview(false); renderMenu(); }  // approved (or closed): same view, now in ordering mode
    if (st === "REJECTED") return show("sRejected");
    if (st === "CLOSED" || st === "PAID_CASH") {
      $("closedTitle").textContent = st === "PAID_CASH" ? "Paid. Thank you!" : "Thank you!";
      $("closedText").textContent = st === "PAID_CASH" ? `The cashier marked ${BD.rupees(sess.settled_paise)} as paid in cash. See you again soon.` : "This table's order is closed. See you again soon.";
      $("closedAgain").href = location.pathname;
      forget();
      return show("sClosed");
    }
    if ($("sMain").classList.contains("hidden")) { show("sMain"); renderMenu(); }
    renderMain();
  }

  function onStatusChange(from, to) {
    if (from === "WAITING_APPROVAL" && to === "OPEN") { BD.toast("You're in! Order away.", "ok"); BD.buzz([20, 40, 20]); BD.confetti(80); }
    if (to === "PAID" && from && from !== "PAID") { BD.confetti(); BD.toast("Payment confirmed. Thank you!", "ok", 5000); setTab("bill"); }
    if (to === "BILL_REQUESTED" && from === "OPEN") setTab("bill");
  }

  // ---------------------------------------------------------------- menu preview (before approval)
  function setPreview(on) {
    preview = on;
    document.body.classList.toggle("preview", on);
    $("previewBanner").classList.toggle("hidden", !on);
  }
  function openPreview() {
    setPreview(true);
    $("mRest").textContent = info.restaurant.name; $("mTable").textContent = info.table.number;
    $("mGuests").textContent = info.features.seats && info.table.seats ? `· ${info.table.seats} seats` : "";
    show("sMain"); setTab("menu"); renderMenu();
  }
  document.querySelectorAll(".preview-btn").forEach(b => {
    b.classList.toggle("hidden", !info_feature("menu_preview"));
    b.onclick = openPreview;
  });
  function info_feature(k) { return !!(info && info.features && info.features[k]); }
  $("previewBack").onclick = () => { setPreview(false); renderMenu(); if (sess) { prevStatus = null; route(); } else renderWelcome(true); };

  // ---------------------------------------------------------------- welcome / start / join
  function renderWelcome(animate) {
    const r = info.restaurant;
    $("wRest").textContent = r.name; $("wTable").textContent = info.table.number;
    if (r.wifi_name || r.wifi_password) {
      $("wifiCard").classList.remove("hidden");
      $("wifiName").textContent = r.wifi_name || "Wi-Fi";
      $("wifiPass").textContent = r.wifi_password ? "Password: " + r.wifi_password : "";
      $("wifiCopy").classList.toggle("hidden", !r.wifi_password);
    }
    const st = info.active_status;
    // Someone already started at this table -> only the join-code box makes sense.
    const joinMode = st === "OPEN" || st === "BILL_REQUESTED" || st === "PAID" || st === "WAITING_APPROVAL";
    const showJoin = joinMode || showJoinOverride;
    $("startBox").classList.toggle("hidden", showJoin);
    $("joinBox").classList.toggle("hidden", !showJoin);
    $("backStart").classList.toggle("hidden", joinMode || !showJoinOverride);
    $("joinHint").textContent = st === "WAITING_APPROVAL"
      ? "Someone at this table already asked to start. Once the cashier approves, ask them for the 4-digit code on their screen."
      : "Your table is already ordering. Ask whoever started for the 4-digit code on their screen.";
    if (animate) show("sWelcome");
  }
  let showJoinOverride = false;
  $("haveCode").onclick = () => { showJoinOverride = true; $("startBox").classList.add("hidden"); $("joinBox").classList.remove("hidden"); $("backStart").classList.remove("hidden"); boxes[0].focus(); };
  $("backStart").onclick = () => { showJoinOverride = false; $("joinBox").classList.add("hidden"); $("startBox").classList.remove("hidden"); };
  $("wifiCopy").onclick = async () => { try { await navigator.clipboard.writeText(info.restaurant.wifi_password); BD.toast("Wi-Fi password copied", "ok"); } catch (e) { BD.toast(info.restaurant.wifi_password); } };

  $("startBtn").onclick = async () => {
    const b = $("startBtn"); BD.busy(b, true, "Asking the cashier…");
    try {
      const r = await BD.api(`/api/t/${encodeURIComponent(TOKEN)}/start`, { body: { device_id: BD.deviceId() } });
      me = { sid: r.session_id, token: r.guest_token }; saveMe(); BD.store.set("bd_g_" + me.sid, me.token);
      await fetchSession(); route();
    } catch (x) {
      BD.toast(x.message, "bad", 5000);
      if (x.status === 409) { info.active_status = "OPEN"; renderWelcome(false); }
    }
    BD.busy(b, false);
  };
  $("retryStart").onclick = () => { forget(); info.active_status = null; renderWelcome(true); };

  const boxes = [...$("codeBoxes").querySelectorAll("input")];
  boxes.forEach((inp, i) => {
    inp.addEventListener("input", () => {
      inp.value = inp.value.replace(/\D/g, "").slice(-1);
      if (inp.value && i < 3) boxes[i + 1].focus();
      if (boxes.every(b => b.value)) join();
    });
    inp.addEventListener("keydown", e => { if (e.key === "Backspace" && !inp.value && i > 0) boxes[i - 1].focus(); });
    inp.addEventListener("paste", e => {
      const t = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 4);
      if (t.length) { e.preventDefault(); t.split("").forEach((c, k) => boxes[k].value = c); (boxes[t.length] || boxes[3]).focus(); if (t.length === 4) join(); }
    });
  });
  $("joinBtn").onclick = join;
  let joining = false;
  async function join() {
    const code = boxes.map(b => b.value).join("");
    if (code.length !== 4) { $("joinErr").textContent = "Enter all 4 digits"; return; }
    if (joining) return; joining = true;
    $("joinErr").textContent = ""; BD.busy($("joinBtn"), true, "Joining…");
    try {
      const r = await BD.api(`/api/t/${encodeURIComponent(TOKEN)}/join`, { body: { code, device_id: BD.deviceId() } });
      me = { sid: r.session_id, token: r.guest_token }; saveMe(); BD.store.set("bd_g_" + me.sid, me.token);
      await fetchSession(); loadCart(); BD.toast("Joined the table", "ok"); route();
    } catch (x) {
      $("joinErr").textContent = x.message;
      $("codeBoxes").classList.add("bad"); setTimeout(() => $("codeBoxes").classList.remove("bad"), 450);
      boxes.forEach(b => b.value = ""); boxes[0].focus(); BD.buzz(60);
    }
    BD.busy($("joinBtn"), false); joining = false;
  }

  // ---------------------------------------------------------------- tabs
  function setTab(t) {
    tab = t;
    document.querySelectorAll(".g-tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    $("tabMenu").classList.toggle("hidden", t !== "menu");
    $("tabOrders").classList.toggle("hidden", t !== "orders");
    $("tabBill").classList.toggle("hidden", t !== "bill");
    scrollTo({ top: 0, behavior: "smooth" });
    updateCartBar();
  }
  document.querySelectorAll(".g-tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));

  // ---------------------------------------------------------------- main render
  function renderMain() {
    $("mRest").textContent = info.restaurant.name;
    $("mTable").textContent = info.table.number;
    $("mGuests").textContent = [sess.guests > 1 ? `· ${sess.guests} phones` : "", info.features.seats && info.table.seats ? `· ${info.table.seats} seats` : ""].filter(Boolean).join(" ");
    $("mCode").textContent = sess.join_code || "····";
    if (renderMain.wasCalled && !sess.waiter_called) BD.toast("The waiter has seen your request ✓", "ok");
    renderMain.wasCalled = sess.waiter_called;
    $("waiterBtn").classList.toggle("called", sess.waiter_called);
    $("waiterBtn").title = sess.waiter_called ? "A waiter is coming" : "Call waiter";
    const active = sess.orders.filter(o => o.status !== "REJECTED" && o.status !== "SERVED").length;
    $("ordersN").textContent = active; $("ordersN").classList.toggle("hidden", !active);
    $("billN").textContent = sess.status === "PAID" ? "✓" : "₹"; $("billN").classList.toggle("hidden", !(sess.status === "BILL_REQUESTED" || sess.status === "PAID"));
    notifyOrderChanges();
    renderOrders(); renderBill(); updateCartBar();
    $("micFab").classList.toggle("hidden", !(info.features.voice_order && (sess.status === "OPEN" || (sess.status === "BILL_REQUESTED" && info.features.voice_actions))));
    $("budgetBtn").classList.toggle("hidden", !(info.features.budget_order && sess.status === "OPEN"));
  }

  function notifyOrderChanges() {
    const first = prevOrders.size === 0;
    sess.orders.forEach(o => {
      const before = prevOrders.get(o.id);
      if (!first && before && before !== o.status) {
        const msg = { ACCEPTED: "Your order was accepted 👍", PREPARING: "The kitchen is preparing your food 🔥", SERVED: "Served. Enjoy! 😋", REJECTED: "An order was declined" + (o.reject_reason ? ": " + o.reject_reason : "") }[o.status];
        if (msg) { BD.toast(msg, o.status === "REJECTED" ? "bad" : "ok", 4500); BD.buzz(30); }
      }
      prevOrders.set(o.id, o.status);
    });
  }

  // ---------------------------------------------------------------- menu
  function renderMenu() {
    const cats = [...new Set(info.menu.map(m => m.category))];
    $("cats").innerHTML = [`<button class="pill ${cat ? "" : "active"}" data-cat="">All</button>`].concat(cats.map(c => `<button class="pill ${cat === c ? "active" : ""}" data-cat="${BD.esc(c)}">${BD.esc(c)}</button>`)).join("");
    const q = query.trim().toLowerCase();
    const list = info.menu.filter(m => (!cat || m.category === cat) && (!q || (m.name + " " + m.name_local + " " + m.category).toLowerCase().includes(q)));
    if (!info.menu.length) { $("menuList").innerHTML = `<div class="glass card center" style="margin-top:20px"><p class="muted">The menu isn't ready yet. Please ask the staff.</p></div>`; return; }
    if (!list.length) { $("menuList").innerHTML = `<p class="muted center" style="margin:40px 0">Nothing matches “${BD.esc(query)}”.</p>`; return; }
    let html = "", i = 0;
    [...new Set(list.map(m => m.category))].forEach(c => {
      const group = list.filter(m => m.category === c);
      html += `<div class="cat-title">${BD.esc(c)} <small>${group.length}</small></div><div class="items">`;
      group.forEach(m => { html += itemHtml(m, i++); });
      html += `</div>`;
    });
    if (info.menu.some(m => m.photo_credit || m.nutrition)) html += `<p class="faint small center" style="margin:18px 0 0">${info.menu.some(m => m.nutrition) ? "Calories &amp; protein are approx. per serving (IFCT/NIN data). " : ""}${info.menu.some(m => m.photo_credit) ? 'Photos: Wikimedia Commons · <a href="/credits">credits</a>' : ""}</p>`;
    $("menuList").innerHTML = html;
    BD.tilt($("menuList"));
  }
  function itemHtml(m, i) {
    const qty = cart.get(m.id) || 0;
    const pic = m.photo_url ? `<img src="${BD.esc(m.photo_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'e',textContent:'${BD.foodEmoji(m.name, m.category)}'}))">` : `<span class="e">${BD.foodEmoji(m.name, m.category)}</span>`;
    const ctl = preview ? "" : qty
      ? `<div class="stepper"><button data-dec="${m.id}" aria-label="One less">−</button><span class="val">${qty}</span><button data-inc="${m.id}" aria-label="One more">+</button></div>`
      : `<button class="add-btn" data-inc="${m.id}" aria-label="Add ${BD.esc(m.name)}">+</button>`;
    return `<div class="glass item ${qty ? "in-cart" : ""}" data-tilt="5" data-item="${m.id}" style="--h:${BD.hueFor(m.category + m.name)};animation-delay:${Math.min(i, 14) * 0.03}s">
      <div class="pic">${pic}</div>
      <div style="min-width:0"><div class="nm">${BD.esc(m.name)}</div>${m.name_local ? `<div class="lc">${BD.esc(m.name_local)}</div>` : ""}<div class="pr">${BD.rupees(m.price_paise)}</div>${m.nutrition ? `<div class="nut-mini" title="Approx. per serving, computed from ${BD.esc(m.nutrition_recipe || "a standard recipe")} (IFCT/NIN data)"><span><b>${m.nutrition.kcal}</b> kcal</span><span class="p"><b>${m.nutrition.protein_g}g</b> protein</span><span><b>${m.nutrition.carbs_g}g</b> carbs</span><span><b>${m.nutrition.fat_g}g</b> fat</span><span class="faint">approx.</span></div>` : ""}</div>
      <div class="ctl">${ctl}</div></div>`;
  }
  // ---------------------------------------------------------------- 4: dish details sheet
  const SPICE = ["Not spicy", "Mild", "Medium", "Hot"];
  function macroRow(label, g, kcalPer, totalKcal, color) {
    if (g == null) return "";
    const pct = kcalPer && totalKcal ? Math.round(g * kcalPer * 100 / totalKcal) : null;
    const w = kcalPer && totalKcal ? Math.min(100, g * kcalPer * 100 / totalKcal) : Math.min(100, g * 4);
    return `<div class="mrow"><div class="row spread"><span>${label}</span><span><b>${g} g</b>${pct != null ? ` <span class="faint">· ${pct}% of kcal</span>` : ""}</span></div>
      <div class="mbar"><i style="--w:${w.toFixed(1)}%;--c:${color}"></i></div></div>`;
  }
  function openDish(id) {
    const m = menuById.get(id); if (!m) return;
    const n = m.nutrition, qty = cart.get(id) || 0;
    const canAdd = !preview && sess && sess.status === "OPEN";
    let nut;
    if (n && n.kcal != null) {
      const p = (n.protein_g || 0) * 4, c = (n.carbs_g || 0) * 4, f = (n.fat_g || 0) * 9, tot = Math.max(1, p + c + f);
      const C = 2 * Math.PI * 46, seg = (v, off, col) => `<circle r="46" cx="60" cy="60" fill="none" stroke="${col}" stroke-width="14" stroke-dasharray="${(v / tot * C).toFixed(1)} ${C.toFixed(1)}" stroke-dashoffset="${(-off / tot * C).toFixed(1)}" transform="rotate(-90 60 60)" class="seg"/>`;
      nut = `<div class="nut-panel"><svg viewBox="0 0 120 120" class="kring" aria-hidden="true"><circle r="46" cx="60" cy="60" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="14"/>${n.protein_g != null || n.carbs_g != null || n.fat_g != null ? seg(p, 0, "#2ee6a6") + seg(c, p, "#ffc145") + seg(f, p + c, "#ff6b8a") : ""}
          <text x="60" y="58" text-anchor="middle" class="kv">${n.kcal}</text><text x="60" y="76" text-anchor="middle" class="kl">kcal</text></svg>
        <div class="grow">${macroRow("Protein", n.protein_g, 4, tot, "#2ee6a6")}${macroRow("Carbs", n.carbs_g, 4, tot, "#ffc145")}${macroRow("Fat", n.fat_g, 9, tot, "#ff6b8a")}${macroRow("Fibre", n.fibre_g, 0, 0, "#4cc9f0")}</div></div>
        <p class="faint small" style="margin:8px 0 0">${m.nutrition_source === "owner" ? "Approx. per serving · entered by the restaurant" : `Approx. per serving, computed from IFCT/NIN data${m.nutrition_recipe ? ` (standard ${BD.esc(m.nutrition_recipe)} recipe)` : ""}`}</p>`;
    } else nut = `<p class="muted small">Nutrition info not available for this dish.</p>`;
    const pic = m.photo_url ? `<img src="${BD.esc(m.photo_url)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : "";
    $("dishBody").innerHTML = `<div class="dish-hero" style="--h:${BD.hueFor(m.category + m.name)}"><span class="init">${BD.esc((m.name || "?").trim()[0])}</span>${pic}</div>
      <div class="row spread" style="align-items:flex-start;gap:12px">
        <div><h2 id="dishName" style="font-size:1.6rem">${m.is_veg != null ? `<i class="vdot ${m.is_veg ? "veg" : "nonveg"}" title="${m.is_veg ? "Veg" : "Non-veg"}"></i>` : ""}${BD.esc(m.name)}</h2>${m.name_local ? `<div class="muted">${BD.esc(m.name_local)}</div>` : ""}</div>
        <b style="font-size:1.4rem" class="mono">${BD.rupees(m.price_paise)}</b></div>
      ${m.description ? `<p style="margin:10px 0 0">${BD.esc(m.description)}</p>` : ""}
      <div class="row wrap" style="gap:6px;margin:12px 0">${m.spice != null ? `<span class="chip">${"🌶️".repeat(Math.max(1, m.spice))} ${SPICE[m.spice]}</span>` : ""}${m.allergens ? `<span class="chip" style="color:#fbbf24">⚠ Contains: ${BD.esc(m.allergens)}</span>` : ""}<span class="chip">${BD.esc(m.category)}</span></div>
      <h3 style="margin:6px 0 10px;font-size:1.05rem">Nutrition</h3>${nut}
      ${canAdd ? `<button class="btn lg block" id="dishAdd" style="margin-top:16px">Add to cart · ${BD.rupees(m.price_paise)}${qty ? ` <span class="small">(${qty} in cart)</span>` : ""}</button>`
        : preview ? `<p class="notice" style="margin-top:16px">Ordering opens once the waiter confirms you're at the table.</p>` : ""}`;
    const add = $("dishAdd"); if (add) add.onclick = () => { changeQty(id, 1); closeSheets(); BD.toast(`Added ${m.name}`, "ok", 1800); };
    openSheet("dishSheet");
  }
  $("menuList").addEventListener("click", e => {
    if (!info_feature("dish_details") || e.target.closest("[data-inc],[data-dec],.ctl")) return;
    const card = e.target.closest("[data-item]"); if (card) openDish(Number(card.dataset.item));
  });

  function refreshItem(id) {
    const el = document.querySelector(`[data-item="${id}"]`); if (!el) return;
    const m = menuById.get(id), qty = cart.get(id) || 0;
    el.classList.toggle("in-cart", !!qty);
    el.querySelector(".ctl").innerHTML = qty
      ? `<div class="stepper"><button data-dec="${id}" aria-label="One less">−</button><span class="val bump">${qty}</span><button data-inc="${id}" aria-label="One more">+</button></div>`
      : `<button class="add-btn" data-inc="${id}" aria-label="Add ${BD.esc(m.name)}">+</button>`;
  }
  $("cats").addEventListener("click", e => { const p = e.target.closest("[data-cat]"); if (!p) return; cat = p.dataset.cat; renderMenu(); });
  let searchT; $("search").addEventListener("input", e => { clearTimeout(searchT); searchT = setTimeout(() => { query = e.target.value; renderMenu(); }, 120); });

  function changeQty(id, delta) {
    if (preview) { BD.toast("Ordering opens once the waiter confirms you're at the table.", "info"); return; }
    if (!sess || sess.status !== "OPEN") { BD.toast(sess && sess.status === "BILL_REQUESTED" ? "The bill is requested, so ordering is closed." : "Ordering is closed.", "bad"); return; }
    const q = Math.max(0, Math.min(20, (cart.get(id) || 0) + delta));
    q ? cart.set(id, q) : cart.delete(id);
    saveCart(); refreshItem(id); updateCartBar(); renderCartSheet(); BD.buzz(8);
    if (delta > 0) { const c = $("cartCount"); c.classList.remove("bump"); void c.offsetWidth; c.classList.add("bump"); }
  }
  document.addEventListener("click", e => {
    const inc = e.target.closest("[data-inc]"), dec = e.target.closest("[data-dec]");
    if (inc) changeQty(Number(inc.dataset.inc), 1);
    if (dec) changeQty(Number(dec.dataset.dec), -1);
  });

  // ---------------------------------------------------------------- cart
  function cartTotals() { let n = 0, sum = 0; cart.forEach((q, id) => { const m = menuById.get(id); if (m) { n += q; sum += q * m.price_paise; } }); return { n, sum }; }
  function updateCartBar() {
    const { n, sum } = cartTotals();
    $("cartCount").textContent = n; $("cartTotal").textContent = BD.rupees(sum);
    const showBar = n > 0 && sess && sess.status === "OPEN" && !preview;
    $("cartBar").classList.toggle("show", showBar);
    $("micFab").classList.toggle("low", !showBar);
  }
  function renderCartSheet() {
    const { sum } = cartTotals();
    $("cartSum").textContent = BD.rupees(sum);
    if (!cart.size) { $("cartItems").innerHTML = `<p class="muted center">Your cart is empty.</p>`; $("placeBtn").disabled = true; return; }
    $("placeBtn").disabled = false;
    $("cartItems").innerHTML = [...cart].map(([id, q]) => { const m = menuById.get(id); return m ? `<div class="cart-line"><span class="e">${BD.foodEmoji(m.name, m.category)}</span>
      <div><div style="font-weight:700">${BD.esc(m.name)}</div><div class="muted small">${BD.rupees(m.price_paise)} × ${q} = <b>${BD.rupees(m.price_paise * q)}</b></div></div>
      <div class="stepper"><button data-dec="${id}" aria-label="One less">−</button><span class="val">${q}</span><button data-inc="${id}" aria-label="One more">+</button></div></div>` : ""; }).join("");
  }
  $("cartOpen").onclick = () => { renderCartSheet(); openSheet("cartSheet"); };
  $("placeBtn").onclick = async () => {
    const items = [...cart].map(([menu_item_id, qty]) => ({ menu_item_id, qty }));
    if (!items.length) return;
    const b = $("placeBtn"); BD.busy(b, true, "Sending to the kitchen…");
    try {
      const r = await guestApi(`/api/session/${me.sid}/orders`, { body: { items } });
      cart.clear(); saveCart(); sess = r.session; prevOrders.set(r.order_id, "PENDING");
      closeSheets(); renderMenu(); renderMain(); setTab("orders");
      BD.toast("Order sent! The cashier will confirm it.", "ok"); BD.buzz([15, 30, 15]);
    } catch (x) { BD.toast(x.message, "bad", 5000); if (x.status === 400) { info = await BD.api("/api/t/" + encodeURIComponent(TOKEN)); menuById = new Map(info.menu.map(m => [m.id, m])); loadCart(); renderMenu(); renderCartSheet(); } }
    BD.busy(b, false);
  };

  // ---------------------------------------------------------------- orders
  const STEPS = ["PENDING", "ACCEPTED", "PREPARING", "SERVED"];
  function renderOrders() {
    if (!sess.orders.length) { setHtml("tabOrders", `<div class="glass card center" style="margin-top:16px"><div style="font-size:2.4rem" class="float">🧑‍🍳</div><p class="muted">No orders yet. Pick something from the menu${info.features.voice_order ? " or tap the mic and say it" : ""}.</p><button class="btn" data-goto="menu">Open the menu</button></div>`); return; }
    const html = sess.orders.slice().reverse().map((o, i) => {
      const n = sess.orders.length - i;
      const idx = STEPS.indexOf(o.status);
      const track = o.status === "REJECTED"
        ? `<div class="notice bad" style="margin-top:12px">Declined${o.reject_reason ? ": " + BD.esc(o.reject_reason) : ""}. It's not on your bill.</div>`
        : `<div class="track" style="--p:${Math.max(0, idx) / 3}"><span class="bar"></span>${["Sent", "Accepted", "Cooking", "Served"].map((l, k) => `<div class="st ${k <= idx ? "done" : ""} ${k === idx && k < 3 ? "now" : ""}"><i>${k <= idx ? "✓" : k + 1}</i>${l}</div>`).join("")}</div>`;
      return `<div class="glass round"><div class="row spread"><strong>Round ${n}</strong><span class="faint small">${BD.ago(o.created_at)}</span></div>
        <div style="margin-top:8px">${o.items.map(it => `<div class="oi"><span>${BD.foodEmoji(it.name)} ${it.qty} × ${BD.esc(it.name)}</span><span class="mono">${BD.rupees(it.qty * it.unit_price_paise)}</span></div>`).join("")}</div>${track}</div>`;
    }).join("");
    const cooking = sess.orders.some(o => ["PENDING", "ACCEPTED", "PREPARING"].includes(o.status));
    const games = cooking ? `<button class="glass round open-games" style="width:100%;display:flex;align-items:center;gap:14px;text-align:left;cursor:pointer;color:var(--text)">
        <span style="font-size:2rem">🎮</span><span class="grow"><b>Food's cooking</b><br><span class="muted small">Play Dosa Flip, Chai Catch or Spice Match and top today's board</span></span><span>→</span></button>` : "";
    setHtml("tabOrders", games + html);
  }
  function setHtml(id, html) { const el = $(id); if (el._h !== html) { el._h = html; el.innerHTML = html; } }
  document.addEventListener("click", e => {
    const g = e.target.closest("[data-goto]"); if (g) setTab(g.dataset.goto);
    if (e.target.closest(".open-games") && BD.Games) BD.Games.open({ tableToken: TOKEN, quizEnabled: !!(info && info.features.table_quiz), roomsEnabled: !!(info && info.features.game_rooms), session: () => (me && sess && ["OPEN", "BILL_REQUESTED", "PAID", "WAITING_APPROVAL"].includes(sess.status) ? me : null) });
  });

  // ---------------------------------------------------------------- bill
  function renderBill() {
    const lines = new Map();
    sess.orders.filter(o => ["ACCEPTED", "PREPARING", "SERVED"].includes(o.status)).forEach(o => o.items.forEach(it => {
      const k = it.name + "|" + it.unit_price_paise; const l = lines.get(k) || { name: it.name, price: it.unit_price_paise, qty: 0 }; l.qty += it.qty; lines.set(k, l);
    }));
    const pending = sess.orders.filter(o => o.status === "PENDING").length;
    const when = new Date(sess.started_at || Date.now()).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
    const nItems = [...lines.values()].reduce((a, l) => a + l.qty, 0);
    const tables = [info.table.number].concat(info.table.merged || []).join(" + ");
    let html = `<div class="bill receipt"><div class="rc-head"><div class="rc-logo">${BD.logoSvg}</div><h3>${BD.esc(info.restaurant.name)}</h3>
      <div class="rc-meta"><span>Table ${tables}</span><span>Bill #${sess.id}</span><span>${when}</span></div></div><div class="rc-lines">`;
    if (!lines.size) html += `<p style="opacity:.6">Nothing on the bill yet. Only orders the cashier accepted show here.</p>`;
    lines.forEach(l => html += `<div class="ln"><span><span><b>${l.qty} ×</b> ${BD.esc(l.name)}</span><small>${BD.rupees(l.price)} each</small></span><span class="mono">${l.price ? BD.rupees(l.qty * l.price) : "FREE"}</span></div>`);
    html += `</div><div class="rc-sub"><span>${nItems} item${nItems === 1 ? "" : "s"}</span><span class="mono">${BD.rupees(sess.bill_paise)}</span></div>
      <div class="tot"><span>Total</span><b class="mono">${BD.rupees(sess.bill_paise)}</b></div>
      ${sess.status === "PAID" || sess.pay_method ? "" : `<p class="rc-note">Prices as on the menu. Pay by UPI or at the counter.</p>`}`;
    if (sess.status === "PAID") html += `<div style="margin-top:14px;text-align:center;font-weight:900;font-size:1.3rem;color:#0d8a5f;letter-spacing:.2em;border:3px solid #0d8a5f;border-radius:12px;padding:6px;transform:rotate(-4deg)">PAID ✓</div>`;
    html += `<div class="rc-edge"></div></div>`;
    if (lines.size) html += `<div class="row share-row"><button class="btn-ghost grow wa-btn" id="shareWa"><span class="wa-ic">🟢</span> Share on WhatsApp</button>${navigator.share ? `<button class="btn-ghost" id="shareAny" aria-label="Share">↗ Share</button>` : ""}</div>`;
    if (pending) html += `<div class="notice" style="margin-top:26px">${pending} order${pending > 1 ? "s are" : " is"} waiting for the cashier. ${pending > 1 ? "They'll" : "It'll"} appear on the bill once accepted.</div>`;

    html += `<div class="pay-box">`;
    if (sess.status === "OPEN") {
      html += `<button class="btn lg block violet" id="reqBill" ${sess.bill_paise > 0 && !pending ? "" : "disabled"}>Request the bill</button><p class="faint small center" style="margin-top:10px">After this, no new orders can be added.</p>`;
    } else if (sess.status === "BILL_REQUESTED" && sess.split && info.features.split_bill) {
      html += `<div id="splitBox" class="split-box"><div class="loader-orb" style="width:60px;height:60px"><i></i><i></i><i></i><b></b></div></div>`;
    } else if (sess.status === "BILL_REQUESTED") {
      if (info.features.split_bill && info.features.online_payment) {
        html += `<div class="glass split-offer"><div class="row" style="gap:12px"><span class="split-ic">➗</span><div class="grow"><b>Split the bill</b><div class="muted small">Each person pays their part by UPI on their own phone</div></div></div>
          <div class="row wrap" style="gap:10px;margin-top:12px">
            <div class="stepper"><button type="button" data-splitn="-1" aria-label="Fewer people">−</button><span class="val" id="splitN">${Math.max(2, Math.min(20, sess.guests || 2))}</span><button type="button" data-splitn="1" aria-label="More people">+</button></div>
            <button class="btn sm cool grow" id="splitEqual">Split equally</button>
            ${sess.guests > 1 ? `<button class="btn-ghost sm grow" id="splitItems">Pay for my items</button>` : ""}
          </div></div>`;
      }
      if (info.features.online_payment) {
        const phone = BD.store.get("bd_phone") || "";
        html += `<h3 style="margin-bottom:6px">Pay by UPI</h3><p class="muted small" style="margin:0 0 12px">Cashfree needs a phone number for the receipt.</p>
          <form id="payForm" class="stack" novalidate><input class="input" id="payPhone" type="tel" inputmode="numeric" autocomplete="tel" placeholder="10-digit mobile number" value="${BD.esc(phone)}" maxlength="14">
          <button class="btn lg block mint" id="payBtn">Pay ${BD.rupees(sess.bill_paise)} →</button></form>
          <button class="btn-ghost block" id="checkPay" style="margin-top:10px">I've paid · check status</button>
          <p class="faint small center" style="margin-top:10px">Or pay at the counter in cash. The cashier will close the table.</p>`;
      } else {
        html += `<div class="glass card center"><div style="font-size:2rem">💵</div><p style="margin:8px 0 0"><b>Please pay ${BD.rupees(sess.bill_paise)} at the counter.</b></p><p class="muted small">The cashier will mark your table as paid.</p></div>`;
      }
    } else if (sess.status === "PAID") {
      html += `<div class="glass card center"><div class="thanks-orb" style="width:80px;height:80px;font-size:2.2rem">✓</div><h3 style="margin:14px 0 4px">Paid. Thank you!</h3><p class="muted small">Payment confirmed by Cashfree. You can leave whenever you like.</p></div>`;
    }
    html += `</div>`;
    setHtml("tabBill", html);
    const billText = () => {
      const out = [`🧾 *${info.restaurant.name}*`, `Table ${tables} · Bill #${sess.id}`, when, ""];
      lines.forEach(l => out.push(`${l.qty} × ${l.name} — ${l.price ? BD.rupees(l.qty * l.price) : "FREE"}`));
      out.push("", `*Total: ${BD.rupees(sess.bill_paise)}*`);
      if (sess.status === "PAID") out.push("✅ Paid by UPI");
      out.push("", "Ordered with Bolo Dukaan");
      return out.join("\n");
    };
    const wa = $("shareWa"); if (wa) wa.onclick = () => window.open("https://wa.me/?text=" + encodeURIComponent(billText()), "_blank", "noopener");
    const sh = $("shareAny"); if (sh) sh.onclick = () => navigator.share({ title: `${info.restaurant.name} bill`, text: billText() }).catch(() => {});
    wireBill();
    if ($("splitBox")) loadSplit();
  }

  // ---------------------------------------------------------------- split the bill
  let splitLoading = false, splitPicking = false;
  async function loadSplit() {
    if (splitLoading || splitPicking) return;
    splitLoading = true;
    try { drawSplit(await guestApi(`/api/session/${me.sid}/split`)); }
    catch (x) { const b = $("splitBox"); if (b) b.innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; }
    splitLoading = false;
  }
  function drawSplit(v) {
    const box = $("splitBox"); if (!box) return;
    const phone = BD.store.get("bd_phone") || "";
    const sum = v.summary || { paid: 0, total: v.shares.length, pending_paise: 0 };
    const html = `<div class="row spread"><h3>Split bill</h3><span class="chip">${sum.paid} of ${sum.total} paid</span></div>
      <div class="split-bar"><i style="width:${sum.total ? Math.round(sum.paid / sum.total * 100) : 0}%"></i></div>
      <input class="input" id="sharePhone" type="tel" inputmode="numeric" placeholder="Your 10-digit mobile (for the UPI receipt)" value="${BD.esc(phone)}" maxlength="14" style="margin:12px 0">
      <div class="shares">${v.shares.map((x, i) => {
        const done = ["PAID", "CASH", "ZERO"].includes(x.status);
        return `<div class="share-card ${x.mine ? "mine" : ""} ${done ? "done" : ""}" style="animation-delay:${i * 0.06}s">
          <div class="share-flip"><div class="grow"><b>${BD.esc(x.label)}</b><div class="mono share-amt">${BD.rupees(x.amount_paise)}</div></div>
          ${done ? `<span class="share-paid">✓ ${x.status === "CASH" ? "cash" : x.status === "ZERO" ? "nothing due" : "paid"}</span>` : `<button class="btn sm mint" data-sharepay="${x.id}">Pay ${BD.rupees(x.amount_paise)}</button>`}</div></div>`;
      }).join("")}</div>
      ${sum.pending_paise ? `<p class="faint small center" style="margin-top:8px">${BD.rupees(sum.pending_paise)} still to pay. The table is marked paid when every share is paid.</p>` : ""}
      <div class="row" style="margin-top:10px">${v.can_change ? `<button class="btn-ghost sm" id="splitUndo">Undo split</button>` : ""}<button class="btn-ghost sm" id="splitCheck">Check payments</button></div>`;
    if (box._h !== html) { box._h = html; box.innerHTML = html; }
    box.querySelectorAll("[data-sharepay]").forEach(b => b.onclick = async () => {
      const ph = $("sharePhone").value.replace(/\D/g, "").replace(/^91(?=\d{10}$)/, "");
      if (!/^[6-9]\d{9}$/.test(ph)) { BD.toast("Enter a valid 10-digit mobile number first", "bad"); $("sharePhone").focus(); return; }
      BD.store.set("bd_phone", ph); BD.busy(b, true, "Opening UPI…");
      try { const r = await guestApi(`/api/session/${me.sid}/shares/${b.dataset.sharepay}/pay`, { body: { phone: ph } }); BD.store.set("bd_g_" + me.sid, me.token); location.href = r.link_url; }
      catch (x) { BD.toast(x.message, "bad", 5000); BD.busy(b, false); }
    });
    if ($("splitUndo")) $("splitUndo").onclick = async () => {
      try { await guestApi(`/api/session/${me.sid}/split/cancel`, { method: "POST", body: {} }); await fetchSession(); renderMain(); BD.toast("Split undone", "ok"); }
      catch (x) { BD.toast(x.message, "bad"); }
    };
    $("splitCheck").onclick = async () => { await checkPay(); loadSplit(); };
  }
  async function createSplit(body) {
    try {
      await guestApi(`/api/session/${me.sid}/split`, { body });
      await fetchSession(); renderMain(); BD.toast("Bill split. Everyone can pay their share now.", "ok"); BD.buzz([10, 30, 10]);
    } catch (x) { BD.toast(x.message, "bad", 5000); }
  }
  document.addEventListener("click", async e => {
    const step = e.target.closest("[data-splitn]");
    if (step) { const el = $("splitN"); el.textContent = Math.max(2, Math.min(20, Number(el.textContent) + Number(step.dataset.splitn))); return; }
    if (e.target.closest("#splitEqual")) return createSplit({ mode: "equal", n: Number($("splitN").textContent) });
    if (e.target.closest("#splitItems")) {
      // let the guest tick items to share equally, then split by who ordered what
      splitPicking = true;
      let v; try { v = await guestApi(`/api/session/${me.sid}/split`); } catch (x) { splitPicking = false; return BD.toast(x.message, "bad"); }
      const offer = document.querySelector(".split-offer");
      offer.innerHTML = `<b>Tick anything you all shared</b><p class="muted small" style="margin:4px 0 10px">Ticked items are split equally. The rest is paid by whoever ordered it.</p>
        ${v.lines.map(l => `<label class="share-line"><input type="checkbox" value="${l.id}"><span class="grow">${l.qty} × ${BD.esc(l.name)}${l.mine ? ' <span class="chip" style="padding:2px 8px">yours</span>' : ""}</span><b class="mono">${BD.rupees(l.amount_paise)}</b></label>`).join("")}
        <div class="row" style="margin-top:12px"><button class="btn sm cool grow" id="splitItemsGo">Split by items</button><button class="btn-ghost sm" id="splitItemsBack">Back</button></div>`;
      $("splitItemsGo").onclick = async () => { const ids = [...offer.querySelectorAll("input:checked")].map(i => Number(i.value)); splitPicking = false; await createSplit({ mode: "items", shared_item_ids: ids }); };
      $("splitItemsBack").onclick = () => { splitPicking = false; $("tabBill")._h = ""; renderBill(); };
    }
  });
  function wireBill() {
    const rb = $("reqBill");
    if (rb && !rb._w) { rb._w = 1; rb.onclick = requestBill; }
    const pf = $("payForm");
    if (pf && !pf._w) { pf._w = 1; pf.onsubmit = pay; }
    const cp = $("checkPay");
    if (cp && !cp._w) { cp._w = 1; cp.onclick = checkPay; }
  }
  async function requestBill() {
    if (!confirm("Request the bill now? You won't be able to add more orders.")) return;
    const b = $("reqBill"); if (b) BD.busy(b, true, "Requesting…");
    try { const r = await guestApi(`/api/session/${me.sid}/request-bill`, { method: "POST", body: {} }); sess = r.session; prevStatus = "BILL_REQUESTED"; renderMain(); setTab("bill"); BD.toast("Bill requested", "ok"); }
    catch (x) { BD.toast(x.message, "bad", 5000); if (b) BD.busy(b, false); }
  }
  async function pay(e) {
    e.preventDefault();
    const phone = $("payPhone").value.replace(/\D/g, "").replace(/^91(?=\d{10}$)/, "");
    if (!/^[6-9]\d{9}$/.test(phone)) { BD.toast("Please enter a valid 10-digit mobile number", "bad"); $("payPhone").focus(); return; }
    BD.store.set("bd_phone", phone);
    const b = $("payBtn"); BD.busy(b, true, "Opening UPI…");
    try {
      const r = await guestApi(`/api/session/${me.sid}/pay`, { body: { phone } });
      BD.store.set("bd_g_" + me.sid, me.token);
      location.href = r.link_url;
    } catch (x) { BD.toast(x.message, "bad", 6000); BD.busy(b, false); }
  }
  async function checkPay() {
    const b = $("checkPay"); BD.busy(b, true, "Checking with Cashfree…");
    try { sess = await guestApi(`/api/session/${me.sid}/payment-status`); route(); if (sess.status !== "PAID") BD.toast("Not paid yet. If you just paid, wait a few seconds.", "info"); }
    catch (x) { BD.toast(x.message, "bad"); }
    BD.busy(b, false);
  }

  // ---------------------------------------------------------------- waiter & code
  $("waiterBtn").onclick = callWaiter;
  // Call waiter: pick what you need (the kitchen hears it in Kannada), see that it's on the way, cancel if not needed.
  const REASONS = [["Water", "💧"], ["Cutlery", "🍴"], ["Clean the table", "🧹"], ["Help to order", "📝"], ["Extra chutney / sambar", "🥣"], ["", "🙋", "Something else"]];
  function renderWaiterSheet() {
    const c = sess.waiter_call;
    $("wsBody").innerHTML = c
      ? `<div class="ws-wait"><div class="ws-bell">🔔</div><h3 style="margin:12px 0 4px">A waiter is on the way</h3>
          <p class="muted">${c.reason ? `You asked for: <b>${BD.esc(c.reason)}</b> · ` : ""}${BD.ago(c.created_at)}</p>
          <div class="row" style="justify-content:center;margin-top:14px;gap:8px"><button class="btn-ghost" id="wsCancel">Don't need it any more</button><button class="btn" data-close>OK</button></div></div>`
      : `<div class="ws-grid">${REASONS.map(([r, ic, label]) => `<button class="ws-opt" data-reason="${BD.esc(r)}"><span>${ic}</span>${BD.esc(label || r)}</button>`).join("")}</div>
         <form class="row" id="wsForm" style="gap:8px;margin-top:12px"><input class="input grow" id="wsText" maxlength="100" placeholder="Or type it (e.g. baby chair)"><button class="btn">Call</button></form>`;
    const cancel = $("wsCancel");
    if (cancel) cancel.onclick = async () => { try { await guestApi(`/api/session/${me.sid}/call-waiter/cancel`, { body: {} }); sess.waiter_called = false; sess.waiter_call = null; renderMain(); closeSheets(); BD.toast("Okay, cancelled", "ok"); } catch (x) { BD.toast(x.message, "bad"); } };
    const form = $("wsForm");
    if (form) form.onsubmit = e => { e.preventDefault(); sendCall($("wsText").value.trim() || ""); };
  }
  $("wsBody").addEventListener("click", e => { const b = e.target.closest("[data-reason]"); if (b) sendCall(b.dataset.reason); });
  async function sendCall(reason) {
    try {
      await guestApi(`/api/session/${me.sid}/call-waiter`, { body: { reason } });
      sess.waiter_called = true; sess.waiter_call = { reason, created_at: new Date().toISOString() };
      renderMain(); renderWaiterSheet(); BD.buzz([20, 40, 20]);
    } catch (x) { BD.toast(x.message, "bad"); }
  }
  function callWaiter() { renderWaiterSheet(); openSheet("waiterSheet"); }
  $("codeChip").onclick = async () => {
    if (!sess || !sess.join_code) return;
    const text = `Join our table at ${info.restaurant.name}: scan the QR on table ${info.table.number} and enter code ${sess.join_code}`;
    try { if (navigator.share) await navigator.share({ text, url: location.href }); else { await navigator.clipboard.writeText(`${text}\n${location.href}`); BD.toast("Copied. Send it to your friends", "ok"); } }
    catch (e) { BD.toast(`Code: ${sess.join_code}`); }
  };

  // ---------------------------------------------------------------- voice
  const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder && window.isSecureContext);
  let rec = null, stream = null, chunks = [], meterRAF = 0, autoStop = 0, cancelled = false, thinking = false;
  $("micFab").onclick = () => {
    $("vResult").innerHTML = ""; $("vText").value = "";
    setVState("idle");
    if (!canRecord) { $("vOrb").classList.add("hidden"); $("vState").textContent = window.isSecureContext ? "This browser can't record. Type your order below." : "Voice needs the HTTPS link (ngrok). Type your order below."; }
    if (!info.features.budget_order) $("vHint").textContent = "Try “2 masala dosa and 1 filter coffee” or “ಎರಡು ಇಡ್ಲಿ ವಡೆ”.";
    openSheet("voiceSheet");
  };
  function setVState(s, text) {
    const orb = $("vOrb");
    orb.classList.toggle("rec", s === "rec"); orb.classList.toggle("think", s === "think");
    $("vState").textContent = text || { idle: "Hold to talk (or tap)", rec: "Listening… let go when done", think: "Understanding…" }[s] || "";
    orb.setAttribute("aria-label", s === "rec" ? "Stop recording" : "Start recording");
  }
  // Hold to record, release to send. A quick tap also works: tap to start, tap again to send.
  let pressAt = 0, startedByThisPress = false;
  $("vOrb").addEventListener("pointerdown", e => {
    e.preventDefault();
    if (thinking) return;
    if (rec && rec.state === "recording") { stopRecording(false); startedByThisPress = false; return; }
    pressAt = Date.now(); startedByThisPress = true; startRecording();
  });
  const release = () => { if (startedByThisPress && Date.now() - pressAt > 450 && rec && rec.state === "recording") stopRecording(false); startedByThisPress = false; };
  $("vOrb").addEventListener("pointerup", release);
  $("vOrb").addEventListener("pointerleave", release);
  $("vOrb").addEventListener("contextmenu", e => e.preventDefault());
  async function startRecording() {
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } }); }
    catch (e) { setVState("idle", "Microphone blocked. Allow it in the browser, or type below."); return; }
    chunks = []; cancelled = false;
    rec = new MediaRecorder(stream);
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = onRecorded;
    rec.start(250);
    setVState("rec"); BD.buzz(15);
    try {
      const actx = new (window.AudioContext || window.webkitAudioContext)(), src = actx.createMediaStreamSource(stream), an = actx.createAnalyser();
      an.fftSize = 512; src.connect(an); const buf = new Uint8Array(an.fftSize);
      const loop = () => { an.getByteTimeDomainData(buf); let s = 0; for (const v of buf) s += ((v - 128) / 128) ** 2; $("vOrb").style.setProperty("--lvl", Math.min(1, Math.sqrt(s / buf.length) * 4).toFixed(3)); meterRAF = requestAnimationFrame(loop); };
      loop(); rec._actx = actx;
    } catch (e) {}
    autoStop = setTimeout(() => stopRecording(false), 15000);
  }
  function stopRecording(cancel) {
    clearTimeout(autoStop); cancelAnimationFrame(meterRAF); $("vOrb").style.setProperty("--lvl", 0);
    if (rec && rec.state === "recording") { cancelled = cancel; rec.stop(); }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    if (rec && rec._actx) { rec._actx.close().catch(() => {}); rec._actx = null; }
  }
  async function onRecorded() {
    if (cancelled || !chunks.length) { setVState("idle"); return; }
    const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
    setVState("think"); thinking = true;
    try {
      const wav = await toWav(blob);
      if (wav.byteLength < 8000) { setVState("idle", "That was very short. Tap and try again."); thinking = false; return; }
      const fd = new FormData(); fd.append("audio", new Blob([wav], { type: "audio/wav" }), "voice.wav");
      showResult(await guestApi(`/api/session/${me.sid}/voice`, { form: fd }));
    } catch (x) { setVState("idle", ""); $("vResult").innerHTML = `<div class="notice bad">${BD.esc(x.message)} You can also tap dishes on the menu.</div>`; }
    thinking = false;
  }
  $("vForm").onsubmit = async e => {
    e.preventDefault();
    const text = $("vText").value.trim(); if (!text || thinking) return;
    thinking = true; setVState("think"); BD.busy($("vSend"), true);
    try { const fd = new FormData(); fd.append("text", text); showResult(await guestApi(`/api/session/${me.sid}/voice`, { form: fd })); $("vText").value = ""; }
    catch (x) { setVState("idle", ""); $("vResult").innerHTML = `<div class="notice bad">${BD.esc(x.message)} You can also tap dishes on the menu.</div>`; }
    BD.busy($("vSend"), false); thinking = false;
  };
  async function toWav(blob) {
    // Gemini reads WAV everywhere; convert whatever the browser recorded to 16 kHz mono 16-bit.
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
    return out.buffer;
  }
  function showResult(r) {
    setVState("idle", "Hold to say more");
    renderProposal($("vResult"), r, () => setVState("idle"));
  }

  // Shared by voice and "Order by budget": shows the proposed cart; nothing is ordered until "Add to order".
  let replyAudio = null;
  function renderProposal(box, r, onRetry) {
    if (replyAudio) { try { replyAudio.pause(); } catch (e) {} }
    if (r.reply_audio) { replyAudio = new Audio(r.reply_audio); replyAudio.play().catch(() => {}); }
    let lines = (r.proposed_items || []).map(l => Object.assign({}, l));
    const draw = () => {
      const total = lines.reduce((n, l) => n + l.line_total_paise, 0);
      let html = r.transcript ? `<div class="v-said"><small>You said</small>${BD.esc(r.transcript)}</div>` : "";
      if (r.reply_text) html += `<p class="v-reply">${BD.esc(r.reply_text)}</p>`;
      if (r.ok && lines.length && (r.intent === "add_items" || r.intent === "budget_order")) {
        html += `<div class="glass" style="padding:6px 14px;border-radius:16px">${lines.map(l => `<div class="cart-line" style="grid-template-columns:34px 1fr auto"><span class="e" style="font-size:1.3rem">${BD.foodEmoji(l.name)}</span><div><b>${l.qty} × ${BD.esc(l.name)}</b>${l.name_local ? `<div class="muted small">${BD.esc(l.name_local)}</div>` : ""}<div class="faint small">${BD.rupees(l.unit_price_paise)} each</div></div><span class="mono">${BD.rupees(l.line_total_paise)}</span></div>`).join("")}
          <div class="row spread" style="padding:10px 0"><span class="muted">${r.budget_paise ? `Total (budget ${BD.rupees(r.budget_paise)})` : "Total"}</span><b>${BD.rupees(total)}</b></div></div>`;
        if (r.suggestion && !lines.some(l => l.menu_item_id === r.suggestion.menu_item_id)) {
          html += `<div class="notice" style="margin-top:10px">${BD.esc(r.suggestion.text)} <button class="btn sm" data-sugg style="margin-left:6px">Add suggestion</button></div>`;
        }
        if ((r.not_found || []).length) html += `<p class="faint small" style="margin:8px 0 0">Not on the menu: ${BD.esc(r.not_found.join(", "))}</p>`;
        if ((r.unavailable || []).length) html += `<p class="faint small" style="margin:4px 0 0">Not available today: ${BD.esc(r.unavailable.join(", "))}</p>`;
        html += `<div class="row" style="margin-top:12px"><button class="btn mint grow" data-add>Add to order · ${BD.rupees(total)}</button><button class="btn-ghost" data-retry>Try again</button></div>`;
      } else if (r.action) {
        // the reply above already says what happened (or why it couldn't)
      } else if (r.min_budget_paise) {
        html += `<div class="notice">Try a budget of at least ${BD.rupees(r.min_budget_paise)}.</div>`;
      } else if (!r.ok) {
        html += `<div class="notice">You can also tap dishes on the menu.</div><div class="row" style="margin-top:10px"><button class="btn-ghost" data-retry>Try again</button></div>`;
      }
      box.innerHTML = html;
      const add = box.querySelector("[data-add]"), retry = box.querySelector("[data-retry]"), sugg = box.querySelector("[data-sugg]");
      if (sugg) sugg.onclick = () => { lines.push(Object.assign({}, r.suggestion)); r.suggestion = null; draw(); };
      if (retry) retry.onclick = () => { box.innerHTML = ""; if (onRetry) onRetry(); };
      if (add) add.onclick = async () => {
        BD.busy(add, true, "Sending to the kitchen…");
        try {  // the normal order route: the cashier still accepts it as usual
          const res = await guestApi(`/api/session/${me.sid}/orders`, { body: { items: lines.map(l => ({ menu_item_id: l.menu_item_id, qty: Math.min(20, l.qty) })) } });
          sess = res.session; prevOrders.set(res.order_id, "PENDING");
          closeSheets(); renderMain(); setTab("orders");
          BD.toast("Order sent! The cashier will confirm it.", "ok"); BD.buzz([15, 30, 15]);
        } catch (x) { BD.toast(x.message, "bad", 5000); BD.busy(add, false); }
      };
    };
    draw();
    if (r.action && r.action.ok) {  // voice "bill" / "waiter" already happened, just like the buttons
      fetchSession().then(() => { renderMain(); if (r.action.type === "bill" || r.action.type === "split") setTimeout(() => { closeSheets(); setTab("bill"); }, 1800); });
    }
  }

  // "Order by budget": no AI, the server builds the basket from real prices.
  $("budgetBtn").onclick = () => { $("bResult").innerHTML = ""; openSheet("budgetSheet"); };
  $("bForm").onsubmit = async e => {
    e.preventDefault();
    const btn = $("bGo"); BD.busy(btn, true, "Building…");
    try {
      const r = await guestApi(`/api/session/${me.sid}/budget`, { body: { budget_rupees: Number($("bBudget").value), people: Number($("bPeople").value), meal: $("bMeal").value } });
      renderProposal($("bResult"), r);
    } catch (x) { $("bResult").innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; }
    BD.busy(btn, false);
  };

  boot();
})();
