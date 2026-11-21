/* Kitchen TV: read-only ticket board. Refreshes every 2 s, keeps the last board on screen if the network drops,
   and speaks each new accepted order once (claimed on the server, so two TVs don't both speak it). */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const TOKEN = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  const API = "/api/kitchen/" + encodeURIComponent(TOKEN);
  let offset = 0, tickets = [], seen = new Set(), first = true, started = false, failures = 0, lang = "kn-IN";
  const queue = [], heard = new Set();
  let speaking = false, wakeLock = null;

  function clock() { $("clock").textContent = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
  setInterval(clock, 1000); clock();

  const mmss = ms => { const s = Math.max(0, Math.floor(ms / 1000)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
  function times() {  // every second: only the timers and colours change, so nothing flickers
    const now = Date.now() + offset;
    document.querySelectorAll(".tk[data-at]").forEach(el => {
      const age = now - new Date(el.dataset.at).getTime();
      el.querySelector(".tk-time").textContent = mmss(age);
      el.classList.toggle("red", age > 20 * 60000); el.classList.toggle("amber", age > 10 * 60000 && age <= 20 * 60000);
    });
  }
  function draw() {
    const now = Date.now() + offset;
    $("kstat").textContent = tickets.length ? `${tickets.length} ticket${tickets.length === 1 ? "" : "s"}` : "";
    if (!tickets.length) { $("grid").innerHTML = `<div class="empty-k">No orders right now 🍳</div>`; return; }
    $("grid").innerHTML = tickets.map(t => {
      const age = now - new Date(t.accepted_at).getTime(), cls = age > 20 * 60000 ? "red" : age > 10 * 60000 ? "amber" : "";
      return `<article class="tk ${cls} ${t._new || first ? "new" : ""}" data-at="${BD.esc(t.accepted_at)}">
        <div class="tk-h"><div class="tk-t">TABLE ${t.table_number}<small>${t.seats ? `${t.seats} seats · ` : ""}order ${t.order_no}</small></div><div class="tk-time">${mmss(age)}</div></div>
        ${t.items.map(i => `<div class="tk-i"><b>${i.qty} ×</b><span>${BD.esc(i.name)}${i.name_local ? `<small>${BD.esc(i.name_local)}</small>` : ""}</span></div>`).join("")}
        ${t.status === "PREPARING" ? `<span class="cook">🔥 Cooking</span>` : ""}</article>`;
    }).join("");
  }
  setInterval(times, 1000);

  async function poll() {
    try {
      const r = await fetch(API + "/board", { cache: "no-store" });
      if (r.status === 404) { $("grid").innerHTML = `<div class="empty-k">This kitchen link was changed. Ask the owner for the new link.</div>`; $("conn").textContent = "● Link expired"; $("conn").classList.add("off"); return; }
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      failures = 0; $("conn").textContent = "● Live"; $("conn").classList.remove("off");
      offset = new Date(d.server_time).getTime() - Date.now();
      lang = d.restaurant.language || "kn-IN";
      $("rname").textContent = d.restaurant.name + " · Kitchen"; $("sTitle").textContent = d.restaurant.name + " · Kitchen";
      const sig = JSON.stringify(d.tickets.map(t => [t.order_id, t.status]));
      tickets = d.tickets.map(t => Object.assign(t, { _new: !first && !seen.has(t.order_id) }));
      tickets.forEach(t => seen.add(t.order_id));
      if (tickets.some(t => t._new)) BD.sound.chime("order");
      if (sig !== draw.sig || first) {  // redraw only when tickets change; the highlight fades after 6 s
        draw.sig = sig; draw();
        setTimeout(() => document.querySelectorAll(".tk.new").forEach(e => e.classList.remove("new")), 6000);
      }
      first = false;
      if (started) (d.announcements || []).forEach(a => { if (!heard.has(a.id)) { heard.add(a.id); queue.push(a.id); } });
      drain();
    } catch (e) {
      if (++failures >= 2) { $("conn").textContent = "● Reconnecting…"; $("conn").classList.add("off"); }
    } finally { setTimeout(poll, 2000); }
  }

  function browserSay(text) {
    return new Promise(res => { try { const u = new SpeechSynthesisUtterance(text); u.lang = lang; u.onend = res; u.onerror = res; speechSynthesis.speak(u); setTimeout(res, 12000); } catch (e) { res(); } });
  }
  async function drain() {
    if (speaking || !queue.length) return;
    speaking = true;
    const id = queue.shift();
    try {
      const r = await fetch(`${API}/announcements/${id}/claim`, { method: "POST" }).then(x => x.json());
      if (r.spoken_here) {
        const text = lang === "en-IN" ? r.text_en : r.text_kn;
        $("say").textContent = "🔊 " + text; $("say").classList.remove("hidden");
        if (r.audio) await new Promise(ok => { const a = new Audio(r.audio); a.onended = ok; a.onerror = ok; a.play().catch(ok); setTimeout(ok, 15000); });
        else await browserSay(text);
        setTimeout(() => $("say").classList.add("hidden"), 2500);
      }
    } catch (e) {}
    speaking = false;
    if (queue.length) setTimeout(drain, 300);
  }

  async function keepAwake() { try { if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen"); } catch (e) {} }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && started) keepAwake(); });
  $("go").onclick = async () => {
    started = true; BD.sound.unlock(); BD.sound.chime("start");
    $("start").classList.add("hidden");
    try { await document.documentElement.requestFullscreen(); } catch (e) {}
    keepAwake();
  };
  poll();
})();
