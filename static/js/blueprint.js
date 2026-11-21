/* Blueprint reader helpers (browser side).
   - traceWalls: finds the thick wall lines in the floor-plan image itself (pixels), so the 3D walls follow the drawing
     exactly, with door gaps left open. No AI.
   - refine: checks every AI-proposed table, counter and room against the drawing and drops what isn't really there.
   - matchTables: pairs detected tables with the restaurant's tables ("T4" -> table 4, the rest in reading order).
   Everything returned is a proposal; the owner taps Apply before anything is saved. */
(function () {
  "use strict";

  async function load(url) {
    const img = new Image(); img.decoding = "async"; img.src = url;
    await img.decode();
    const W = Math.min(900, img.naturalWidth), H = Math.max(1, Math.round(W * img.naturalHeight / img.naturalWidth));
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(img, 0, 0, W, H);
    const px = g.getImageData(0, 0, W, H).data, lum = new Uint8Array(W * H), hist = new Uint32Array(256);
    for (let i = 0; i < W * H; i++) { const l = (px[i * 4] * 299 + px[i * 4 + 1] * 587 + px[i * 4 + 2] * 114) / 1000 | 0; lum[i] = l; hist[l]++; }
    let bg = 0; for (let l = 1; l < 256; l++) if (hist[l] > hist[bg]) bg = l;   // most common shade = paper
    const diff = i => Math.abs(lum[i] - bg);
    const ink = new Uint8Array(W * H), soft = new Uint8Array(W * H);
    for (let i = 0; i < W * H; i++) { const d = diff(i); ink[i] = d > 70 ? 1 : 0; soft[i] = d > 32 ? 1 : 0; }
    return { W, H, ink, soft, aspect: img.naturalWidth / img.naturalHeight };
  }

  // ---------------------------------------------------------------- walls from pixels
  function traceWalls(im) {
    const { W, H, ink } = im;
    const tMin = Math.max(3, Math.round(W * 0.0042)), tMax = Math.round(W * 0.03), lMin = Math.round(W * 0.03);
    const vrun = new Uint16Array(W * H), hrun = new Uint16Array(W * H);
    for (let x = 0; x < W; x++) for (let y = 0; y < H;) { if (!ink[y * W + x]) { y++; continue; } let e = y; while (e < H && ink[e * W + x]) e++; for (let k = y; k < e; k++) vrun[k * W + x] = e - y; y = e; }
    for (let y = 0; y < H; y++) for (let x = 0; x < W;) { if (!ink[y * W + x]) { x++; continue; } let e = x; while (e < W && ink[y * W + e]) e++; for (let k = x; k < e; k++) hrun[y * W + k] = e - x; x = e; }
    const mask = new Uint8Array(W * H), walls = [];
    // horizontal walls: thick vertically (tMin..tMax), long horizontally
    const grow = (rows, horiz) => {
      // rows: [{a: line index, s, e}] runs per scan line; merge adjacent lines into bands
      const bands = [];
      rows.forEach(r => {
        const b = bands.find(b => b.last === r.a - 1 && Math.min(b.e, r.e) - Math.max(b.s, r.s) > 0.6 * Math.min(b.e - b.s, r.e - r.s));
        if (b) { b.last = r.a; b.n++; b.s = Math.min(b.s, r.s); b.e = Math.max(b.e, r.e); b.sum += r.a; } else bands.push({ first: r.a, last: r.a, n: 1, s: r.s, e: r.e, sum: r.a });
      });
      bands.filter(b => b.n >= tMin).forEach(b => {
        const mid = b.sum / b.n, th = b.n;
        if (horiz) { walls.push([b.s / W * 100, mid / H * 100, b.e / W * 100, mid / H * 100, th / W * 100]); for (let y = b.first; y <= b.last; y++) for (let x = b.s; x < b.e; x++) mask[y * W + x] = 1; }
        else { walls.push([mid / W * 100, b.s / H * 100, mid / W * 100, b.e / H * 100, th / W * 100]); for (let x = b.first; x <= b.last; x++) for (let y = b.s; y < b.e; y++) mask[y * W + x] = 1; }
      });
    };
    const hRows = [];
    for (let y = 0; y < H; y++) for (let x = 0; x < W;) {
      const ok = i => ink[i] && vrun[i] >= tMin && vrun[i] <= tMax;
      if (!ok(y * W + x)) { x++; continue; } let e = x; while (e < W && ok(y * W + e)) e++; if (e - x >= lMin) hRows.push({ a: y, s: x, e }); x = e;
    }
    const vRows = [];
    for (let x = 0; x < W; x++) for (let y = 0; y < H;) {
      const ok = i => ink[i] && hrun[i] >= tMin && hrun[i] <= tMax;
      if (!ok(y * W + x)) { y++; continue; } let e = y; while (e < H && ok(e * W + x)) e++; if (e - y >= lMin) vRows.push({ a: x, s: y, e }); y = e;
    }
    grow(hRows, true); grow(vRows, false);
    const round = v => Math.round(v * 100) / 100;
    return { walls: walls.slice(0, 160).map(w => w.map(round)), mask };
  }

  // ---------------------------------------------------------------- checking proposals against the drawing
  function hit(im, layer, x, y, tol) {
    const { W, H } = im;
    for (let dy = -tol; dy <= tol; dy++) for (let dx = -tol; dx <= tol; dx++) {
      const xx = x + dx, yy = y + dy;
      if (xx >= 0 && yy >= 0 && xx < W && yy < H && layer[yy * W + xx]) return true;
    }
    return false;
  }
  function rectScore(im, layer, r, tol) {   // r in %, fraction of its border that lies on drawn lines
    const { W, H } = im, x1 = r.x / 100 * W, y1 = r.y / 100 * H, x2 = (r.x + r.w) / 100 * W, y2 = (r.y + r.h) / 100 * H;
    let n = 0, ok = 0;
    for (let x = x1; x <= x2; x += 2) { n += 2; ok += hit(im, layer, x | 0, y1 | 0, tol) + hit(im, layer, x | 0, y2 | 0, tol); }
    for (let y = y1; y <= y2; y += 2) { n += 2; ok += hit(im, layer, x1 | 0, y | 0, tol) + hit(im, layer, x2 | 0, y | 0, tol); }
    return n ? ok / n : 0;
  }
  function ellipseScore(im, layer, r, tol) {
    const { W, H } = im, cx = (r.x + r.w / 2) / 100 * W, cy = (r.y + r.h / 2) / 100 * H, rx = r.w / 200 * W, ry = r.h / 200 * H;
    let ok = 0; const N = 48;
    for (let i = 0; i < N; i++) { const a = i / N * Math.PI * 2; ok += hit(im, layer, Math.round(cx + Math.cos(a) * rx), Math.round(cy + Math.sin(a) * ry), tol); }
    return ok / N;
  }
  function tableScore(im, t) {
    const r = { x: t.x - t.w / 2, y: t.y - t.h / 2, w: t.w, h: t.h }, tol = Math.max(2, Math.round(im.W * 0.004));
    // the detected box may include the chairs: also try the inner 60 %
    const inner = { x: t.x - t.w * 0.3, y: t.y - t.h * 0.3, w: t.w * 0.6, h: t.h * 0.6 };
    return Math.max(ellipseScore(im, im.soft, r, tol), rectScore(im, im.soft, r, tol), ellipseScore(im, im.soft, inner, tol), rectScore(im, im.soft, inner, tol));
  }

  function refine(layout, im, wallMask) {
    const tol = Math.max(2, Math.round(im.W * 0.005));
    const counters = layout.counters.filter(c => rectScore(im, im.soft, c, tol) >= 0.55);
    const wl = { ...im, soft: wallMask };
    const rooms = layout.rooms.filter(r => r.type !== "dining" && r.type !== "outdoor" ? rectScore(wl, wallMask, r, Math.round(im.W * 0.012)) >= 0.6 : true);
    // tables: score every candidate; per label keep the best; drop anything that isn't drawn
    const scored = layout.tables.map(t => {
      const pw = t.w / 100 * im.W, ph = t.h / 100 * im.H;  // real proportions: a long box is a rectangular table
      return Object.assign({}, t, { score: tableScore(im, t), shape: t.shape || (pw > ph * 1.35 || ph > pw * 1.35 ? "rect" : "round") });
    }).filter(t => t.score >= 0.45).sort((a, b) => b.score - a.score);
    const tables = [];
    scored.forEach(t => {
      const same = tables.find(u => (t.label && u.label.toUpperCase() === t.label.toUpperCase()) || (Math.abs(u.x - t.x) < 2.5 && Math.abs(u.y - t.y) < 2.5));
      if (!same) tables.push(t);
    });
    tables.sort((a, b) => (Math.round(a.y / 8) - Math.round(b.y / 8)) || a.x - b.x);
    return { rooms, counters, tables };
  }

  function matchTables(found, mine) {
    const byNum = new Map(mine.map(t => [t.number, t])), used = new Set(), out = [], rest = [];
    found.forEach(d => {
      const m = (d.label || "").match(/\d+/), n = m ? Number(m[0]) : null;
      if (n != null && byNum.has(n) && !used.has(n)) { used.add(n); out.push({ table_id: byNum.get(n).id, number: n, x: d.x, y: d.y, seats: d.seats, label: d.label }); }
      else rest.push(d);
    });
    const free = mine.filter(t => !used.has(t.number)).sort((a, b) => a.number - b.number);
    rest.forEach((d, i) => { if (free[i]) out.push({ table_id: free[i].id, number: free[i].number, x: d.x, y: d.y, seats: d.seats, label: d.label }); });
    return out.sort((a, b) => a.number - b.number);
  }

  window.Blueprint = { load, traceWalls, refine, matchTables };
})();
