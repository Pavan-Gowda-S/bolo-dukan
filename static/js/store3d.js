// Supermarket aisle finder: a 3D store built from the shop's own categories, with a glowing path to the product.
// window.Store3D = { layout(products, categories), locate(product), open(mount, products, categories, product) }
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const L = 12, BAYS = 6, LEVEL_NAMES = ["bottom shelf", "middle shelf", "top shelf"];

// Same layout for everyone: categories in A-Z order, two per aisle (left side, right side);
// products A-Z inside a category, 3 shelves per bay, 6 bays along the aisle.
function layout(products, categories) {
  const cats = [...categories].sort((a, b) => a.localeCompare(b));
  const aisles = Math.max(1, Math.ceil(cats.length / 2));
  const where = new Map();
  cats.forEach((c, ci) => {
    const list = products.filter(p => p.category === c).sort((a, b) => a.name.localeCompare(b.name));
    list.forEach((p, i) => where.set(p.id, { aisle: Math.floor(ci / 2) + 1, side: ci % 2 ? "right" : "left", category: c,
      bay: Math.floor(i / 3) % BAYS, level: i % 3 }));
  });
  return { cats, aisles, where };
}
function locate(products, categories, product) {
  const w = layout(products, categories).where.get(product.id);
  return w ? Object.assign({}, w, { text: `Aisle ${w.aisle} · ${w.side} side · bay ${w.bay + 1} · ${LEVEL_NAMES[w.level]}` }) : null;
}

function textSprite(text, sub, color = "#ffc145") {
  const c = document.createElement("canvas"); c.width = 512; c.height = 160;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(14,8,26,.92)"; g.beginPath(); g.roundRect(8, 8, 496, 144, 28); g.fill();
  g.strokeStyle = color; g.lineWidth = 6; g.stroke();
  g.fillStyle = color; g.font = "800 64px 'Plus Jakarta Sans', system-ui"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text, 256, 60);
  g.fillStyle = "#fff"; g.font = "700 34px 'Plus Jakarta Sans', system-ui"; g.fillText(sub.length > 28 ? sub.slice(0, 27) + "…" : sub, 256, 118);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthWrite: false })); s.scale.set(3.4, 1.06, 1);
  return s;
}
const hue = str => { let h = 0; for (const ch of str) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; };

let scene3d = null;
function open(mount, products, categories, product, opts = {}) {
  const AW = opts.aisleWord || "AISLE", CT = opts.counter || ["BILLING", "pay by UPI"], EN = opts.entrance || ["ENTRANCE", "you are here"];
  close();
  const { cats, aisles, where } = layout(products, categories);
  const W = mount.clientWidth || 800, H = mount.clientHeight || 520;
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1)); renderer.setSize(W, H);
  renderer.shadowMap.enabled = true; renderer.toneMapping = THREE.ACESFilmicToneMapping;
  mount.innerHTML = ""; mount.appendChild(renderer.domElement);
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0d0818); scene.fog = new THREE.Fog(0x0d0818, 30, 70);
  const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.47; controls.minDistance = 4; controls.maxDistance = 50;

  scene.add(new THREE.HemisphereLight(0xfff4e0, 0x2a1a40, 0.9));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(8, 20, 12); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -30, right: 30, top: 30, bottom: -30 }); scene.add(sun);

  const GAP = 3.4, UNIT_D = 1.1, units = aisles + 1, width = units * (GAP + UNIT_D);
  const unitX = j => (j - (units - 1) / 2) * (GAP + UNIT_D);
  const aisleX = k => (unitX(k - 1) + unitX(k)) / 2;           // aisle k (1-based) runs between unit k-1 and unit k
  // floor + low walls
  const floorTex = (() => { const c = document.createElement("canvas"); c.width = c.height = 256; const g = c.getContext("2d");
    g.fillStyle = "#e9e4da"; g.fillRect(0, 0, 256, 256); g.strokeStyle = "#cfc7b8"; g.lineWidth = 3; g.strokeRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(width / 2, 14); t.colorSpace = THREE.SRGBColorSpace; return t; })();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(width + 4, 28), new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.85 }));
  floor.rotation.x = -Math.PI / 2; floor.position.z = 2; floor.receiveShadow = true; scene.add(floor);
  const wallMat = new THREE.MeshStandardMaterial({ color: 0x3a2266, roughness: 0.7 });
  [[0, -12, width + 4, 0.3], [-(width + 4) / 2, 2, 0.3, 28], [(width + 4) / 2, 2, 0.3, 28]].forEach(([x, z, w, d]) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, 2.6, d), wallMat); m.position.set(x, 1.3, z); m.receiveShadow = true; scene.add(m);
  });
  // shelving units (double-sided), stocked with boxes in each category's colour
  const shelfMat = new THREE.MeshStandardMaterial({ color: 0xf3f4f7, roughness: 0.5, metalness: 0.2 });
  const unitMeshes = [];
  for (let j = 0; j < units; j++) {
    const g = new THREE.Group(); g.position.x = unitX(j);
    const body = new THREE.Mesh(new THREE.BoxGeometry(UNIT_D, 2.3, L), shelfMat); body.position.y = 1.15; body.castShadow = body.receiveShadow = true; g.add(body);
    [[-1, j > 0 ? cats[(j - 1) * 2 + 1] : null], [1, j < aisles ? cats[j * 2] : null]].forEach(([sideSign, cat]) => {
      if (!cat) return;
      const col = new THREE.Color(`hsl(${hue(cat)}, 70%, 58%)`);
      const mat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.6 });
      for (let lv = 0; lv < 3; lv++) for (let b = 0; b < BAYS * 3; b++) {
        if ((b * 7 + lv * 3 + j) % 5 === 0) continue;  // a few gaps so shelves look real
        const box = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.42, 0.55), mat);
        box.position.set(sideSign * (UNIT_D / 2 + 0.12), 0.32 + lv * 0.7, -L / 2 + 0.35 + b * (L - 0.7) / (BAYS * 3 - 1));
        g.add(box);
      }
      for (let lv = 0; lv < 3; lv++) { const sh = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.05, L), shelfMat); sh.position.set(sideSign * (UNIT_D / 2 + 0.2), 0.08 + lv * 0.7, 0); g.add(sh); }
    });
    scene.add(g); unitMeshes.push(body);
  }
  // aisle signs hanging above each walkway
  for (let k = 1; k <= aisles; k++) {
    const left = cats[(k - 1) * 2], right = cats[(k - 1) * 2 + 1];
    const s = textSprite(`${AW} ${k}`, [left, right].filter(Boolean).join(" · ")); s.position.set(aisleX(k), 3.3, -L / 2 + 0.6); scene.add(s);
  }
  // entrance + billing counters
  const counterMat = new THREE.MeshStandardMaterial({ color: 0xffc145, roughness: 0.35 });
  [-1, 1].forEach(sgn => { const c = new THREE.Mesh(new THREE.BoxGeometry(2.2, 1, 0.9), counterMat); c.position.set(sgn * 3.2, 0.5, 9.2); c.castShadow = true; scene.add(c); });
  const bill = textSprite(CT[0], CT[1]); bill.position.set(0, 2.4, 9.2); bill.scale.set(2.6, 0.8, 1); scene.add(bill);
  const ent = textSprite(EN[0], EN[1], "#2ee6a6"); ent.position.set(0, 2, 13.2); scene.add(ent);
  const youMat = new THREE.MeshStandardMaterial({ color: 0x2ee6a6, emissive: 0x0a6b4c });
  const you = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 0.1, 32), youMat); you.position.set(0, 0.05, 13); scene.add(you);

  // the product: highlight its spot, draw the path, fly the camera there
  let pin = null, spot = null, dots = [];
  const w = product && where.get(product.id);
  if (w) {
    const j = w.side === "left" ? w.aisle - 1 : w.aisle, sideSign = w.side === "left" ? 1 : -1;
    const x = unitX(j) + sideSign * (UNIT_D / 2 + 0.15), z = -L / 2 + (w.bay + 0.5) * L / BAYS, y = 0.32 + w.level * 0.7;
    spot = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.55, 1.4), new THREE.MeshStandardMaterial({ color: 0xff9f1c, emissive: 0xff6a00, emissiveIntensity: 1.2 }));
    spot.position.set(x + sideSign * 0.06, y, z); scene.add(spot);
    const light = new THREE.PointLight(0xffa640, 18, 6, 2); light.position.set(x + sideSign * 1, y + 1, z); scene.add(light);
    pin = new THREE.Group();
    const cone = new THREE.Mesh(new THREE.ConeGeometry(0.28, 0.7, 24), new THREE.MeshStandardMaterial({ color: 0xff3d6e, emissive: 0x7a0020 })); cone.rotation.x = Math.PI;
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 24), cone.material); ball.position.y = 0.45;
    pin.add(cone, ball); pin.position.set(x + sideSign * 0.9, 2.8, z); scene.add(pin);
    const ax = aisleX(w.aisle);
    const pts = [new THREE.Vector3(0, 0.06, 13), new THREE.Vector3(0, 0.06, 7.3), new THREE.Vector3(ax, 0.06, 7.3), new THREE.Vector3(ax, 0.06, z), new THREE.Vector3(x + sideSign * 0.9, 0.06, z)];
    const curve = new THREE.CatmullRomCurve3(pts, false, "catmullrom", 0.05);
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 200, 0.08, 8, false), new THREE.MeshBasicMaterial({ color: 0x2ee6a6, transparent: true, opacity: 0.55 }));
    scene.add(tube);
    for (let i = 0; i < 14; i++) { const d = new THREE.Mesh(new THREE.SphereGeometry(0.16, 16, 16), new THREE.MeshBasicMaterial({ color: 0xb9ffe6 })); d.userData.t = i / 14; scene.add(d); dots.push(d); }
    scene3d = { curve };
    camera.position.set(0, 22, 26); controls.target.set(0, 0, 0);
    // fly in after a moment
    const end = { pos: new THREE.Vector3(ax + sideSign * -4.5, 5.5, z + 6.5), tgt: new THREE.Vector3(x, y, z) };
    const start = { pos: camera.position.clone(), tgt: controls.target.clone() }, t0 = performance.now() + 900;
    scene3d.fly = now => { const k = Math.min(1, Math.max(0, (now - t0) / 2400)), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      camera.position.lerpVectors(start.pos, end.pos, e); controls.target.lerpVectors(start.tgt, end.tgt, e); return k < 1; };
  } else {
    camera.position.set(0, 22, 26); controls.target.set(0, 0, 0); scene3d = {};
  }
  let alive = true, flying = true;
  renderer.domElement.addEventListener("pointerdown", () => { flying = false; });
  const clock = new THREE.Clock();
  const loop = now => {
    if (!alive) return;
    const t = clock.getElapsedTime();
    if (flying && scene3d.fly) flying = scene3d.fly(now);
    if (pin) { pin.position.y = 2.8 + Math.sin(t * 3) * 0.25; pin.rotation.y = t * 1.5; }
    if (spot) spot.material.emissiveIntensity = 0.8 + Math.sin(t * 5) * 0.6;
    if (scene3d.curve) dots.forEach(d => { const u = (d.userData.t + t * 0.12) % 1; d.position.copy(scene3d.curve.getPointAt(u)); d.position.y = 0.12; });
    you.scale.setScalar(1 + Math.sin(t * 4) * 0.15);
    controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
  const ro = new ResizeObserver(() => { const w2 = mount.clientWidth, h2 = mount.clientHeight; if (!w2 || !h2) return; renderer.setSize(w2, h2); camera.aspect = w2 / h2; camera.updateProjectionMatrix(); });
  ro.observe(mount);
  scene3d.dispose = () => { alive = false; ro.disconnect(); renderer.dispose(); scene.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } }); mount.innerHTML = ""; };
  return w ? locate(products, categories, product) : null;
}
function close() { if (scene3d && scene3d.dispose) scene3d.dispose(); scene3d = null; }

window.Store3D = { layout, locate: (p, c, x) => locate(p, c, x), open, close };
window.dispatchEvent(new Event("store3d-ready"));
