/* Owner store page: overview (A1 sales + QR), pick-and-pack orders (with Kannada alerts), products (form, CSV, photo, demo). */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  let info = null, products = [], orders = [], orderFilter = "open", ingredients = [];
  const picked = new Set(JSON.parse(BD.store.get("bd_picked") || "[]"));
  const emoji = (n, c) => BD.groceryEmoji(n, c);
  const packLabel = p => p.pack_unit === "g" && p.pack_size >= 1000 ? p.pack_size / 1000 + " kg" : p.pack_unit === "ml" && p.pack_size >= 1000 ? p.pack_size / 1000 + " L" : p.pack_size + " " + p.pack_unit;

  async function boot() {
    $("mark").innerHTML = BD.logoSvg;
    $("logout").onclick = async e => { e.preventDefault(); try { await BD.api("/api/owner/logout", { method: "POST" }); } catch (_) {} location.href = "/owner/login"; };
    try { await BD.requireOwner(); info = await BD.api("/api/store/info"); }
    catch (x) { if (x.status === 409) { location.href = "/dashboard"; return; } BD.toast(x.message, "bad"); return; }
    $("sName").textContent = info.store.name; document.title = info.store.name + " · Store";
    $("openShop").href = info.shop_url; $("link").value = info.shop_url;
    $("qr").src = "/api/store/qr.svg?v=" + Date.now(); $("dlQr").href = "/api/store/qr.svg";
    if (info.features.menu_photo) $("photoDrop").classList.remove("hidden");
    tick(); setInterval(tick, 30000);
    await loadProducts(); loadSummary(); loadOrders();
    setInterval(loadOrders, 5000); setInterval(loadSummary, 30000);
    BD.tilt();
  }
  function tick() { $("clock").textContent = new Date().toLocaleString("en-IN", { weekday: "short", hour: "2-digit", minute: "2-digit" }); }
  $("copy").onclick = async () => { try { await navigator.clipboard.writeText($("link").value); BD.toast("Link copied", "ok"); } catch (e) { $("link").select(); } };
  document.querySelector(".tabs").addEventListener("click", e => {
    const b = e.target.closest("[data-tab]"); if (!b) return;
    document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("show", p.id === "t-" + b.dataset.tab));
    BD.tilt();
  });
  $("soundBtn").onclick = () => { if (BD.sound.unlock()) { BD.sound.chime("start"); $("soundBtn").textContent = "🔔 Sound on"; $("soundBtn").classList.add("active"); } };

  // ---------------------------------------------------------------- overview (A1)
  function countUp(el, to, money) {
    const t0 = performance.now(), from = Number(el.dataset.v || 0); el.dataset.v = to;
    const f = v => money ? BD.rupees(v) : String(Math.round(v));
    const step = t => { const k = Math.min(1, (t - t0) / 700), e = 1 - Math.pow(1 - k, 3); el.textContent = f(from + (to - from) * e); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  async function loadSummary() {
    let s; try { s = await BD.api("/api/dashboard/summary"); } catch (e) { return; }
    if (!$("kpis").children.length) $("kpis").innerHTML = `
      <div class="glass kpi" data-tilt="6"><div class="k">Collected today</div><div class="v" id="k1">₹0</div><div class="faint small">verified UPI payments</div></div>
      <div class="glass kpi" data-tilt="6"><div class="k">Orders</div><div class="v" id="k2">0</div><div class="faint small" id="k2s"></div></div>
      <div class="glass kpi" data-tilt="6"><div class="k">Products</div><div class="v" id="k3">0</div><div class="faint small" id="k3s"></div></div>
      <div class="glass kpi" data-tilt="6"><div class="k">Top seller</div><div class="v" id="k4" style="font-size:1.1rem;margin-top:8px">—</div></div>`;
    countUp($("k1"), s.collected_paise, true); countUp($("k2"), s.bills); $("k2s").textContent = "avg " + BD.rupees(s.average_paise);
    countUp($("k3"), products.length); $("k3s").textContent = products.filter(p => p.stock <= 5).length + " low on stock";
    $("k4").innerHTML = s.top_items.length ? s.top_items.map(t => `<div>${emoji(t.name)} ${BD.esc(t.name)} <b>×${t.qty}</b></div>`).join("") : "—";
    $("bills").innerHTML = s.bill_list.length ? `<table class="table-list"><tr><th>Time</th><th>Order</th><th style="text-align:right">Amount</th></tr>${s.bill_list.map(b => `<tr><td>${BD.esc(b.time)}</td><td>${BD.esc(b.label)}</td><td class="mono" style="text-align:right">${BD.rupees(b.amount_paise)}</td></tr>`).join("")}</table>`
      : `<p class="muted">No paid orders yet today. Share your QR code to get started.</p>`;
    BD.tilt($("kpis"));
  }

  // ---------------------------------------------------------------- orders
  const seenAnn = new Set(); let firstLoad = true, speaking = false; const sayQ = [];
  async function loadOrders() {
    let r; try { r = await BD.api("/api/store/orders"); } catch (e) { return; }
    const before = new Set(orders.filter(o => o.status === "PAID").map(o => o.id));
    orders = r.orders;
    const fresh = orders.filter(o => o.status === "PAID" && !before.has(o.id));
    if (!firstLoad && fresh.length) { BD.sound.chime("paid"); BD.toast(`New paid order #${fresh[0].id} · ${BD.rupees(fresh[0].total_paise)}`, "ok", 6000); loadSummary(); }
    (r.announcements || []).forEach(a => {
      if (seenAnn.has(a.id)) return; seenAnn.add(a.id);
      if (!firstLoad && !a.claimed && BD.sound.ready) { sayQ.push(a.id); drain(); }
    });
    firstLoad = false;
    $("toPack").textContent = orders.filter(o => o.status === "PAID").length;
    drawOrders();
  }
  async function drain() {
    if (speaking || !sayQ.length) return; speaking = true;
    try { const r = await BD.api(`/api/announcements/${sayQ.shift()}/claim`, { method: "POST", body: {} }); if (r.audio) await new Promise(ok => { const a = new Audio(r.audio); a.onended = ok; a.onerror = ok; a.play().catch(ok); setTimeout(ok, 15000); }); } catch (e) {}
    speaking = false; if (sayQ.length) setTimeout(drain, 250);
  }
  document.querySelector("#t-orders .seg-o").addEventListener("click", e => { const b = e.target.closest("[data-of]"); if (!b) return; orderFilter = b.dataset.of; document.querySelectorAll("[data-of]").forEach(x => x.classList.toggle("active", x === b)); drawOrders(); });
  function drawOrders() {
    const list = orders.filter(o => orderFilter === "open" ? o.status === "PAID" : o.status === orderFilter);
    if (!list.length) { $("orders").innerHTML = `<div class="glass card center"><div class="big-ic">📦</div><p class="muted">${orderFilter === "open" ? "No orders to pack right now." : "Nothing here."}</p></div>`; return; }
    $("orders").innerHTML = list.map((o, i) => {
      const all = o.items.every((_, k) => picked.has(o.id + ":" + k));
      return `<div class="glass ocard s-${o.status} ${drawOrders.done ? "still" : ""}" style="animation-delay:${i * .04}s">
        <div class="row spread wrap"><div><b style="font-size:1.15rem">Order #${o.id}</b> <span class="faint small">${BD.esc(o.customer_name || "Customer")} · ${BD.esc(o.phone)} · ${BD.ago(o.paid_at || o.created_at)}</span>
          ${o.source === "planner" ? `<span class="chip" style="margin-left:6px">🍳 Meal plan${o.plan ? ` · ${o.plan.people} people · ${o.plan.days} days` : ""}</span>` : ""}</div>
          <b class="mono">${BD.rupees(o.total_paise)}</b></div>
        <div style="margin-top:8px">${o.items.map((it, k) => `<label class="pick ${picked.has(o.id + ":" + k) ? "done" : ""}">${o.status === "PAID" ? `<input type="checkbox" data-pick="${o.id}:${k}" ${picked.has(o.id + ":" + k) ? "checked" : ""}>` : ""}
          <span class="grow">${emoji(it.name)} <b>${it.packs} ×</b> ${BD.esc(it.name)}</span><span class="mono faint">${BD.rupees(it.line_total_paise)}</span></label>`).join("")}</div>
        <div class="row" style="margin-top:10px;justify-content:flex-end">
          ${o.status === "PAID" ? `<button class="btn mint sm" data-st="PACKED" data-oid="${o.id}" ${all ? "" : "disabled"} title="Tick every item first">✓ Mark packed</button>` : ""}
          ${o.status === "PACKED" ? `<button class="btn sm" data-st="DONE" data-oid="${o.id}">Handed over</button>` : ""}
          ${o.status === "PENDING_PAYMENT" ? `<span class="faint small">Not paid yet — don't pack.</span>` : ""}</div></div>`;
    }).join("");
    drawOrders.done = true;
  }
  $("orders").addEventListener("change", e => {
    const c = e.target.closest("[data-pick]"); if (!c) return;
    if (c.checked) picked.add(c.dataset.pick); else picked.delete(c.dataset.pick);
    BD.store.set("bd_picked", JSON.stringify([...picked].slice(-500))); BD.buzz(8); drawOrders();
  });
  $("orders").addEventListener("click", async e => {
    const b = e.target.closest("[data-st]"); if (!b) return;
    BD.busy(b, true);
    try { await BD.api(`/api/store/orders/${b.dataset.oid}/status`, { body: { status: b.dataset.st } }); if (b.dataset.st === "PACKED") BD.confetti(50); await loadOrders(); }
    catch (x) { BD.toast(x.message, "bad"); BD.busy(b, false); }
  });

  // ---------------------------------------------------------------- products
  async function loadProducts() {
    const r = await BD.api("/api/store/products"); products = r.products; ingredients = r.ingredients;
    if ($("ingSel").options.length <= 1) $("ingSel").insertAdjacentHTML("beforeend", ingredients.map(i => `<option value="${BD.esc(i.id)}">${BD.esc(i.name)} (${i.unit})</option>`).join(""));
    $("catList").innerHTML = [...new Set(products.map(p => p.category))].map(c => `<option value="${BD.esc(c)}">`).join("");
    $("demoCard").classList.toggle("hidden", products.length > 0);
    drawProducts();
  }
  let pq = ""; $("pq").addEventListener("input", e => { pq = e.target.value.toLowerCase(); drawProducts(); });
  function drawProducts() {
    const list = products.filter(p => !pq || (p.name + " " + p.brand + " " + p.category).toLowerCase().includes(pq));
    $("pCount").textContent = `· ${products.length}`;
    $("ptbody").innerHTML = list.length ? list.map(p => `<tr class="${p.stock <= 5 ? "low" : ""}" data-pid="${p.id}">
      <td><div class="th">${p.image_url ? `<img src="${BD.esc(p.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : emoji(p.name, p.category)}</div></td>
      <td><b>${BD.esc(p.name)}</b><div class="faint small">${BD.esc(p.category)} · ${packLabel(p)}</div></td>
      <td><input class="input input-sm mono" data-f="price" value="${(p.price_paise / 100).toFixed(2).replace(/\.00$/, "")}" inputmode="decimal" aria-label="Price"></td>
      <td><input class="input input-sm mono" data-f="stock" value="${p.stock}" inputmode="numeric" style="width:70px" aria-label="Stock"></td>
      <td><label class="switch"><input type="checkbox" data-f="available" ${p.available ? "checked" : ""}><span></span></label></td>
      <td><button class="btn-ghost sm" data-del="${p.id}" aria-label="Delete">🗑</button></td></tr>`).join("")
      : `<tr><td colspan="6" class="center muted" style="padding:24px">${products.length ? "No match" : "No products yet. Load the demo catalogue or add one."}</td></tr>`;
  }
  async function saveProduct(p, patch, el) {
    const body = Object.assign({}, p, patch);
    try { await BD.api(`/api/store/products/${p.id}`, { method: "PUT", body }); Object.assign(p, patch); if (el) { el.style.borderColor = "var(--mint)"; setTimeout(() => el.style.borderColor = "", 900); } }
    catch (x) { BD.toast(x.message, "bad"); drawProducts(); }
  }
  $("ptbody").addEventListener("change", e => {
    const el = e.target, tr = el.closest("[data-pid]"); if (!tr || !el.dataset.f) return;
    const p = products.find(x => x.id === Number(tr.dataset.pid));
    if (el.dataset.f === "price") { const v = Math.round(parseFloat(el.value) * 100); if (!(v >= 100)) { BD.toast("Price must be ₹1 or more", "bad"); el.value = p.price_paise / 100; return; } saveProduct(p, { price_paise: v }, el); }
    if (el.dataset.f === "stock") { const v = parseInt(el.value, 10); if (!(v >= 0)) { el.value = p.stock; return; } saveProduct(p, { stock: v }, el); }
    if (el.dataset.f === "available") saveProduct(p, { available: el.checked ? 1 : 0 });
  });
  $("ptbody").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.dataset.f) e.target.blur(); });
  $("ptbody").addEventListener("click", async e => {
    const b = e.target.closest("[data-del]"); if (!b) return;
    const p = products.find(x => x.id === Number(b.dataset.del));
    if (!confirm(`Delete ${p.name}?`)) return;
    try { await BD.api(`/api/store/products/${p.id}`, { method: "DELETE" }); products = products.filter(x => x !== p); drawProducts(); BD.toast("Deleted", "ok"); } catch (x) { BD.toast(x.message, "bad"); }
  });
  $("seed").onclick = async () => {
    BD.busy($("seed"), true, "Loading…");
    try { const r = await BD.api("/api/store/seed-demo", { body: {} }); BD.toast(`Added ${r.added} products`, "ok"); BD.confetti(); await loadProducts(); loadSummary(); }
    catch (x) { BD.toast(x.message, "bad"); BD.busy($("seed"), false); }
  };
  $("addForm").addEventListener("submit", async e => {
    e.preventDefault(); $("addErr").textContent = "";
    const d = Object.fromEntries(new FormData(e.target));
    const price = Math.round(parseFloat(d.price) * 100);
    if (!(price >= 100)) { $("addErr").textContent = "Enter a price of ₹1 or more"; return; }
    const btn = e.target.querySelector("button"); BD.busy(btn, true);
    try {
      await BD.api("/api/store/products", { body: { name: d.name, brand: d.brand, category: d.category || "Other", pack_size: d.pack_size, pack_unit: d.pack_unit, price_paise: price, stock: d.stock || 100, ingredient_id: d.ingredient_id || null } });
      e.target.reset(); BD.toast("Product added", "ok"); await loadProducts();
    } catch (x) { $("addErr").textContent = x.message; }
    BD.busy(btn, false);
  });
  function dropZone(zone, input, handler) {
    zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", e => { e.preventDefault(); zone.classList.remove("over"); if (e.dataTransfer.files[0]) handler(e.dataTransfer.files[0]); });
    input.addEventListener("change", () => { if (input.files[0]) handler(input.files[0]); input.value = ""; });
  }
  dropZone($("csvDrop"), $("csvFile"), async f => {
    const fd = new FormData(); fd.append("file", f);
    try { const r = await BD.api("/api/store/products/csv", { form: fd }); BD.toast(`Added ${r.added}${r.skipped ? `, skipped ${r.skipped} rows with missing data` : ""}`, r.added ? "ok" : "bad", 6000); await loadProducts(); }
    catch (x) { BD.toast(x.message, "bad", 6000); }
  });
  let drafts = [];
  dropZone($("photoDrop"), $("photoFile"), async f => {
    const fd = new FormData(); fd.append("file", f);
    $("photoMsg").innerHTML = `<span class="spinner" style="display:inline-block;vertical-align:middle"></span> Reading the price list… (up to a minute)`;
    try { const r = await BD.api("/api/store/products/photo", { form: fd }); drafts = r.draft_items; openDrafts(); }
    catch (x) { BD.toast(x.message, "bad", 6000); }
    $("photoMsg").innerHTML = "";
  });
  function openDrafts() {
    $("draftBody").innerHTML = drafts.map((d, i) => `<tr data-i="${i}"><td><input type="checkbox" data-k="keep" checked aria-label="Keep"></td>
      <td><input class="input input-sm" data-k="name" value="${BD.esc(d.name)}" style="width:180px"></td>
      <td><input class="input input-sm" data-k="pack_size" value="${d.pack_size ?? ""}" style="width:70px"></td>
      <td><select class="input input-sm" data-k="pack_unit">${["g", "ml", "pcs"].map(u => `<option ${u === d.pack_unit ? "selected" : ""}>${u}</option>`).join("")}</select></td>
      <td><input class="input input-sm mono" data-k="price" value="${d.price_paise ? d.price_paise / 100 : ""}" placeholder="missing" style="width:80px;${d.price_paise ? "" : "border-color:#ff8fa3"}"></td></tr>`).join("");
    $("draftErr").textContent = ""; $("draftModal").classList.add("show"); $("ov").classList.add("show");
  }
  const closeDrafts = () => { $("draftModal").classList.remove("show"); $("ov").classList.remove("show"); };
  $("draftCancel").onclick = closeDrafts; $("ov").onclick = closeDrafts;
  $("draftSave").onclick = async () => {
    const items = [];
    for (const tr of $("draftBody").querySelectorAll("tr")) {
      const g = k => tr.querySelector(`[data-k="${k}"]`);
      if (!g("keep").checked) continue;
      const price = Math.round(parseFloat(g("price").value) * 100), size = parseFloat(g("pack_size").value);
      if (!(price >= 100) || !(size > 0) || !g("name").value.trim()) { $("draftErr").textContent = `Fill in the price and size for “${g("name").value || "a row"}”, or untick it.`; g("price").focus(); return; }
      const d = drafts[Number(tr.dataset.i)];
      items.push({ name: g("name").value.trim(), brand: d.brand, category: d.category, pack_size: size, pack_unit: g("pack_unit").value, price_paise: price, stock: 100 });
    }
    if (!items.length) { $("draftErr").textContent = "Nothing ticked"; return; }
    BD.busy($("draftSave"), true);
    try { const r = await BD.api("/api/store/products/bulk", { body: { items } }); closeDrafts(); BD.toast(`Saved ${r.added} products`, "ok"); await loadProducts(); }
    catch (x) { $("draftErr").textContent = x.message; }
    BD.busy($("draftSave"), false);
  };

  document.addEventListener("DOMContentLoaded", boot);
})();
