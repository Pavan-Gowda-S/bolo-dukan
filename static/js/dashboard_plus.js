/* Dashboard add-ons: A1 sales strip + today's bills, A3 owner voice assistant. Each shows only when its switch is on. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  let feats = null, lastSummaryAt = 0, lastPaidCount = -1;
  window.BDDash = {
    emit(data) {
      if (!feats) { feats = data.features; init(); }
      const paidNow = (data.announcements || []).filter(a => a.event_type === "paid" || a.event_type === "share_paid").length;
      if (feats.sales_summary && (Date.now() - lastSummaryAt > 20000 || paidNow !== lastPaidCount)) { lastPaidCount = paidNow; loadSummary(); }
    },
  };

  function init() {
    if (feats.sales_summary) {
      const box = document.createElement("section");
      box.id = "salesStrip"; box.className = "sales-strip";
      box.innerHTML = `<div class="sales-loading">Loading today's sales…</div>`;
      document.querySelector(".stats").before(box);
    }
    if (feats.owner_voice) buildOwnerMic();
    if (feats.kitchen_tv) buildKitchenLink();
    if (feats.staff) {
      const a = document.createElement("a"); a.className = "btn-ghost"; a.href = "/owner/staff"; a.textContent = "🧑‍🍳 Staff";
      const bar = document.querySelector(".dash-head .row.wrap"); if (bar) bar.prepend(a);
    }
  }

  // ---------------------------------------------------------------- 3. kitchen TV link
  function buildKitchenLink() {
    const btn = document.createElement("button");
    btn.className = "btn-ghost"; btn.textContent = "📺 Kitchen display";
    const bar = document.querySelector(".dash-head .row.wrap"); if (bar) bar.prepend(btn);
    const m = document.createElement("div");
    m.className = "modal"; m.id = "kitchenModal"; m.setAttribute("role", "dialog"); m.style.width = "min(520px, calc(100% - 24px))";
    m.innerHTML = `<h3>Kitchen display</h3><p class="muted small" style="margin:6px 0 14px">Open this link on the kitchen TV or tablet and tap ▶ Start once. It shows accepted orders only (no prices or phone numbers) and reads new ones aloud.</p>
      <div class="row"><input class="input grow mono" id="kUrl" readonly><button class="btn-ghost sm" id="kCopy">Copy</button></div>
      <div class="row" style="margin-top:14px"><a class="btn grow" id="kOpen" target="_blank" rel="noopener">Open display ↗</a><button class="btn-ghost" id="kRegen" title="The old link stops working">Regenerate link</button><button class="btn-ghost" id="kClose">Close</button></div>`;
    document.body.appendChild(m);
    const ov = document.getElementById("ov");
    const close = () => { m.classList.remove("show"); ov.classList.remove("show"); };
    const set = url => { $("kUrl").value = url; $("kOpen").href = url; };
    btn.onclick = async () => {
      try { set((await BD.api("/api/owner/kitchen-link")).url); m.classList.add("show"); ov.classList.add("show"); } catch (x) { BD.toast(x.message, "bad"); }
    };
    $("kClose").onclick = close; ov.addEventListener("click", close);
    $("kCopy").onclick = async () => { try { await navigator.clipboard.writeText($("kUrl").value); BD.toast("Link copied", "ok"); } catch (e) { $("kUrl").select(); } };
    $("kRegen").onclick = async () => {
      if (!confirm("Make a new kitchen link? The old link stops working on any screen that has it open.")) return;
      try { set((await BD.api("/api/owner/kitchen-link/regenerate", { body: {} })).url); BD.toast("New link made. Open it on the kitchen screen.", "ok"); } catch (x) { BD.toast(x.message, "bad"); }
    };
  }

  // ---------------------------------------------------------------- A1 sales summary
  let billsOpen = false;
  async function loadSummary() {
    lastSummaryAt = Date.now();
    let s;
    try { s = await BD.api("/api/dashboard/summary"); } catch (e) { return; }
    const box = $("salesStrip"); if (!box) return;
    const pct = s.collected_paise ? Math.round(s.online_paise / s.collected_paise * 100) : 0;
    box.innerHTML = `
      <div class="ss-grid">
        <div class="ss-card glass" data-tilt="6"><span class="k">Collected today</span><b class="v mono">${BD.rupees(s.collected_paise)}</b><span class="s">${s.date} · verified bills only</span></div>
        <div class="ss-card glass" data-tilt="6"><span class="k">Bills</span><b class="v mono">${s.bills}</b><span class="s">avg ${BD.rupees(s.average_paise)}</span></div>
        <div class="ss-card glass" data-tilt="6"><span class="k">Online vs cash</span>
          <div class="ss-donut" style="--p:${pct}"><span>${pct}%</span></div>
          <span class="s">${BD.rupees(s.online_paise)} online · ${BD.rupees(s.cash_paise)} cash</span></div>
        <div class="ss-card glass" data-tilt="6"><span class="k">Top items</span>
          ${s.top_items.length ? `<ol class="ss-top">${s.top_items.map(t => `<li><span>${BD.foodEmoji(t.name)} ${BD.esc(t.name)}</span><b>${t.qty}</b></li>`).join("")}</ol>` : `<span class="s">No sales yet today</span>`}</div>
      </div>
      <button class="btn-ghost sm ss-toggle" id="ssToggle">${billsOpen ? "Hide" : "Show"} today's bills (${s.bills})</button>
      <div class="ss-bills ${billsOpen ? "" : "hidden"}" id="ssBills">
        ${s.bill_list.length ? `<table class="table-list"><thead><tr><th>Time</th><th>Table</th><th>Amount</th><th>Method</th><th>Cashfree link</th></tr></thead><tbody>
        ${s.bill_list.map(b => `<tr><td class="mono">${BD.esc(b.time)}</td><td>${b.table != null ? "Table " + b.table : BD.esc(b.label || "")}</td><td class="mono"><b>${BD.rupees(b.amount_paise)}</b></td>
          <td><span class="status-tag ${b.method === "cash" ? "s-PREPARING" : "s-SERVED"}">${b.method === "cash" ? "cash" : b.method === "split" ? "split · Cashfree" : "Cashfree"}</span></td>
          <td class="mono small faint">${BD.esc(b.link_id || "—")}</td></tr>`).join("")}</tbody></table>` : `<p class="muted small">No paid bills yet today.</p>`}
      </div>`;
    $("ssToggle").onclick = () => { billsOpen = !billsOpen; $("ssBills").classList.toggle("hidden", !billsOpen); $("ssToggle").textContent = `${billsOpen ? "Hide" : "Show"} today's bills (${s.bills})`; };
    BD.tilt(box);
  }

  // ---------------------------------------------------------------- A3 owner voice
  function buildOwnerMic() {
    const fab = document.createElement("button");
    fab.className = "owner-fab"; fab.setAttribute("aria-label", "Ask your assistant"); fab.innerHTML = `<span class="mic-rings"></span>🎙️`;
    document.body.appendChild(fab);
    const sheet = document.createElement("div");
    sheet.className = "sheet"; sheet.id = "ownerSheet"; sheet.setAttribute("role", "dialog");
    sheet.innerHTML = `<div class="grab"></div>
      <div class="row spread"><h3>Ask your assistant</h3><button class="btn-ghost sm" data-oclose>Close</button></div>
      <p class="muted small" style="margin:4px 0 0">“ಇವತ್ತಿನ ಸೇಲ್ಸ್ ಎಷ್ಟು?” · “top items today” · “which tables are waiting?” · “masala dosa khatam ho gaya” · “free table 5”</p>
      <div class="voice-stage"><button class="voice-orb" id="oOrb" aria-label="Hold to talk"><span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span><span class="core">🎙️</span></button>
      <div class="v-state" id="oState">${BD.canRecord ? "Hold to talk (or tap)" : "Type your question below"}</div></div>
      <div id="oResult"></div>
      <form class="row" id="oForm" style="gap:8px;margin-top:10px"><input class="input grow" id="oText" placeholder="…or type it here" maxlength="300" autocomplete="off"><button class="btn" id="oSend" aria-label="Ask">→</button></form>`;
    document.body.appendChild(sheet);
    const ov = $("ov");
    const open = () => { $("oResult").innerHTML = ""; ov.classList.add("show"); sheet.classList.add("show"); };
    const close = () => { sheet.classList.remove("show"); if (!document.querySelector(".drawer.show, .modal.show")) ov.classList.remove("show"); if (rec.recording) rec.stop(); };
    fab.onclick = open;
    sheet.querySelector("[data-oclose]").onclick = close;
    ov.addEventListener("click", close);
    if (!BD.canRecord) $("oOrb").classList.add("hidden");
    const orb = $("oOrb");
    const rec = BD.recorder(l => orb.style.setProperty("--lvl", l.toFixed(3)));
    let pressAt = 0, busy = false;
    const setState = (s, t) => { orb.classList.toggle("rec", s === "rec"); orb.classList.toggle("think", s === "think"); $("oState").textContent = t || { idle: "Hold to talk (or tap)", rec: "Listening… let go when done", think: "Checking…" }[s]; };
    async function finish() { const wav = await rec.stop(); if (wav) send({ audio: wav }); else setState("idle"); }
    orb.addEventListener("pointerdown", e => {
      e.preventDefault(); if (busy) return;
      if (rec.recording) return finish();
      pressAt = Date.now(); setState("rec"); BD.sound.unlock();
      rec.start(15000).then(w => { if (w) send({ audio: w }); }).catch(() => setState("idle", "Microphone blocked. Type your question below."));
    });
    orb.addEventListener("pointerup", () => { if (rec.recording && Date.now() - pressAt > 450) finish(); });
    $("oForm").onsubmit = e => { e.preventDefault(); const t = $("oText").value.trim(); if (t) { send({ text: t }); $("oText").value = ""; } };
    async function send(input) {
      busy = true; setState("think");
      const fd = new FormData();
      if (input.audio) fd.append("audio", input.audio, "voice.wav"); else fd.append("text", input.text);
      try {
        const r = await BD.api("/api/owner/voice", { form: fd });
        BD.play(r.audio);
        $("oResult").innerHTML = `${r.transcript ? `<div class="v-said"><small>You asked</small>${BD.esc(r.transcript)}</div>` : ""}
          <div class="o-answer">${BD.esc(r.answer)}</div>${r.answer_en && r.answer_en !== r.answer ? `<p class="faint small">${BD.esc(r.answer_en)}</p>` : ""}
          ${r.confirm ? `<div class="row" style="margin-top:12px"><button class="btn mint grow" id="oYes">Yes, do it</button><button class="btn-ghost" id="oNo">No</button></div>` : ""}`;
        if (r.confirm) {
          $("oNo").onclick = () => { $("oResult").innerHTML = `<p class="muted">Okay, nothing changed.</p>`; };
          $("oYes").onclick = async () => {
            BD.busy($("oYes"), true);
            try { const c = await BD.api("/api/owner/voice/confirm", { body: r.confirm }); $("oResult").innerHTML = `<div class="o-answer">✅ ${BD.esc(c.message)}</div>`; BD.toast(c.message, "ok"); }
            catch (x) { $("oResult").innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; }
          };
        }
      } catch (x) { $("oResult").innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; }
      busy = false; setState("idle");
    }
  }
})();
