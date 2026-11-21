/* Waiter portal: only this waiter's tables. Approve tables, cross-check and accept orders, mark preparing/served,
   clear waiter calls. Every action is checked again on the server (owner or assigned waiter only). */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const C = { empty: "#6b6584", waiting: "#facc15", open: "#3b82f6", order: "#fb923c", bill: "#a855f7", paid: "#22c55e", alert: "#ef4444" };
  let data = null, first = true, voiceOn = false;
  const ticked = new Set(), seenAnn = new Set(), prevPending = new Set(), prevCalls = new Set(), prevWaiting = new Set();

  function state(s) {
    if (!s) return ["Free", C.empty];
    if (s.waiter_calls.length) return ["Needs help", C.alert];
    if (s.status === "WAITING_APPROVAL") return ["Wants to start", C.waiting];
    if (s.pending_count) return ["New order", C.order];
    if (s.status === "BILL_REQUESTED") return ["Bill requested", C.bill];
    if (s.status === "PAID") return ["Paid", C.paid];
    return ["Ordering", C.open];
  }

  async function load() {
    try { data = await BD.api("/api/waiter/board"); }
    catch (x) { if (x.status === 401 || x.status === 404) { location.href = "/staff/login"; return; } return; }
    $("who").textContent = "👋 " + data.me.name; $("rname").textContent = data.restaurant.name;
    notify(); draw(); first = false;
  }

  function notify() {
    const pend = new Set(), calls = new Set(), wait = new Set();
    data.tables.forEach(t => { const s = t.session; if (!s) return;
      if (s.status === "WAITING_APPROVAL") wait.add(s.id);
      s.orders.filter(o => o.status === "PENDING").forEach(o => pend.add(o.id));
      s.waiter_calls.forEach(c => calls.add(c.id)); });
    const fresh = [...pend].some(x => !prevPending.has(x)) || [...calls].some(x => !prevCalls.has(x)) || [...wait].some(x => !prevWaiting.has(x));
    if (!first && fresh) { BD.buzz([60, 40, 60]); BD.sound.chime("order"); }
    prevPending.clear(); pend.forEach(x => prevPending.add(x)); prevCalls.clear(); calls.forEach(x => prevCalls.add(x)); prevWaiting.clear(); wait.forEach(x => prevWaiting.add(x));
    (data.announcements || []).forEach(a => {
      if (seenAnn.has(a.id)) return; seenAnn.add(a.id);
      if (!first && voiceOn && data.features.kannada_alerts) try {
        const u = new SpeechSynthesisUtterance(data.restaurant.language === "en-IN" ? a.text_en : a.text_kn); u.lang = data.restaurant.language || "kn-IN"; speechSynthesis.speak(u);
      } catch (e) {}
    });
  }

  function draw() {
    if (!data.tables.length) { $("grid").innerHTML = `<div class="glass card center" style="grid-column:1/-1"><p class="muted">No tables are assigned to you yet. Ask the owner.</p></div>`; return; }
    $("grid").innerHTML = data.tables.map(t => {
      const s = t.session, [label, color] = state(s);
      const seats = data.features.seats && t.seats ? `${t.seats} seats` : "";
      let body = "";
      if (!s) body = `<p class="faint small" style="margin:8px 0 0">Free</p>`;
      else {
        body += `<div class="faint small" style="margin-top:2px">👥 ${s.guests} phone${s.guests === 1 ? "" : "s"}${seats ? " · " + seats : ""}${t.seats && s.guests > t.seats && data.features.seats ? ' · <b style="color:#fbbf24">more phones than chairs</b>' : ""}</div>`;
        s.waiter_calls.forEach(c => body += `<div class="call"><span class="grow">🔔 ${c.reason ? BD.esc(c.reason) : "Needs help"} <span class="faint small">${BD.ago(c.created_at)}</span></span><button class="btn sm" data-a="wdone" data-c="${c.id}">Done</button></div>`);
        if (s.status === "WAITING_APPROVAL") body += `<div class="acts"><button class="btn mint" data-a="approve" data-s="${s.id}" data-t="${t.number}">Approve</button><button class="btn-ghost" data-a="reject" data-s="${s.id}">Reject</button></div>`;
        s.orders.filter(o => o.status !== "SERVED").forEach(o => {
          if (o.status === "PENDING") {
            const all = o.items.every((_, k) => ticked.has(`${o.id}:${k}`));
            body += `<div class="ord"><div class="row spread"><b>New order</b><span class="faint small">${BD.ago(o.created_at)}</span></div>
              <p class="faint small" style="margin:4px 0">Read each item back to the guests and tick it.</p>
              ${o.items.map((i, k) => `<label class="chk"><input type="checkbox" data-tick="${o.id}:${k}" ${ticked.has(`${o.id}:${k}`) ? "checked" : ""}><b>${i.qty} ×</b><span>${BD.esc(i.name)}</span></label>`).join("")}
              <div class="acts"><button class="btn mint" data-a="accept" data-o="${o.id}" ${all ? "" : "disabled"}>Accept → kitchen</button><button class="btn-ghost" data-a="rejorder" data-o="${o.id}">Reject</button></div></div>`;
          } else {
            body += `<div class="ord"><div class="row spread"><b>${o.status === "PREPARING" ? "🔥 Cooking" : "✓ Accepted"}</b><span class="faint small">${o.items.map(i => `${i.qty}× ${BD.esc(i.name)}`).join(", ")}</span></div>
              <div class="acts">${o.status === "ACCEPTED" ? `<button class="btn-ghost sm" data-a="prep" data-o="${o.id}">Mark preparing</button>` : ""}<button class="btn sm" data-a="served" data-o="${o.id}">Served</button></div></div>`;
          }
        });
      }
      const hot = s && (s.status === "WAITING_APPROVAL" || s.pending_count || s.waiter_calls.length);
      return `<article class="wt ${hot ? "hot" : ""}" style="--c:${color}"><div class="wt-h"><div class="wt-n">Table ${t.number}${seats ? `<small>${seats}</small>` : ""}</div><span class="wt-st">${label}</span></div>${body}</article>`;
    }).join("");
  }

  $("grid").addEventListener("change", e => {
    const c = e.target.closest("[data-tick]"); if (!c) return;
    c.checked ? ticked.add(c.dataset.tick) : ticked.delete(c.dataset.tick); BD.buzz(8); draw();
  });
  $("grid").addEventListener("click", async e => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const a = b.dataset.a;
    let path, body = {};
    if (a === "approve") { if (!confirm(`Are guests seated at Table ${b.dataset.t}?`)) return; path = `/api/session/${b.dataset.s}/approve`; }
    if (a === "reject") { if (!confirm("Reject this table? Only do this if nobody is sitting there.")) return; path = `/api/session/${b.dataset.s}/reject`; }
    if (a === "accept") { path = `/api/orders/${b.dataset.o}/status`; body = { status: "ACCEPTED" }; }
    if (a === "rejorder") { const r = prompt("Reason for the guests (e.g. Out of stock):", "Out of stock"); if (r === null) return; path = `/api/orders/${b.dataset.o}/status`; body = { status: "REJECTED", reason: r }; }
    if (a === "prep") { path = `/api/orders/${b.dataset.o}/status`; body = { status: "PREPARING" }; }
    if (a === "served") { path = `/api/orders/${b.dataset.o}/status`; body = { status: "SERVED" }; }
    if (a === "wdone") path = `/api/waiter-calls/${b.dataset.c}/done`;
    BD.busy(b, true);
    try { await BD.api(path, { body }); BD.buzz(20); if (a === "accept") BD.toast("Sent to the kitchen", "ok"); await load(); }
    catch (x) { BD.toast(x.message, "bad"); BD.busy(b, false); }
  });
  $("soundBtn").onclick = () => { BD.sound.unlock(); BD.sound.chime("start"); voiceOn = !voiceOn; $("soundBtn").textContent = voiceOn ? "🔊 Voice on" : "🔔 Sound"; $("soundBtn").classList.toggle("active", voiceOn); };
  $("logout").onclick = async () => { try { await BD.api("/api/staff/logout", { body: {} }); } catch (e) {} location.href = "/staff/login"; };
  load(); setInterval(() => { if (!document.hidden) load(); }, 3000);
})();
