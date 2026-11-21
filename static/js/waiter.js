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

  let planOn = false;
  function drawPlan() {
    const url = data.restaurant.floor_image, n = data.tables.length, cols = Math.ceil(Math.sqrt(n * 1.4)), rows = Math.ceil(n / cols);
    $("grid").innerHTML = `<div class="glass" style="grid-column:1/-1;position:relative;border-radius:16px;overflow:hidden;${url ? "" : "aspect-ratio:16/10"}">${url ? `<img src="${BD.esc(url)}" alt="Floor plan" style="display:block;width:100%;opacity:.85">` : ""}
      ${data.tables.map((t, i) => { const [label, color] = state(t.session), x = t.pos_x != null ? t.pos_x : ((i % cols) + .5) / cols * 100, y = t.pos_y != null ? t.pos_y : (Math.floor(i / cols) + .5) / rows * 100;
        return `<button data-plan="${t.id}" style="position:absolute;left:${x}%;top:${y}%;transform:translate(-50%,-50%);padding:6px 10px;border-radius:12px;border:2px solid ${color};background:#120a20;color:#fff;font-weight:800">${t.number}<small style="display:block;font-size:.6rem">${label}</small></button>`; }).join("")}</div>`;
  }
  function draw() {
    const canPlan = data.features.floor_plan && (data.restaurant.floor_image || data.tables.some(t => t.pos_x != null));
    let pb = document.getElementById("planBtn");
    if (canPlan && !pb) { pb = document.createElement("button"); pb.id = "planBtn"; pb.className = "btn-ghost sm"; pb.textContent = "▣ Floor"; $("soundBtn").before(pb); pb.onclick = () => { planOn = !planOn; pb.classList.toggle("active", planOn); draw(); }; }
    if (planOn && canPlan) return drawPlan();
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
      if (data.features.merge_tables) {
        const host = t.merged_into && data.tables.find(x => x.id === t.merged_into);
        const joined = data.tables.filter(x => x.merged_into === t.id).map(x => x.number);
        if (t.merged_into) body = `<p class="faint" style="margin:8px 0">🔗 Merged with Table ${host ? host.number : "?"}</p><div class="acts"><button class="btn-ghost sm" data-a="unmerge" data-t="${t.id}">Unmerge</button></div>`;
        else {
          if (joined.length) body = `<p style="margin:6px 0 0;color:#a5e8ff;font-weight:700">🔗 + Table ${joined.join(", ")}</p>` + body;
          if (!s || s.status === "OPEN" || s.status === "WAITING_APPROVAL") body += `<div class="acts"><button class="btn-ghost sm" data-a="merge" data-t="${t.id}" data-n="${t.number}">🔗 Merge a table into this one</button></div>`;
        }
      }
      const hot = s && (s.status === "WAITING_APPROVAL" || s.pending_count || s.waiter_calls.length);
      return `<article class="wt ${hot ? "hot" : ""}" style="--c:${color}"><div class="wt-h"><div class="wt-n">Table ${t.number}${seats ? `<small>${seats}</small>` : ""}</div><span class="wt-st">${label}</span></div>${body}</article>`;
    }).join("");
  }

  $("grid").addEventListener("click", e => { const p = e.target.closest("[data-plan]"); if (!p) return; planOn = false; const b = $("planBtn"); if (b) b.classList.remove("active"); draw(); const el = [...document.querySelectorAll(".wt")][data.tables.findIndex(t => String(t.id) === p.dataset.plan)]; if (el) el.scrollIntoView({ behavior: "smooth", block: "center" }); });
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
    if (a === "unmerge") path = `/api/tables/${b.dataset.t}/unmerge`;
    if (a === "merge") {
      const n = prompt(`Which table number should join Table ${b.dataset.n}? (Its QR will open the same order and bill.)`); if (!n) return;
      const other = data.tables.find(x => String(x.number) === n.trim());
      if (!other) { BD.toast("That table isn't one of yours", "bad"); return; }
      path = "/api/tables/merge"; body = { host_table_id: Number(b.dataset.t), table_id: other.id };
    }
    BD.busy(b, true);
    try { await BD.api(path, { body }); BD.buzz(20); if (a === "accept") BD.toast("Sent to the kitchen", "ok"); await load(); }
    catch (x) { BD.toast(x.message, "bad"); BD.busy(b, false); }
  });
  $("soundBtn").onclick = () => { BD.sound.unlock(); BD.sound.chime("start"); voiceOn = !voiceOn; $("soundBtn").textContent = voiceOn ? "🔊 Voice on" : "🔔 Sound"; $("soundBtn").classList.toggle("active", voiceOn); };
  $("logout").onclick = async () => { try { await BD.api("/api/staff/logout", { body: {} }); } catch (e) {} location.href = "/staff/login"; };
  load(); setInterval(() => { if (!document.hidden) load(); }, 3000);
})();
