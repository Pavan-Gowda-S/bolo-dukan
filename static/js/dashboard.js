/* Cashier dashboard: polls every 2 s, colours tables, plays + speaks alerts, runs all cashier actions. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const C = { empty: "#6b6584", waiting: "#facc15", open: "#3b82f6", order: "#fb923c", bill: "#a855f7", paid: "#22c55e", alert: "#ef4444" };
  let data = null, prev = null, openTable = null, polling = false, view = BD.store.get("bd_view") || "grid";
  let floorLoaded = false, rejectTarget = null, failures = 0;
  const cards = new Map();

  BD.ownerNav("/dashboard");

  // ---------------------------------------------------------------- view model
  function viewOf(t) {
    const s = t.session;
    const v = { id: t.id, number: t.number, pos_x: data && data.features && data.features.floor_plan ? t.pos_x : null, pos_y: t.pos_y, seats: data && data.features && data.features.seats ? t.seats : null, waiter: !!(s && s.waiter_calls.length), flash: false };
    if (!s) return Object.assign(v, { state: "empty", stateLabel: "Empty", color: C.empty });
    switch (s.status) {
      case "WAITING_APPROVAL": return Object.assign(v, { state: "waiting", stateLabel: "Wants to order", color: C.waiting, flash: true });
      case "OPEN": return s.pending_count
        ? Object.assign(v, { state: "order", stateLabel: s.pending_count > 1 ? `${s.pending_count} new orders` : "New order", color: C.order, flash: true })
        : Object.assign(v, { state: "open", stateLabel: "Ordering", color: C.open });
      case "BILL_REQUESTED": return Object.assign(v, { state: "bill", stateLabel: "Bill requested", color: C.bill });
      case "PAID": return Object.assign(v, { state: "paid", stateLabel: "Paid", color: C.paid });
      default: return Object.assign(v, { state: "empty", stateLabel: s.status, color: C.empty });
    }
  }

  // ---------------------------------------------------------------- alerts
  const queue = []; let speaking = false;
  function lang() { return (data && data.restaurant.language) || "kn-IN"; }
  function phrase(kind, n) { const p = BD.phrases[lang()] || BD.phrases["en-IN"]; return p[kind](n); }
  const EV_COLOR = { start: C.waiting, order: C.order, waiter: C.alert, bill: C.bill, paid: C.paid, quiz: "#ffc145" };
  function feedItem(kind, text, en) {
    const ev = document.createElement("div"); ev.className = "ev"; ev.style.setProperty("--c", EV_COLOR[kind] || C.order);
    ev.innerHTML = `<b>●</b><span>${BD.esc(text)}</span>${en && en !== text ? `<span class="t">${BD.esc(en)}</span>` : ""}<span class="t">${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>`;
    const feed = $("feed"); feed.prepend(ev); while (feed.children.length > 8) feed.lastChild.remove();
    BD.toast(text, "say", 4500);
  }
  function alertEvent(kind, n) {
    BD.sound.chime(kind === "paid" ? "paid" : kind === "waiter" ? "waiter" : kind === "start" ? "start" : "order");
    // With Kannada alerts on, the server's announcements drive the feed, the card text and the voice.
    if (data && data.features.kannada_alerts) return;
    feedItem(kind, phrase(kind, n), lang() !== "en-IN" ? BD.phrases["en-IN"][kind](n) : "");
  }

  // Kannada alerts: each announcement is spoken once across all open dashboards (the server's claim decides).
  const seenAnn = new Set(), cardSay = new Map(); let firstAnn = true;
  function processAnnouncements(list) {
    (list || []).forEach(a => {
      if (seenAnn.has(a.id)) return;
      seenAnn.add(a.id);
      cardSay.set(a.table_number, { text: a.text_kn, until: Date.now() + 60000 });
      if (firstAnn) return;  // don't replay old alerts when the page opens
      feedItem(a.event_type, a.text_kn, a.text_en);
      if (!a.claimed && BD.sound.ready) { queue.push(a.id); setTimeout(drain, 150); }
    });
    firstAnn = false;
  }
  async function drain() {
    if (speaking || !queue.length || !BD.sound.ready) return;
    speaking = true;
    const id = queue.shift();
    try {
      const r = await BD.api(`/api/announcements/${id}/claim`, { method: "POST", body: {} });
      if (r.audio) await new Promise(ok => { const au = new Audio(r.audio); au.onended = ok; au.onerror = ok; au.play().catch(ok); setTimeout(ok, 15000); });
    } catch (e) {}
    speaking = false;
    if (queue.length) setTimeout(drain, 250);
  }
  const ttsBroken = { gemini: false };
  async function speak(text) {
    if (data.features.gemini_tts && !ttsBroken.gemini) {
      try {
        const res = await fetch("/api/announce?text=" + encodeURIComponent(text), { credentials: "same-origin" });
        if (!res.ok) throw new Error("tts " + res.status);
        const url = URL.createObjectURL(await res.blob());
        await new Promise((ok, bad) => { const a = new Audio(url); a.onended = ok; a.onerror = bad; a.play().catch(bad); });
        URL.revokeObjectURL(url);
        return;
      } catch (e) { console.warn("Gemini voice failed, using browser voice", e); ttsBroken.gemini = true; setTimeout(() => ttsBroken.gemini = false, 60000); }
    }
    if ("speechSynthesis" in window) {
      await new Promise(ok => {
        const u = new SpeechSynthesisUtterance(text); u.lang = lang(); u.rate = 0.95;
        const voice = speechSynthesis.getVoices().find(v => v.lang && v.lang.replace("_", "-").toLowerCase().startsWith(lang().slice(0, 2)));
        if (voice) u.voice = voice;
        u.onend = ok; u.onerror = ok; speechSynthesis.speak(u); setTimeout(ok, 6000);
      });
    }
  }
  function detectEvents(next) {
    if (!prev) return;
    const before = new Map(prev.tables.map(t => [t.id, t.session]));
    next.tables.forEach(t => {
      const s = t.session, p = before.get(t.id);
      if (!s) return;
      const same = p && p.id === s.id;
      if (s.status === "WAITING_APPROVAL" && !same) alertEvent("start", t.number);
      const oldPending = new Set(same ? p.orders.filter(o => o.status === "PENDING").map(o => o.id) : []);
      if (s.orders.some(o => o.status === "PENDING" && !oldPending.has(o.id))) alertEvent("order", t.number);
      const oldCalls = new Set(same ? p.waiter_calls.map(c => c.id) : []);
      if (s.waiter_calls.some(c => !oldCalls.has(c.id))) alertEvent("waiter", t.number);
      if (s.status === "BILL_REQUESTED" && (!same || p.status !== "BILL_REQUESTED")) alertEvent("bill", t.number);
      if (s.status === "PAID" && (!same || p.status !== "PAID")) alertEvent("paid", t.number);
    });
  }

  // ---------------------------------------------------------------- grid
  function cardHtml(t, v) {
    const s = t.session;
    let body;
    if (!s) body = `<div class="idle">Free · waiting for guests</div>`;
    else {
      const seatsOn = data.features.seats && t.seats;
      const info = [seatsOn ? `👥 ${s.guests} phone${s.guests === 1 ? "" : "s"} · 🪑 ${t.seats}` : `👥 ${s.guests}`, `🍽 ${s.item_count} item${s.item_count === 1 ? "" : "s"}`, `⏱ ${BD.ago(s.started_at)}`];
      if (seatsOn && s.guests > t.seats) info.push(`<b class="over-seats" title="More phones joined than chairs">⚠ more phones than chairs</b>`);
      let acts = "";
      if (s.status === "WAITING_APPROVAL") acts = `<button class="btn sm mint" data-a="approve" data-s="${s.id}">Approve</button><button class="btn-ghost sm" data-a="reject" data-s="${s.id}">Reject</button>`;
      else if (s.pending_count) { const o = s.orders.find(x => x.status === "PENDING"); acts = `<button class="btn sm mint" data-a="accept" data-o="${o.id}">Accept ${BD.rupees(o.total_paise)}</button><button class="btn-ghost sm" data-a="rejorder" data-o="${o.id}">Reject</button>`; }
      else if (s.status === "BILL_REQUESTED") acts = `<button class="btn sm violet" data-a="cash" data-s="${s.id}">Paid in cash</button>`;
      else if (s.status === "PAID") acts = `<button class="btn sm mint" data-a="free" data-s="${s.id}">Free table</button>`;
      const sp = data.splits && data.splits[String(s.id)];
      body = `<div class="info">${info.map(i => `<span>${i}</span>`).join("")}</div>
        <div class="total">${BD.rupees(s.bill_paise)}</div>
        ${sp ? `<div class="split-pill"><span class="sp-bar"><i style="width:${Math.round(sp.paid / sp.total * 100)}%"></i></span>${sp.paid} of ${sp.total} paid${sp.pending_paise ? ` · ${BD.rupees(sp.pending_paise)} pending` : ""}</div>` : ""}
        ${acts ? `<div class="acts">${acts}</div>` : ""}`;
    }
    if (data.features.merge_tables) {
      const host = t.merged_into && data.tables.find(x => x.id === t.merged_into);
      const guests = data.tables.filter(x => x.merged_into === t.id).map(x => x.number);
      if (host) body = `<div class="merge-badge">🔗 Merged with Table ${host.number}</div><div class="acts"><button class="btn-ghost sm" data-a="unmerge" data-t="${t.id}">Unmerge</button></div>`;
      else if (guests.length) body = `<div class="merge-badge">🔗 + Table ${guests.join(", ")}</div>` + body;
    }
    const say = cardSay.get(t.number);
    const sayHtml = say && say.until > Date.now() ? `<div class="kn-say">🔊 ${BD.esc(say.text)}</div>` : "";
    return `${v.waiter ? `<span class="bell" title="Waiter called">🔔</span>` : ""}
      <div class="top"><div class="num"><small>TABLE${data.features.seats && t.seats ? ` · ${t.seats} 🪑` : ""}</small>${t.number}</div><span class="st">${BD.esc(v.stateLabel)}</span></div>${sayHtml}${body}`;
  }
  function renderGrid() {
    const grid = $("gridView"), seen = new Set();
    data.tables.forEach((t, i) => {
      const v = viewOf(t); seen.add(t.id);
      let el = cards.get(t.id);
      if (!el) {
        el = document.createElement("article"); el.className = "tcard"; el.tabIndex = 0; el.dataset.tilt = "7"; el.dataset.tid = t.id;
        el.style.animationDelay = (i * 0.035) + "s"; el.setAttribute("role", "button");
        cards.set(t.id, el); grid.appendChild(el);
      }
      const html = cardHtml(t, v), sig = html + v.color + v.flash;
      if (el._sig !== sig) {
        el._sig = sig; el.innerHTML = html;
        el.style.setProperty("--c", v.color);
        el.classList.toggle("flash", v.flash); el.classList.toggle("empty", v.state === "empty");
        el.setAttribute("aria-label", `Table ${t.number}: ${v.stateLabel}`);
      }
      if (grid.children[i] !== el) grid.insertBefore(el, grid.children[i] || null);
    });
    cards.forEach((el, id) => { if (!seen.has(id)) { el.remove(); cards.delete(id); } });
    BD.tilt(grid);
  }

  function renderStats() {
    const ts = data.tables, active = ts.filter(t => t.session);
    const needs = active.reduce((n, t) => n + (t.session.status === "WAITING_APPROVAL" ? 1 : 0) + t.session.pending_count + t.session.waiter_calls.length, 0);
    const open = active.filter(t => ["OPEN", "BILL_REQUESTED"].includes(t.session.status));
    const set = (id, val) => { const el = $(id); if (el.textContent !== String(val)) { el.textContent = val; el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); } };
    set("stBusy", active.length); $("stBusyOf").textContent = `of ${ts.length} tables`;
    set("stNeeds", needs);
    set("stBills", BD.rupees(open.reduce((n, t) => n + t.session.bill_paise, 0))); $("stBillsN").textContent = `${open.length} table${open.length === 1 ? "" : "s"}`;
    set("stRev", BD.rupees(data.stats.revenue_today_paise)); $("stRevN").textContent = `${data.stats.bills_today} bill${data.stats.bills_today === 1 ? "" : "s"}`;
    document.title = needs ? `(${needs}) Cashier Dashboard` : "Cashier Dashboard";
  }

  // ---------------------------------------------------------------- drawer
  function renderDrawer() {
    if (openTable == null) return;
    const t = data.tables.find(x => x.id === openTable);
    if (!t) return closeDrawer();
    const v = viewOf(t), s = t.session, d = $("drawer");
    let html = `<div class="d-head"><div><div class="eyebrow" style="color:${v.color}">${BD.esc(v.stateLabel)}</div><div class="d-num">Table ${t.number}</div></div><button class="btn-ghost sm" id="dClose" aria-label="Close">✕</button></div>`;
    if (data.features.merge_tables && !t.merged_into && (!s || s.status === "OPEN" || s.status === "WAITING_APPROVAL")) {
      const cands = data.tables.filter(x => x.id !== t.id && !x.merged_into && !data.tables.some(y => y.merged_into === x.id)
        && (!x.session || (s && (x.session.status === "OPEN" || x.session.status === "WAITING_APPROVAL"))));
      if (cands.length) html += `<div class="merge-row"><span>🔗 Big group?</span><select class="input input-sm" id="mergeSel">${cands.map(x => `<option value="${x.id}">Table ${x.number}${x.session ? " (ordering: orders move here)" : ""}${data.features.seats && x.seats ? ` · ${x.seats} seats` : ""}</option>`).join("")}</select><button class="btn-ghost sm" data-a="merge" data-t="${t.id}">Merge into this table</button></div>`;
    }
    if (!s) {
      html += `<div class="glass card center" style="margin-top:20px"><div style="font-size:2.6rem" class="float">🪑</div><p class="muted">This table is free. When guests scan its QR code and tap “Start ordering”, it lights up yellow here.</p></div>`;
    } else {
      html += `<div class="d-meta"><div><span>Bill</span><b>${BD.rupees(s.bill_paise)}</b></div><div><span>Guests</span><b>${s.guests}${data.features.seats && t.seats ? ` <small class="faint">/ ${t.seats} seats</small>` : ""}</b></div>${s.approved_by && s.approved_by !== "owner" ? `<div><span>Approved by</span><b>${BD.esc(s.approved_by.replace(/^waiter:/, "🧑‍🍳 "))}</b></div>` : ""}<div><span>Join code</span><b class="code-big">${s.status === "WAITING_APPROVAL" ? "····" : BD.esc(s.join_code)}</b></div></div>`;
      s.waiter_calls.forEach(c => html += `<div class="waiter-row"><span>🔔 Needs help${c.reason ? " · " + BD.esc(c.reason) : ""} <span class="faint small">${BD.ago(c.created_at)}</span></span><button class="btn sm" data-a="wdone" data-c="${c.id}">Done</button></div>`);
      if (s.status === "WAITING_APPROVAL") {
        html += `<div class="notice" style="margin-bottom:14px">Someone at table ${t.number} wants to start ordering. Glance at the table: if nobody is sitting there, reject it.${data.features.seats && t.seats ? `<br><b>${s.guests} phone${s.guests === 1 ? "" : "s"} joined · ${t.seats} seats</b>${s.guests > t.seats ? " · ⚠ more phones than chairs" : ""}` : ""}</div>
          <div class="row"><button class="btn mint grow" data-a="approve" data-s="${s.id}">Approve table</button><button class="btn-ghost" data-a="reject" data-s="${s.id}">Reject</button></div>`;
      }
      if (s.payment && s.payment.status === "ACTIVE" && s.status === "BILL_REQUESTED") html += `<div class="notice" style="margin-bottom:12px">💳 Guest opened a UPI payment link for ${BD.rupees(s.payment.amount_paise)}. Waiting for Cashfree to confirm…</div>`;
      if (s.status === "PAID") html += `<div class="notice" style="border-color:rgba(34,197,94,.5);background:rgba(34,197,94,.1);color:#bbf7d0;margin-bottom:12px">✓ Paid online · ${BD.rupees(s.payment ? s.payment.amount_paise : s.bill_paise)} · confirmed by Cashfree</div>`;
      const sp = data.splits && data.splits[String(s.id)];
      if (sp) {
        html += `<div class="glass" style="padding:12px 14px;border-radius:16px;margin-bottom:12px"><div class="row spread"><b>Split bill</b><span class="small muted">${sp.paid} of ${sp.total} paid</span></div>
          ${sp.shares.map(x => `<div class="row spread" style="padding:8px 0;border-top:1px solid var(--line)"><span>${BD.esc(x.label)} · <b class="mono">${BD.rupees(x.amount_paise)}</b></span>
            ${["PAID", "CASH", "ZERO"].includes(x.status) ? `<span class="status-tag s-SERVED">${x.status === "CASH" ? "cash" : x.status === "ZERO" ? "nothing due" : "paid"}</span>` : `<button class="btn-ghost sm" data-a="sharecash" data-x="${x.id}">Paid in cash</button>`}</div>`).join("")}</div>`;
      }
      if (!s.orders.length && s.status !== "WAITING_APPROVAL") html += `<p class="muted center" style="margin:30px 0">No orders yet.</p>`;
      s.orders.slice().reverse().forEach((o, i) => {
        const n = s.orders.length - i;
        let acts = "";
        if (o.status === "PENDING") acts = `<button class="btn sm mint" data-a="accept" data-o="${o.id}">Accept</button><button class="btn-ghost sm" data-a="rejorder" data-o="${o.id}">Reject</button>`;
        else if (o.status === "ACCEPTED") acts = `<button class="btn sm" data-a="preparing" data-o="${o.id}">Preparing</button><button class="btn-ghost sm" data-a="served" data-o="${o.id}">Served</button>`;
        else if (o.status === "PREPARING") acts = `<button class="btn sm mint" data-a="served" data-o="${o.id}">Mark served</button>`;
        html += `<div class="order ${o.status}"><div class="row spread"><strong>Round ${n} <span class="faint small">· ${BD.ago(o.created_at)}${o.accepted_by && o.accepted_by !== "owner" ? ` · accepted by ${BD.esc(o.accepted_by.replace(/^waiter:/, ""))}` : ""}</span></strong><span class="status-tag s-${o.status}">${o.status.toLowerCase()}</span></div>
          <div style="margin-top:8px">${o.items.map(it => `<div class="oi"><span>${BD.foodEmoji(it.name)} ${it.qty} × ${BD.esc(it.name)}</span><span class="mono">${BD.rupees(it.qty * it.unit_price_paise)}</span></div>`).join("")}</div>
          <div class="oi" style="border-top:1px dashed var(--line-2);margin-top:6px;padding-top:8px"><span class="muted">Total</span><strong class="mono">${BD.rupees(o.total_paise)}</strong></div>
          ${o.status === "REJECTED" && o.reject_reason ? `<div class="small" style="color:#ff8fa3">Reason: ${BD.esc(o.reject_reason)}</div>` : ""}
          ${acts ? `<div class="acts">${acts}</div>` : ""}</div>`;
      });
      const foot = [];
      if (["OPEN", "BILL_REQUESTED"].includes(s.status)) foot.push(`<button class="btn violet block" data-a="cash" data-s="${s.id}">💵 Paid in cash · ${BD.rupees(s.bill_paise)}</button>`);
      if (s.status !== "WAITING_APPROVAL") foot.push(`<button class="${s.status === "PAID" ? "btn mint" : "btn-ghost"} block" data-a="free" data-s="${s.id}">Free table${s.status === "PAID" ? "" : " (end session)"}</button>`);
      if (foot.length) html += `<div class="d-foot">${foot.join("")}</div>`;
    }
    const scroll = d.scrollTop;
    if (d._html !== html) { d._html = html; d.innerHTML = html; d.scrollTop = scroll; $("dClose").onclick = closeDrawer; }
  }
  function openDrawer(id) { openTable = id; $("drawer")._html = ""; renderDrawer(); $("ov").classList.add("show"); $("drawer").classList.add("show"); }
  function closeDrawer() { openTable = null; $("ov").classList.remove("show"); $("drawer").classList.remove("show"); }
  $("ov").onclick = () => { closeDrawer(); closeReason(); };
  addEventListener("keydown", e => { if (e.key === "Escape") { closeDrawer(); closeReason(); } });

  // ---------------------------------------------------------------- actions
  async function act(btn) {
    const a = btn.dataset.a, sid = btn.dataset.s, oid = btn.dataset.o;
    const tbl = data.tables.find(t => t.session && (String(t.session.id) === sid || t.session.orders.some(o => String(o.id) === oid)));
    try {
      if (a === "rejorder") return openReason(oid);
      if (a === "merge" || a === "unmerge") {
        const other = a === "merge" ? data.tables.find(x => String(x.id) === $("mergeSel").value) : null;
        if (a === "merge" && !confirm(`Merge Table ${other.number} into this table? Its QR code will open the same order and bill.`)) return;
        BD.busy(btn, true);
        if (a === "merge") await BD.api("/api/tables/merge", { body: { host_table_id: Number(btn.dataset.t), table_id: other.id } });
        else await BD.api(`/api/tables/${btn.dataset.t}/unmerge`, { body: {} });
        BD.toast(a === "merge" ? "Tables merged" : "Table unmerged", "ok", 2200);
        return poll(true);
      }
      if (a === "sharecash" && !confirm("Mark this share as paid in cash?")) return;
      if (a === "reward") {
        BD.busy(btn, true);
        const r = await BD.api(`/api/quiz/${btn.dataset.r}/reward`, { method: "POST", body: {} });
        BD.toast(r.message, "ok", 5000); BD.sound.chime("paid");
        return poll(true);
      }
      if (a === "cash") {
        const amt = tbl ? BD.rupees(tbl.session.bill_paise) : "";
        if (!confirm(`Mark ${amt} as paid in CASH and close table ${tbl ? tbl.number : ""}?`)) return;
      }
      if (a === "free" && tbl && tbl.session.status !== "PAID" && tbl.session.bill_paise > 0) {
        if (!confirm(`Table ${tbl.number} has an unpaid bill of ${BD.rupees(tbl.session.bill_paise)}.\n\nFree the table anyway? (Use “Paid in cash” if they paid cash.)`)) return;
      }
      BD.busy(btn, true);
      const map = {
        approve: [`/api/session/${sid}/approve`], reject: [`/api/session/${sid}/reject`],
        accept: [`/api/orders/${oid}/status`, { status: "ACCEPTED" }], preparing: [`/api/orders/${oid}/status`, { status: "PREPARING" }],
        served: [`/api/orders/${oid}/status`, { status: "SERVED" }], cash: [`/api/session/${sid}/cash`],
        free: [`/api/session/${sid}/free${tbl && tbl.session.status !== "PAID" ? "?force=1" : ""}`],
        wdone: [`/api/waiter-calls/${btn.dataset.c}/done`],
        sharecash: [`/api/shares/${btn.dataset.x}/cash`],
      };
      const [url, body] = map[a];
      await BD.api(url, { method: "POST", body: body || {} });
      BD.sound.chime("tap"); BD.buzz();
      const msg = { approve: "Table approved", reject: "Request rejected", accept: "Order accepted", preparing: "Marked preparing", served: "Marked served", cash: "Paid in cash. Table closed", free: "Table is free", wdone: "Done", sharecash: "Share marked as paid in cash" }[a];
      BD.toast(msg, "ok", 2200);
      if (a === "free" || a === "cash") closeDrawer();
      await poll(true);
    } catch (x) { BD.toast(x.message, "bad"); BD.busy(btn, false); await poll(true); }
  }
  document.addEventListener("click", e => {
    const btn = e.target.closest("button[data-a]");
    if (btn) { e.stopPropagation(); unlockSound(); act(btn); return; }
    const card = e.target.closest(".tcard");
    if (card) openDrawer(Number(card.dataset.tid));
  });
  document.addEventListener("keydown", e => {
    const card = e.target.closest && e.target.closest(".tcard");
    if (card && (e.key === "Enter" || e.key === " ") && !e.target.closest("button")) { e.preventDefault(); openDrawer(Number(card.dataset.tid)); }
  });

  // reject-with-reason modal
  function openReason(oid) { rejectTarget = oid; $("reasonText").value = ""; $("ov").classList.add("show"); $("reasonModal").classList.add("show"); }
  function closeReason() { rejectTarget = null; $("reasonModal").classList.remove("show"); if (openTable == null) $("ov").classList.remove("show"); }
  $("reasons").addEventListener("click", e => { const p = e.target.closest("[data-r]"); if (p) $("reasonText").value = p.dataset.r; });
  $("reasonCancel").onclick = closeReason;
  $("reasonGo").onclick = async () => {
    const oid = rejectTarget; if (!oid) return;
    BD.busy($("reasonGo"), true);
    try { await BD.api(`/api/orders/${oid}/status`, { body: { status: "REJECTED", reason: $("reasonText").value.trim() } }); BD.toast("Order rejected", "ok"); }
    catch (x) { BD.toast(x.message, "bad"); }
    BD.busy($("reasonGo"), false); closeReason(); poll(true);
  };

  // ---------------------------------------------------------------- sound
  function unlockSound() {
    if (BD.sound.ready) return;
    BD.sound.unlock();
    try { speechSynthesis && speechSynthesis.getVoices(); } catch (e) {}
    setTimeout(updateSoundBtn, 60);
  }
  function updateSoundBtn() {
    const b = $("soundBtn");
    if (BD.sound.ready) { b.textContent = data && data.features.kannada_alerts ? "🔊 Sound + voice on" : "🔊 Sound on"; b.classList.remove("need"); b.classList.add("active"); }
    else { b.textContent = "🔔 Turn on sound"; b.classList.add("need"); b.classList.remove("active"); }
  }
  $("soundBtn").onclick = () => {
    unlockSound();
    setTimeout(() => {
      BD.sound.chime("order");
      if (data && data.features.kannada_alerts) BD.toast("Sound is on. New alerts will be spoken in Kannada here.", "ok");
    }, 120);
  };
  document.addEventListener("pointerdown", unlockSound, { once: true });

  // ---------------------------------------------------------------- 3D floor
  function setView(v) {
    view = v; BD.store.set("bd_view", v);
    document.querySelectorAll(".seg button").forEach(b => { const on = b.dataset.view === v; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
    $("gridView").classList.toggle("hidden", v !== "grid");
    $("floorView").classList.toggle("hidden", v !== "floor");
    $("planView").classList.toggle("hidden", v !== "plan");
    if (v === "plan") renderPlan();
    if (v === "floor") loadFloor();
    if (window.Floor3D) window.Floor3D.visible = v === "floor";
  }
  function loadFloor() {
    if (floorLoaded) { if (window.Floor3D && window.Floor3D.ready) { window.Floor3D.resize(); pushFloor(); } return; }
    floorLoaded = true;
    import("/static/js/floor3d.js?v=5").then(() => {
      window.Floor3D.mount($("floorMount"), id => openDrawer(id));
      window.Floor3D.visible = view === "floor";
      pushFloor();
    }).catch(e => {
      console.error(e);
      $("floorMount").innerHTML = `<div class="center muted" style="padding:80px 20px">The 3D view needs an internet connection (it loads Three.js). The grid view works offline.</div>`;
    });
  }
  function blueprintUrl() { return data && data.features.floor_plan && data.restaurant.floor_image ? "/api/floor/image?v=" + encodeURIComponent(data.restaurant.floor_image) : null; }
  function pushFloor() {
    if (!(window.Floor3D && window.Floor3D.ready && data)) return;
    if (window.Floor3D.setBlueprint) window.Floor3D.setBlueprint(blueprintUrl());
    if (window.Floor3D.setLayout) {  // walls, counters and rooms read from the blueprint (applied by the owner)
      let lay = null;
      try { lay = data.features.floor_plan && data.restaurant.floor_layout ? JSON.parse(data.restaurant.floor_layout) : null; } catch (e) {}
      window.Floor3D.setLayout(lay);
    }
    window.Floor3D.update(data.tables.map(viewOf));
  }
  // 7: 2D plan view: the blueprint with live table markers in the dashboard colours
  function renderPlan() {
    if (!data) return;
    const has = data.features.floor_plan && (data.restaurant.floor_image || data.tables.some(t => t.pos_x != null));
    $("planTab").classList.toggle("hidden", !has);
    if (!has) { if (view === "plan") setView("grid"); return; }
    if (view !== "plan") return;
    const n = data.tables.length, cols = Math.ceil(Math.sqrt(n * 1.4)), rows = Math.ceil(n / cols), url = blueprintUrl();
    const box = $("planBox");
    if (box.dataset.img !== String(url)) { box.dataset.img = String(url); box.innerHTML = (url ? `<img src="${url}" alt="Floor plan">` : "") + `<div class="plan-marks"></div>`; box.classList.toggle("noimg", !url); }
    box.querySelector(".plan-marks").innerHTML = data.tables.map((t, i) => {
      const v = viewOf(t), x = t.pos_x != null ? t.pos_x : ((i % cols) + .5) / cols * 100, y = t.pos_y != null ? t.pos_y : (Math.floor(i / cols) + .5) / rows * 100;
      return `<button class="pmk ${v.flash ? "flash" : ""}" data-tid="${t.id}" style="left:${x}%;top:${y}%;--c:${v.color}" title="Table ${t.number}: ${BD.esc(v.stateLabel)}">${t.number}${v.waiter ? "🔔" : ""}<small>${BD.esc(v.stateLabel)}</small></button>`;
    }).join("");
  }
  $("planBox").addEventListener("click", e => { const b = e.target.closest("[data-tid]"); if (b) openDrawer(Number(b.dataset.tid)); });
  document.querySelectorAll(".seg button").forEach(b => b.onclick = () => setView(b.dataset.view));

  // ---------------------------------------------------------------- quiz prizes
  function renderPrizes(list) {
    const html = list.map(p => `<div class="prize"><span class="gift">🎁</span><span class="grow"><b>Table ${p.table_number} won the Table Quiz</b><br><span class="small muted">${p.score} points · their free tea is added to the bill at ₹0</span></span>
      <button class="btn sm" data-a="reward" data-r="${p.round_id}">Give free tea</button></div>`).join("");
    const box = $("prizes");
    if (box._h !== html) { box._h = html; box.innerHTML = html; }
  }

  // ---------------------------------------------------------------- polling
  async function poll(force) {
    if (polling && !force) return;
    polling = true;
    try {
      const next = await BD.api("/api/dashboard");
      detectEvents(next);
      prev = next; data = next; failures = 0;
      processAnnouncements(data.announcements);
      renderPrizes(data.quiz_prizes || []);
      if (window.BDDash) window.BDDash.emit(data);  // sales strip + owner voice (dashboard_plus.js)
      $("live").classList.remove("off"); $("live").lastChild.textContent = "Live";
      $("rname").textContent = data.restaurant.name;
      if (!data.tables.length) {
        cards.clear();
        $("gridView").innerHTML = `<div class="glass card center" style="grid-column:1/-1"><p>No tables yet. <a href="/owner/setup">Set up your tables</a> to get QR codes.</p></div>`;
      } else renderGrid();
      renderStats(); renderDrawer(); pushFloor(); renderPlan(); updateSoundBtn();
    } catch (x) {
      if (x.status === 401) { location.href = "/owner/login?next=/dashboard"; return; }
      failures++;
      if (failures > 1) { $("live").classList.add("off"); $("live").lastChild.textContent = "Reconnecting"; }
    } finally { polling = false; }
  }
  function tickClock() { $("clock").textContent = new Date().toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }); }
  tickClock(); setInterval(tickClock, 15000);
  setView(view);
  poll(true);
  setInterval(() => { if (!document.hidden) poll(); }, 2000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(true); });
})();
