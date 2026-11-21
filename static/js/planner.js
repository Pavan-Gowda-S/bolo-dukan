/* AI Meal Planner: wizard -> recipes -> recipe detail (read aloud, hands-free) -> cart (swap, remove, fill to budget) -> pay.
   All numbers (costs, nutrition, cart, budget fit) come from the server's planner maths. The AI only fills the wizard from speech
   and translates steps. Nothing is bought until the shopper taps Pay. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const S = window.SHOP;
  const PK = () => "bd_plan_" + S.slug;
  const LANGS = [["en-IN", "English"], ["kn-IN", "ಕನ್ನಡ"], ["hi-IN", "हिन्दी"]];
  const MEALS = [["breakfast", "Breakfast", "🍳", "Morning"], ["lunch", "Lunch", "🍛", "Afternoon"], ["dinner", "Dinner", "🌙", "Night"]];
  const DIET_IC = { veg: "🥦", egg: "🥚", nonveg: "🍗", vegan: "🌱" };
  const GOAL_IC = { high_protein: "💪", high_calorie: "⚡", low_calorie: "🪶", balanced: "⚖️", low_carb: "🥗" };

  let opts = null, step = 0, dirBack = false;
  let q = { people: 4, budget_rupees: 1500, days: 2, meals: ["lunch", "dinner"], appliances: ["gas_stove", "pressure_cooker"], diet: "veg", goal: "balanced", pantry: true };
  let recipes = [], selected = new Set(), removed = new Set(), swaps = {}, fill = false, lastCart = null, rFilter = "all", rQuery = "";
  try { const saved = JSON.parse(BD.store.get(PK()) || "null"); if (saved && saved.q) { q = Object.assign(q, saved.q); selected = new Set(saved.selected || []); } } catch (e) {}
  const save = () => BD.store.set(PK(), JSON.stringify({ q, selected: [...selected] }));

  const STEPS = [
    { id: "people", title: "How many people?", sub: "We'll scale every recipe and pack to this many." },
    { id: "budget", title: "What's your budget?", sub: "Your cart will never go over it." },
    { id: "days", title: "For how many days?", sub: "1 to 7 days of cooking." },
    { id: "meals", title: "Which meals each day?", sub: "Tap all that you cook at home." },
    { id: "appliances", title: "What do you cook with?", sub: "We only show recipes you can actually make." },
    { id: "diet", title: "Food preference", sub: "Pick one." },
    { id: "goal", title: "Your goal", sub: "Recipes are ranked by this, using nutrition data (approx.)." },
    { id: "pantry", title: "Staples at home?", sub: "Salt, oil, sugar and common spices." },
  ];

  // ---------------------------------------------------------------- router entry
  const PL = window.PLANNER = {
    async route(h) {
      if (!opts) {
        try { opts = await BD.api(S.api + "/planner/options"); } catch (x) { BD.toast(x.message, "bad"); return S.go("home"); }
        if (S.info.features.voice) $("wVoice").classList.remove("hidden");
      }
      if (h === "recipes") { if (!recipes.length) return loadRecipes(); S.show("recipes"); return drawRecipes(); }
      if (h === "pcart") { if (!selected.size) return S.go(recipes.length ? "recipes" : "plan"); S.show("pcart"); return loadCart(); }
      S.show("plan"); drawStep();
    },
  };

  // ---------------------------------------------------------------- wizard
  function flipCard(val, label, icon, on, desc, attr) {
    return `<button type="button" class="flip ${on ? "on" : ""}" ${attr}="${val}" aria-pressed="${on}">
      <span class="in"><span class="f"><span class="ic">${icon}</span><span class="lb">${BD.esc(label)}</span>${desc ? `<span class="ds">${BD.esc(desc)}</span>` : ""}</span>
      <span class="b"><span class="tick">✓</span><span class="ic">${icon}</span><span class="lb">${BD.esc(label)}</span></span></span></button>`;
  }
  function drawStep() {
    const s = STEPS[step];
    $("dots").innerHTML = STEPS.map((_, i) => `<i class="${i <= step ? "on" : ""}"></i>`).join("");
    $("wBack").style.visibility = step ? "visible" : "hidden";
    $("wNext").textContent = step === STEPS.length - 1 ? "Show recipes →" : "Next →";
    let body = "";
    if (s.id === "people") body = `<div class="big-num"><button data-n="-1" aria-label="Fewer">−</button><span class="v" id="nv">${q.people}</span><button data-n="1" aria-label="More">+</button></div>
      <div class="people-row" id="pr"></div><div class="quick" style="margin-top:14px">${[1, 2, 3, 4, 6].map(n => `<button class="pill ${q.people === n ? "active" : ""}" data-set="${n}">${n}</button>`).join("")}</div>`;
    if (s.id === "budget") body = `<div style="position:relative"><input class="input budget-input mono" id="bud" inputmode="numeric" value="${q.budget_rupees}" aria-label="Budget in rupees"></div>
      <p class="center faint small">₹200 – ₹20,000</p><div class="quick">${[500, 1000, 1500, 2000, 3000, 5000].map(n => `<button class="pill ${q.budget_rupees === n ? "active" : ""}" data-bud="${n}">₹${n.toLocaleString("en-IN")}</button>`).join("")}</div>
      <p class="center muted" id="perHead" style="margin-top:16px"></p>`;
    if (s.id === "days") body = `<div class="big-num"><button data-n="-1" aria-label="Fewer">−</button><span class="v" id="nv">${q.days}</span><button data-n="1" aria-label="More">+</button></div>
      <p class="center muted">${q.days === 1 ? "day" : "days"} · ${q.days * q.meals.length} meal${q.days * q.meals.length === 1 ? "" : "s"} to plan</p>`;
    if (s.id === "meals") body = `<div class="flips">${MEALS.map(([v, l, ic, d]) => flipCard(v, l, ic, q.meals.includes(v), d, "data-meal")).join("")}</div>`;
    if (s.id === "appliances") body = `<div class="flips">${opts.appliances.map(a => flipCard(a.id, a.label, a.icon, q.appliances.includes(a.id), "", "data-app")).join("")}</div>`;
    if (s.id === "diet") body = `<div class="flips wide">${opts.diets.map(d => flipCard(d.id, d.label, DIET_IC[d.id] || "🍽️", q.diet === d.id, "", "data-diet")).join("")}</div>`;
    if (s.id === "goal") body = `<div class="flips wide">${opts.goals.map(g => flipCard(g.id, g.label, GOAL_IC[g.id] || "🎯", q.goal === g.id, "", "data-goal")).join("")}</div>`;
    if (s.id === "pantry") body = `<div class="flips wide">${flipCard("1", "Yes, I have them", "🫙", q.pantry, "Skip salt, oil, sugar, spices", "data-pantry")}${flipCard("0", "No, add them", "🛒", !q.pantry, "Buy everything", "data-pantry")}</div>`;
    $("wizCard").innerHTML = `<div class="step show ${dirBack ? "back" : ""}"><div class="eyebrow">Step ${step + 1} of ${STEPS.length}</div><h2>${s.title}</h2><p class="sub">${s.sub}</p>${body}<div class="err" id="wErr" style="margin-top:12px"></div></div>`;
    if (s.id === "people") drawPeople();
    if (s.id === "budget") { perHead(); const b = $("bud"); b.addEventListener("input", () => { b.value = b.value.replace(/\D/g, "").slice(0, 5); q.budget_rupees = Number(b.value) || 0; perHead(); }); }
  }
  function drawPeople() { $("pr").innerHTML = Array.from({ length: q.people }, (_, i) => `<span style="animation-delay:${i * .03}s">${["🧑", "👩", "👨", "👧", "👦", "👵", "👴"][i % 7]}</span>`).join(""); }
  function perHead() { const el = $("perHead"); if (el) el.textContent = q.budget_rupees >= 200 ? `≈ ₹${Math.round(q.budget_rupees / q.people / q.days).toLocaleString("en-IN")} per person per day` : ""; }
  $("wizCard").addEventListener("click", e => {
    const t = e.target.closest("button"); if (!t) return;
    const id = STEPS[step].id;
    if (t.dataset.n) {
      const [k, lo, hi] = id === "people" ? ["people", 1, 20] : ["days", 1, 7];
      q[k] = Math.max(lo, Math.min(hi, q[k] + Number(t.dataset.n)));
      const v = $("nv"); v.textContent = q[k]; v.classList.remove("flip"); void v.offsetWidth; v.classList.add("flip");
      if (id === "people") drawPeople(); else drawStep();
      BD.buzz(8);
    }
    if (t.dataset.set) { q.people = Number(t.dataset.set); drawStep(); }
    if (t.dataset.bud) { q.budget_rupees = Number(t.dataset.bud); drawStep(); }
    const toggle = (arr, v) => arr.includes(v) ? arr.filter(x => x !== v) : arr.concat(v);
    if (t.dataset.meal) { q.meals = toggle(q.meals, t.dataset.meal); flipTo(t, q.meals.includes(t.dataset.meal)); }
    if (t.dataset.app) { q.appliances = toggle(q.appliances, t.dataset.app); flipTo(t, q.appliances.includes(t.dataset.app)); }
    if (t.dataset.diet) { q.diet = t.dataset.diet; single(t, "data-diet"); }
    if (t.dataset.goal) { q.goal = t.dataset.goal; single(t, "data-goal"); }
    if (t.dataset.pantry) { q.pantry = t.dataset.pantry === "1"; single(t, "data-pantry"); }
    save();
  });
  function flipTo(el, on) { el.classList.toggle("on", on); el.setAttribute("aria-pressed", on); BD.buzz(10); BD.sound.unlock(); BD.sound.chime("tap"); }
  function single(el, attr) { $("wizCard").querySelectorAll(`[${attr}]`).forEach(b => flipTo(b, b === el)); }
  function validStep() {
    const id = STEPS[step].id, err = $("wErr");
    if (id === "budget" && !(q.budget_rupees >= 200 && q.budget_rupees <= 20000)) { err.textContent = "Budget must be between ₹200 and ₹20,000"; return false; }
    if (id === "meals" && !q.meals.length) { err.textContent = "Pick at least one meal"; return false; }
    if (id === "appliances" && !q.appliances.length) { err.textContent = "Pick at least one thing you cook with"; return false; }
    return true;
  }
  $("wNext").addEventListener("click", () => {
    if (!validStep()) return;
    save();
    if (step < STEPS.length - 1) { step++; dirBack = false; drawStep(); return; }
    recipes = []; loadRecipes();
  });
  $("wBack").addEventListener("click", () => { if (step) { step--; dirBack = true; drawStep(); } });

  // wizard by voice: AI only fills the fields; the shopper still reviews every step
  let vSheet = null, vRec = null;
  $("wVoice").addEventListener("click", () => {
    if (!vSheet) {
      vSheet = document.createElement("div"); vSheet.className = "sheet"; vSheet.id = "planVoice"; vSheet.setAttribute("role", "dialog");
      vSheet.innerHTML = `<div class="grab"></div><h3 class="center">Tell me your plan</h3><p class="muted small center" style="margin:4px 0 0">“4 people, 1500 rupees, 2 days, veg, high protein, stove and pressure cooker”</p>
        <button class="v-orb" id="pvOrb" aria-label="Tap to talk">🎙</button><p class="heard" id="pvHeard"></p>
        <form class="row" id="pvForm"><input class="input grow" id="pvText" maxlength="300" placeholder="…or type it"><button class="btn-ghost">Go</button></form><div id="pvOut" style="margin-top:12px"></div>`;
      document.body.appendChild(vSheet);
      $("pvOrb").onclick = async () => {
        if (!BD.canRecord) { $("pvText").focus(); return; }
        if (vRec && vRec.recording) { vRec.stop(); return; }
        vRec = BD.recorder(l => $("pvOrb").style.setProperty("--lvl", l.toFixed(3)));
        $("pvOrb").classList.add("rec"); $("pvHeard").textContent = "Listening… tap again when done";
        let blob; try { blob = await vRec.start(15000); } catch (e) { $("pvOrb").classList.remove("rec"); $("pvHeard").textContent = "Microphone blocked. Type instead."; return; }
        $("pvOrb").classList.remove("rec"); if (!blob) return;
        const fd = new FormData(); fd.append("audio", blob, "voice.wav"); sendPlanVoice(fd);
      };
      $("pvForm").onsubmit = e => { e.preventDefault(); const t = $("pvText").value.trim(); if (!t) return; const fd = new FormData(); fd.append("text", t); sendPlanVoice(fd); };
      const prev = S.onClose; S.onClose = () => { prev && prev(); if (vRec && vRec.recording) vRec.stop(); };
    }
    $("pvOut").innerHTML = ""; $("pvHeard").textContent = BD.canRecord ? "Tap the mic and speak" : "Type your plan below (the mic needs HTTPS).";
    S.openSheet("planVoice");
  });
  async function sendPlanVoice(fd) {
    $("pvOrb").classList.add("think"); $("pvOut").innerHTML = "";
    try {
      const r = await S.timed(BD.api(S.api + "/planner/voice", { form: fd }));
      $("pvHeard").textContent = r.transcript ? `“${r.transcript}”` : "";
      const f = r.fields || {}, keys = Object.keys(f);
      if (!keys.length) { $("pvOut").innerHTML = `<div class="notice">${BD.esc(r.error || "I couldn't pick out the details. Please tap the options.")}</div>`; return; }
      const label = { people: "People", budget_rupees: "Budget", days: "Days", meals: "Meals", appliances: "Cooking with", diet: "Food", goal: "Goal" };
      const show = (k, v) => k === "budget_rupees" ? "₹" + Number(v).toLocaleString("en-IN") : k === "appliances" ? v.map(a => (opts.appliances.find(x => x.id === a) || {}).label || a).join(", ")
        : k === "goal" ? (opts.goals.find(g => g.id === v) || {}).label : k === "diet" ? (opts.diets.find(d => d.id === v) || {}).label : Array.isArray(v) ? v.join(", ") : v;
      $("pvOut").innerHTML = `<div class="glass" style="padding:10px 14px;border-radius:16px">${keys.map(k => `<div class="row spread" style="padding:5px 0"><span class="muted">${label[k]}</span><b>${BD.esc(show(k, f[k]))}</b></div>`).join("")}</div>
        <div class="row" style="margin-top:12px"><button class="btn grow" id="pvUse">Use these</button><button class="btn-ghost" data-close>Cancel</button></div>`;
      $("pvUse").onclick = () => { Object.assign(q, f); save(); S.closeSheets(); step = 0; dirBack = false; drawStep(); BD.toast("Filled in. Check each step and tap Next.", "ok"); };
    } catch (x) { $("pvOut").innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; }
    finally { $("pvOrb").classList.remove("think"); }
  }

  // ---------------------------------------------------------------- recipes
  const planBody = () => ({ people: q.people, days: q.days, budget_rupees: q.budget_rupees, meals: q.meals, appliances: q.appliances, diet: q.diet, goal: q.goal, pantry: q.pantry });
  async function loadRecipes() {
    BD.busy($("wNext"), true, "Finding recipes…");
    try {
      const r = await BD.api(S.api + "/planner/recipes", { body: planBody() });
      recipes = r.recipes;
      const ids = new Set(recipes.map(x => x.id)); selected = new Set([...selected].filter(x => ids.has(x))); save();
      if (location.hash !== "#recipes") location.hash = "recipes";
      S.show("recipes"); drawRecipes();
      BD.toast(`${recipes.length} recipes fit your kitchen`, "ok");
    } catch (x) { BD.toast(x.message, "bad"); S.go("plan"); }
    finally { BD.busy($("wNext"), false); }
  }
  function drawRecipes() {
    const goal = (opts.goals.find(g => g.id === q.goal) || {}).label || "";
    $("rTitle").innerHTML = `${recipes.length} recipes · <span class="hot-text serif-i">${BD.esc(goal)}</span>`;
    $("rfilt").innerHTML = [["all", "All"], ["selected", "✓ Selected"], ["quick", "⏱ ≤ 30 min"]].concat(MEALS.filter(m => q.meals.includes(m[0])).map(m => [m[0], m[2] + " " + m[1]]))
      .map(([k, l]) => `<button class="pill ${rFilter === k ? "active" : ""}" data-rf="${k}">${l}</button>`).join("");
    const list = recipes.filter(r => (rFilter === "all" || (rFilter === "selected" ? selected.has(r.id) : rFilter === "quick" ? r.time_min <= 30 : r.meal.includes(rFilter)))
      && (!rQuery || (r.name + " " + Object.values(r.name_local || {}).join(" ")).toLowerCase().includes(rQuery)));
    $("rgrid").innerHTML = list.length ? list.map((r, i) => `<div class="glass rcard ${selected.has(r.id) ? "on" : ""}" data-tilt="6" data-rid="${r.id}" style="--h:${BD.hueFor(r.name)};animation-delay:${Math.min(i, 12) * .035}s">
      <div class="ph">${S.pic(r.photo, BD.foodEmoji(r.name), r.photo_credit)}<span class="time chip">⏱ ${r.time_min} min</span></div>
      <button class="sel" data-sel="${r.id}" aria-label="${selected.has(r.id) ? "Remove" : "Add"} ${BD.esc(r.name)}" aria-pressed="${selected.has(r.id)}">${selected.has(r.id) ? "✓" : "+"}</button>
      <div class="body"><div class="nm">${BD.esc(r.name)}</div>
        <div class="nut"><span><b>${r.nutrition.kcal}</b> kcal</span><span><b>${r.nutrition.protein_g} g</b> protein</span><span><b>${r.nutrition.carbs_g} g</b> carbs</span></div>
        ${r.badges.length ? `<div class="badges">${r.badges.map(b => `<span>${BD.esc(b)}</span>`).join("")}</div>` : ""}
        <div class="row spread"><span class="faint small">${r.appliances.slice(0, 3).map(a => (opts.appliances.find(x => x.id === a) || {}).icon || "").join(" ")}</span><span class="cost">≈ ${BD.rupees(r.cost_paise)}</span></div></div></div>`).join("")
      : `<div class="glass card center" style="grid-column:1/-1"><p class="muted">${recipes.length ? "No recipes match this filter." : "No recipes fit these appliances and food choices. Try adding a cooking appliance."}</p><button class="btn-ghost" data-go="plan">Change plan</button></div>`;
    BD.tilt($("rgrid")); drawBudget();
  }
  function drawBudget() {
    const budget = q.budget_rupees * 100;
    const est = recipes.filter(r => selected.has(r.id)).reduce((s, r) => s + r.cost_paise, 0);
    const pct = budget ? est / budget : 0;
    const bar = $("bbar");
    bar.classList.toggle("amber", pct > 0.9 && pct <= 1); bar.classList.toggle("red", pct > 1);
    bar.querySelector(".meter i").style.setProperty("--p", Math.min(100, pct * 100).toFixed(1) + "%");
    $("bbText").textContent = selected.size ? `≈ ${BD.rupees(est)} of ${BD.rupees(budget)}${pct > 1 ? " · over budget" : ""}` : `Budget ${BD.rupees(budget)} · pick recipes`;
    const chosen = recipes.filter(r => selected.has(r.id) && r.meal.some(m => q.meals.includes(m))).length, need = q.days * q.meals.length;
    $("bbCover").textContent = `${selected.size} selected · meals for ${Math.min(chosen, need)} of ${need}`;
    $("bbPeople").textContent = `${q.people} ${q.people === 1 ? "person" : "people"}`;
    $("toCart").disabled = !selected.size;
    $("toCart").textContent = selected.size ? `Build my cart (${selected.size}) →` : "Build my cart →";
  }
  $("rfilt").addEventListener("click", e => { const b = e.target.closest("[data-rf]"); if (!b) return; rFilter = b.dataset.rf; drawRecipes(); });
  let rqT; $("rq").addEventListener("input", e => { clearTimeout(rqT); rqT = setTimeout(() => { rQuery = e.target.value.trim().toLowerCase(); drawRecipes(); }, 120); });
  $("rgrid").addEventListener("click", e => {
    const s = e.target.closest("[data-sel]");
    if (s) { e.stopPropagation(); toggleSel(s.dataset.sel); return; }
    const c = e.target.closest("[data-rid]"); if (c) openRecipe(c.dataset.rid);
  });
  function toggleSel(id) {
    if (selected.has(id)) selected.delete(id); else { selected.add(id); BD.sound.unlock(); BD.sound.chime("tap"); }
    BD.buzz(10); save(); removed.clear(); swaps = {}; fill = false;
    const c = document.querySelector(`.rcard[data-rid="${id}"]`);
    if (c && rFilter !== "selected") { const on = selected.has(id); c.classList.toggle("on", on); const b = c.querySelector(".sel"); b.textContent = on ? "✓" : "+"; b.setAttribute("aria-pressed", on); drawBudget(); }
    else drawRecipes();
  }
  $("toCart").addEventListener("click", () => { removed.clear(); swaps = {}; fill = false; S.go("pcart"); });

  // ---------------------------------------------------------------- recipe detail, read aloud, hands-free
  let rd = null, rdLang = "en-IN", nowStep = -1, hf = false, speaking = null, hfRec = null;
  async function openRecipe(id, lang) {
    rdLang = lang || rdLang;
    stopAll();
    $("rd").innerHTML = `<div style="padding:60px 0"><div class="loader-orb"><i></i><i></i><i></i><b></b></div></div>`;
    S.openSheet("recipeSheet");
    const get = lang => BD.api(`${S.api}/planner/recipe/${encodeURIComponent(id)}?people=${q.people}&lang=${lang}`);
    try { rd = await S.timed(get(rdLang), rdLang === "en-IN" ? 15000 : 25000); }
    catch (x) {
      if (rdLang === "en-IN") { $("rd").innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; return; }
      BD.toast("Translation is taking long, showing English for now. Try the language again in a moment.", "info", 6000);
      rdLang = "en-IN";
      try { rd = await get("en-IN"); } catch (y) { $("rd").innerHTML = `<div class="notice bad">${BD.esc(y.message)}</div>`; return; }
    }
    drawRecipe();
  }
  function drawRecipe() {
    const r = rd, n = r.nutrition, on = selected.has(r.id);
    const local = (r.name_local || {})[rdLang.slice(0, 2)];
    const yt = r.youtube_id
      ? `<div class="yt-embed"><iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(r.youtube_id)}" title="${BD.esc(r.name)} video" loading="lazy" allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>`
      : `<a class="yt-card" href="${BD.esc(r.youtube_search)}" target="_blank" rel="noopener"><span class="yt-thumb" style="${r.photo ? `background-image:url('${BD.esc(r.photo)}')` : ""}"></span>
         <span><b>Watch how to make it</b><span class="muted small" style="display:block">Opens YouTube videos for “${BD.esc(r.name)}”</span></span></a>`;
    $("rd").innerHTML = `<div class="rd-hero" style="--h:${BD.hueFor(r.name)}">${S.pic(r.photo, BD.foodEmoji(r.name), r.photo_credit)}</div>
      <div class="row spread wrap" style="gap:10px"><div><h2 id="rdName">${BD.esc(r.name)}</h2>${local ? `<div class="muted">${BD.esc(local)}</div>` : ""}
        <div class="faint small" style="margin-top:4px">⏱ ${r.time_min} min · for ${r.people} ${r.people === 1 ? "person" : "people"} · ≈ ${BD.rupees(r.cost_paise)}</div></div>
        <button class="btn ${on ? "mint" : ""}" id="rdSel">${on ? "✓ In my plan" : "+ Add to plan"}</button></div>
      <div class="nut-grid"><div><b>${n.kcal}</b><span>kcal</span></div><div><b>${n.protein_g}g</b><span>protein</span></div><div><b>${n.carbs_g}g</b><span>carbs</span></div><div><b>${n.fat_g}g</b><span>fat</span></div><div><b>${n.fibre_g}g</b><span>fibre</span></div></div>
      <p class="faint small" style="margin:-4px 0 14px">Per serving, approx. Source: ${BD.esc((r.nutrition_sources || []).join("; "))}</p>
      ${yt}
      <h3 style="margin:20px 0 8px">Ingredients</h3>
      <ul class="ing-list">${r.ingredients.map(i => `<li><span>${BD.esc((i.name_local || {})[rdLang.slice(0, 2)] || i.name)}${i.staple ? ' <span class="faint small">(staple)</span>' : ""}</span><b class="mono">${fmtQty(i)}</b></li>`).join("")}</ul>
      <div class="row spread wrap" style="margin:20px 0 8px"><h3>Steps</h3><div class="row" style="gap:6px">${LANGS.map(([k, l]) => `<button class="pill ${k === rdLang ? "active" : ""}" data-lang="${k}" style="padding:6px 12px">${l}</button>`).join("")}</div></div>
      <div class="hf-bar" id="hfBar"><button class="btn-ghost sm" id="readAll">🔊 Read aloud</button><button class="btn-ghost sm" id="hfOn">🖐 Hands-free</button>
        <span class="grow"></span><button class="btn-ghost sm" data-hf="previous" aria-label="Previous step">⏮</button><button class="btn-ghost sm" data-hf="repeat" aria-label="Repeat step">🔁</button><button class="btn-ghost sm" data-hf="next" aria-label="Next step">⏭</button>
        <span class="faint small" id="hfMsg" style="flex-basis:100%"></span></div>
      <ol class="steps-list" id="stepList">${r.steps.map((s, i) => `<li data-step="${i}">${BD.esc(s)}</li>`).join("")}</ol>`;
    $("rdSel").onclick = () => { toggleSel(r.id); drawRecipe(); };
    $("readAll").onclick = () => { hf = false; readFrom(Math.max(0, nowStep), true); };
    $("hfOn").onclick = () => { if (hf) { stopAll(); return; } hf = true; $("hfBar").classList.add("live"); $("hfOn").textContent = "■ Stop hands-free"; readFrom(Math.max(0, nowStep), false); };
  }
  const fmtQty = i => i.unit === "g" && i.qty >= 1000 ? (i.qty / 1000).toFixed(1).replace(/\.0$/, "") + " kg" : i.unit === "ml" && i.qty >= 1000 ? (i.qty / 1000).toFixed(1).replace(/\.0$/, "") + " L" : i.qty + " " + (i.unit === "pcs" ? "" : i.unit);
  $("rd").addEventListener("click", e => {
    const l = e.target.closest("[data-lang]"); if (l && rd) { const keep = nowStep; openRecipe(rd.id, l.dataset.lang).then(() => { if (keep >= 0) mark(keep); }); return; }
    const h = e.target.closest("[data-hf]"); if (h) { command(h.dataset.hf, true); return; }
    const s = e.target.closest("[data-step]"); if (s) { stopSpeech(); readFrom(Number(s.dataset.step), false, true); }
  });
  function mark(i) {
    nowStep = i;
    document.querySelectorAll("#stepList li").forEach((li, k) => li.classList.toggle("now", k === i));
    const li = document.querySelector(`#stepList li[data-step="${i}"]`); if (li) li.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function stopSpeech() { if (speaking) { try { speaking.pause(); } catch (e) {} speaking = null; } try { speechSynthesis.cancel(); } catch (e) {} }
  function stopAll() {
    hf = false; stopSpeech(); if (hfRec && hfRec.recording) hfRec.stop();
    const bar = $("hfBar"); if (bar) { bar.classList.remove("live"); $("hfOn").textContent = "🖐 Hands-free"; $("hfMsg").textContent = ""; }
  }
  const prevClose = S.onClose; S.onClose = () => { prevClose && prevClose(); stopAll(); };
  async function say(text) {
    stopSpeech();
    const browserSay = () => new Promise(res => {
      try { const u = new SpeechSynthesisUtterance(text); u.lang = rdLang; u.rate = .95; u.onend = res; u.onerror = res; speechSynthesis.speak(u); } catch (e) { res(); }
    });
    if (!S.info.features.tts) return browserSay();
    try {
      const r = await S.timed(BD.api(S.api + "/tts", { body: { text, lang: rdLang } }));
      return await new Promise(res => { const a = new Audio(r.audio); speaking = a; a.onended = res; a.onerror = res; a.play().catch(res); });
    } catch (e) { return browserSay(); }
  }
  let readToken = 0;
  async function readFrom(i, continuous, single) {
    const my = ++readToken;
    if (!rd || i < 0 || i >= rd.steps.length) return;
    mark(i);
    await say(`${rdLang === "kn-IN" ? "ಹಂತ" : rdLang === "hi-IN" ? "चरण" : "Step"} ${i + 1}. ${rd.steps[i]}`);
    if (my !== readToken || single) return;
    if (continuous && !hf) { if (i + 1 < rd.steps.length) readFrom(i + 1, true); return; }
    if (hf) listen(my);
  }
  async function listen(my) {
    if (!BD.canRecord) { $("hfMsg").textContent = "Tap ⏭ 🔁 ⏮ to move (voice commands need HTTPS)."; return; }
    for (let tries = 0; hf && my === readToken && tries < 4; tries++) {
      $("hfMsg").textContent = "Listening… say “next”, “repeat” or “previous” (ಮುಂದೆ / आगे)";
      hfRec = BD.recorder();
      let blob; try { blob = await hfRec.start(3500); } catch (e) { $("hfMsg").textContent = "Microphone blocked. Use the buttons."; return; }
      if (!hf || my !== readToken || !blob) return;
      try {
        const fd = new FormData(); fd.append("audio", blob, "cmd.wav"); fd.append("language", rdLang);
        const r = await S.timed(BD.api(S.api + "/planner/command", { form: fd }));
        if (r.command) return command(r.command);
      } catch (e) { $("hfMsg").textContent = e.message; }
    }
    if (hf && my === readToken) $("hfMsg").textContent = "Paused. Tap ⏭ when you're ready.";
  }
  function command(cmd, tapped) {
    if (!rd) return;
    if (cmd === "stop") return stopAll();
    let i = nowStep < 0 ? 0 : nowStep;
    if (cmd === "next") { if (i + 1 >= rd.steps.length) { $("hfMsg").textContent = "That was the last step. Enjoy your meal! 🎉"; BD.confetti(80); hf = false; return; } i++; }
    if (cmd === "previous") i = Math.max(0, i - 1);
    stopSpeech();
    readFrom(i, false, tapped && !hf);
  }

  // ---------------------------------------------------------------- plan cart
  async function loadCart() {
    $("pcLines").innerHTML = `<div style="padding:50px 0"><div class="loader-orb"><i></i><i></i><i></i><b></b></div></div>`;
    try {
      lastCart = await BD.api(S.api + "/planner/cart", { body: Object.assign(planBody(), { recipe_ids: [...selected], removed_skus: [...removed], swaps, fill }) });
      drawCart();
    } catch (x) { $("pcLines").innerHTML = `<div class="notice bad">${BD.esc(x.message)}</div>`; }
  }
  function drawCart() {
    const c = lastCart, added = c.filled ? c.fit.add : [];
    const lines = c.lines.map((l, i) => `<div class="pc-line" style="animation-delay:${Math.min(i, 14) * .03}s"><div class="th">${S.pic(l.image_url, S.emoji(l.name))}</div>
      <div><b>${l.packs} × ${BD.esc(l.name)}</b><div class="faint small">needs ${fmtQty({ qty: Math.round(l.needed_qty), unit: l.pack_unit })}${l.leftover_qty > 0 ? ` · ${fmtQty({ qty: Math.round(l.leftover_qty), unit: l.pack_unit })} left over` : ""}</div>
        ${l.alternatives.length ? `<select class="input input-sm sw" data-swap="${l.sku}" aria-label="Swap pack"><option value="">Swap pack…</option>${l.alternatives.map(a => `<option value="${a.sku}">${BD.esc(a.name)} · ${BD.rupees(a.price_paise)}</option>`).join("")}</select>` : ""}</div>
      <b class="mono">${BD.rupees(l.line_total)}</b><button class="btn-ghost sm" data-rm="${l.sku}" aria-label="Remove ${BD.esc(l.name)}">✕</button></div>`).join("");
    const adds = added.map((a, i) => `<div class="pc-line added" style="animation-delay:${.2 + i * .08}s"><div class="th" style="background:rgba(46,230,166,.12)">${S.emoji(a.name)}</div>
      <div><b>${a.packs} × ${BD.esc(a.name)}</b><div class="small" style="color:var(--mint)">added to fill your budget</div></div><b class="mono">${BD.rupees(a.line_total)}</b><span></span></div>`).join("");
    $("pcLines").innerHTML = `<div class="row spread"><h3>${c.lines.length + added.length} items</h3>${removed.size || Object.keys(swaps).length ? `<button class="btn-ghost sm" id="pcReset">Undo my edits</button>` : ""}</div>
      ${lines}${adds}
      ${c.missing.length ? `<div class="notice" style="margin-top:12px">Not sold in this store: ${BD.esc(c.missing.map(m => m.name).join(", "))}. Buy these elsewhere or skip them.</div>` : ""}
      ${q.pantry ? `<p class="faint small" style="margin-top:10px">Salt, oil, sugar and spices are skipped (you said you have them).</p>` : ""}`;
    const over = c.total_paise > c.budget_paise;
    $("pcSum").innerHTML = `<div class="eyebrow">${c.filled ? "Filled to budget" : "Cart total"}</div>
      <div style="font-family:var(--font-display);font-size:2.8rem;line-height:1.1;margin:6px 0" class="mono" id="pcTotal" data-v="${drawCart.last || 0}">${BD.rupees(drawCart.last || 0)}</div>
      <p class="${over ? "" : "muted"}" style="${over ? "color:#ff8fa3" : ""};margin:0 0 14px">${BD.esc(c.message)}</p>
      ${!c.fit.ok ? c.fit.suggestions.map(s => `<div class="sugg"><span class="small">${BD.esc(s.text)}</span><button class="btn-ghost sm" data-sug='${BD.esc(JSON.stringify(s))}'>Do it</button></div>`).join("")
        : c.filled ? `<button class="btn-ghost block" id="unfill">Undo fill</button>`
        : `<button class="btn mint block" id="fillBtn">✨ Fill to budget</button><p class="faint small center" style="margin:6px 0 0">Adds fruit, snacks or staples so you land ₹20–30 under. Never over.</p>`}
      <button class="btn lg block" id="pcPay" style="margin-top:14px" ${over || !S.info.features.online_payment || !(c.lines.length + added.length) ? "disabled" : ""}>Pay ${BD.rupees(c.total_paise)} →</button>
      ${S.info.features.online_payment ? "" : `<p class="faint small center">Online payment isn't set up for this store yet.</p>`}`;
    S.countUp($("pcTotal"), c.total_paise, 900); drawCart.last = c.total_paise;
    const cv = c.coverage, pct = cv.slots_needed ? Math.min(100, Math.round(cv.slots_chosen * 100 / cv.slots_needed)) : 0;
    $("pcCover").innerHTML = `<div class="row"><div class="cover-ring" style="--p:${pct}"><span>${pct}%</span></div><div><b>Meal coverage</b><p class="muted small" style="margin:4px 0 0">${BD.esc(cv.text)}</p></div></div>
      <div class="row wrap" style="gap:6px;margin-top:12px">${recipes.filter(r => selected.has(r.id)).map(r => `<span class="chip">${BD.foodEmoji(r.name)} ${BD.esc(r.name)}</span>`).join("")}</div>`;
    if (c.filled && c.fit.in_window) BD.confetti(90);
  }
  $("vPCart").addEventListener("change", e => { const s = e.target.closest("[data-swap]"); if (s && s.value) { swaps[s.dataset.swap] = Number(s.value); fill = false; loadCart(); } });
  $("vPCart").addEventListener("click", e => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.rm) { removed.add(Number(t.dataset.rm)); fill = false; loadCart(); }
    if (t.id === "pcReset") { removed.clear(); swaps = {}; fill = false; loadCart(); }
    if (t.id === "fillBtn") { fill = true; BD.busy(t, true, "Filling…"); loadCart(); }
    if (t.id === "unfill") { fill = false; loadCart(); }
    if (t.dataset.sug) {
      const s = JSON.parse(t.dataset.sug);
      if (s.type === "remove_recipe") { selected.delete(s.recipe_id); save(); }
      if (s.type === "swap") swaps[s.from_sku] = s.to_sku;
      fill = false;
      if (!selected.size) return S.go("recipes");
      loadCart();
    }
    if (t.id === "pcPay") {
      const c = lastCart;
      const items = c.lines.map(l => ({ product_id: l.sku, packs: l.packs })).concat(c.filled ? c.fit.add.map(a => ({ product_id: a.sku, packs: a.packs })) : []);
      S.checkout(items, c.total_paise, "planner", { people: q.people, days: q.days, budget_rupees: q.budget_rupees, recipes: [...selected] });
    }
  });
})();
