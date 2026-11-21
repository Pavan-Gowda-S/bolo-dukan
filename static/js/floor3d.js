// 3D restaurant floor for the cashier dashboard. window.Floor3D = { mount(el, onPick), update(views) }
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

function labelTexture(text, sub, color) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 160;
  const g = c.getContext("2d");
  g.clearRect(0, 0, 256, 160);
  g.fillStyle = "rgba(14,8,26,.82)";
  roundRect(g, 18, 10, 220, 140, 34); g.fill();
  g.strokeStyle = color; g.lineWidth = 5; roundRect(g, 18, 10, 220, 140, 34); g.stroke();
  g.fillStyle = "#fff"; g.font = "700 72px 'Plus Jakarta Sans', system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 128, 66);
  g.fillStyle = color; g.font = "800 24px 'Plus Jakarta Sans', system-ui, sans-serif";
  g.fillText(sub, 128, 120);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  return tex;
}
function roomLabelTexture(text, color) {
  const c = document.createElement("canvas"); c.width = 512; c.height = 128;
  const g = c.getContext("2d");
  g.font = "800 54px 'Plus Jakarta Sans', system-ui, sans-serif";
  const w = Math.min(500, g.measureText(text).width + 70);
  g.fillStyle = "rgba(10,6,20,.78)"; roundRect(g, 256 - w / 2, 18, w, 92, 46); g.fill();
  g.strokeStyle = color; g.lineWidth = 4; roundRect(g, 256 - w / 2, 18, w, 92, 46); g.stroke();
  g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text, 256, 66);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  return tex;
}
const ROOM_TINT = { kitchen: 0xff9f1c, store: 0x4cc9f0, restroom: 0x9b5cff, cashier: 0xffc145, entrance: 0x2ee6a6, bar: 0xff3d9a, office: 0x4cc9f0, other: 0xffffff };
const COUNTER_STYLE = {
  kitchen: { color: 0xc5cfdc, h: 0.95, metal: 0.75, rough: 0.3 }, cashier: { color: 0xffc145, h: 1.05, metal: 0.1, rough: 0.35 },
  serving: { color: 0xffd98a, h: 1.0, metal: 0.1, rough: 0.4 }, bar: { color: 0x8a5a3c, h: 1.1, metal: 0.1, rough: 0.4 },
  other: { color: 0x7d8ca6, h: 0.5, metal: 0.2, rough: 0.6 },
};
function roundRect(g, x, y, w, h, r) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

const Floor3D = {
  ready: false,
  mount(container, onPick) {
    this.container = container; this.onPick = onPick;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    container.appendChild(renderer.domElement);
    this.renderer = renderer;

    const scene = new THREE.Scene(); this.scene = scene;
    scene.fog = new THREE.Fog(0x0b0716, 22, 60);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200); this.camera = camera;
    camera.position.set(0, 15, 17);
    const controls = new OrbitControls(camera, renderer.domElement); this.controls = controls;
    controls.enableDamping = true; controls.dampingFactor = 0.07;
    controls.maxPolarAngle = Math.PI * 0.44; controls.minPolarAngle = Math.PI * 0.12;
    controls.minDistance = 8; controls.maxDistance = 42; controls.enablePan = false;
    controls.autoRotate = !reduced; controls.autoRotateSpeed = 0.35;
    // Mouse wheel keeps scrolling the page; Ctrl/Cmd + wheel zooms. Pinch zoom stays on for touch.
    controls.enableZoom = false;
    renderer.domElement.addEventListener("pointerdown", e => { controls.autoRotate = false; controls.enableZoom = e.pointerType === "touch"; });
    renderer.domElement.addEventListener("wheel", e => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const dir = camera.position.clone().sub(controls.target);
      const len = THREE.MathUtils.clamp(dir.length() * (e.deltaY > 0 ? 1.1 : 0.9), controls.minDistance, controls.maxDistance);
      camera.position.copy(controls.target).add(dir.setLength(len));
    }, { passive: false });

    scene.add(new THREE.HemisphereLight(0xb79cff, 0x1a0f10, 0.7));
    const sun = new THREE.DirectionalLight(0xffd9a8, 2.2);
    sun.position.set(8, 18, 10); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -25, right: 25, top: 25, bottom: -25, near: 1, far: 60 });
    sun.shadow.bias = -0.0005;
    scene.add(sun);

    // floor: warm terrazzo-like disc with a faint grid
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(40, 96),
      new THREE.MeshStandardMaterial({ color: 0x1c1229, roughness: 0.55, metalness: 0.1 })
    );
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    const grid = new THREE.GridHelper(80, 80, 0x3b2a55, 0x24183a);
    grid.material.transparent = true; grid.material.opacity = 0.35; grid.position.y = 0.01; scene.add(grid);

    // shared geometry/materials
    this.geo = {
      top: new THREE.CylinderGeometry(1.05, 1.05, 0.12, 48),
      leg: new THREE.CylinderGeometry(0.09, 0.14, 0.9, 16),
      base: new THREE.CylinderGeometry(0.45, 0.5, 0.06, 32),
      seat: new THREE.BoxGeometry(0.55, 0.08, 0.55),
      back: new THREE.BoxGeometry(0.55, 0.6, 0.07),
      chairLeg: new THREE.CylinderGeometry(0.03, 0.03, 0.5, 8),
      ring: new THREE.TorusGeometry(1.45, 0.06, 16, 96),
      disc: new THREE.CircleGeometry(1.7, 64),
      beam: new THREE.CylinderGeometry(0.9, 1.4, 6, 48, 1, true),
      badge: new THREE.SphereGeometry(0.34, 24, 24),
      plate: new THREE.CylinderGeometry(0.22, 0.17, 0.04, 24),
    };
    this.mat = {
      wood: new THREE.MeshPhysicalMaterial({ color: 0x8a5a3c, roughness: 0.42, clearcoat: 0.6, clearcoatRoughness: 0.25 }),
      metal: new THREE.MeshStandardMaterial({ color: 0x2b2238, metalness: 0.85, roughness: 0.3 }),
      chair: new THREE.MeshPhysicalMaterial({ color: 0xe9dfd2, roughness: 0.5, clearcoat: 0.3 }),
      plate: new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.15, clearcoat: 1 }),
      badge: new THREE.MeshStandardMaterial({ color: 0xff1a1a, emissive: 0xd10f0f, emissiveIntensity: 1.1, roughness: 0.3 }),
    };

    this.tables = new Map();
    this.raycaster = new THREE.Raycaster(); this.pointer = new THREE.Vector2();
    let down = null;
    renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
    renderer.domElement.addEventListener("pointerup", e => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return;
      const hit = this.pick(e); if (hit) this.onPick(hit);
    });
    renderer.domElement.addEventListener("pointermove", e => {
      const hit = this.pick(e);
      renderer.domElement.style.cursor = hit ? "pointer" : "grab";
      this.hover = hit;
    });

    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this.clock = new THREE.Clock();
    const loop = () => { if (this.visible !== false) this.frame(); requestAnimationFrame(loop); };
    loop();
    this.ready = true;
  },

  resize() {
    const w = this.container.clientWidth || 1, h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = w + "px"; this.renderer.domElement.style.height = h + "px";
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  },

  pick(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const targets = []; this.tables.forEach(t => targets.push(t.hit));
    const hits = this.raycaster.intersectObjects(targets, false);
    return hits.length ? hits[0].object.userData.tableId : null;
  },

  build(view, x, z) {
    const g = new THREE.Group(); g.position.set(x, 0, z);
    const { geo, mat } = this;
    const top = new THREE.Mesh(geo.top, mat.wood); top.position.y = 0.95; top.castShadow = top.receiveShadow = true;
    const leg = new THREE.Mesh(geo.leg, mat.metal); leg.position.y = 0.48; leg.castShadow = true;
    const base = new THREE.Mesh(geo.base, mat.metal); base.position.y = 0.03;
    g.add(top, leg, base);
    const nChairs = Math.max(1, Math.min(12, view.seats || 4)), rad = nChairs > 6 ? 1.55 + (nChairs - 6) * 0.12 : 1.55;
    if (nChairs > 6) top.scale.set(1 + (nChairs - 6) * 0.1, 1, 1 + (nChairs - 6) * 0.1);
    for (let i = 0; i < nChairs; i++) {
      const a = (i / nChairs) * Math.PI * 2 + Math.PI / 4;
      const chair = new THREE.Group();
      const seat = new THREE.Mesh(geo.seat, mat.chair); seat.position.y = 0.52; seat.castShadow = true;
      const back = new THREE.Mesh(geo.back, mat.chair); back.position.set(0, 0.85, 0.26); back.castShadow = true;
      chair.add(seat, back);
      [[-.22, -.22], [.22, -.22], [-.22, .22], [.22, .22]].forEach(([lx, lz]) => {
        const l = new THREE.Mesh(geo.chairLeg, mat.metal); l.position.set(lx, 0.25, lz); chair.add(l);
      });
      chair.position.set(Math.cos(a) * rad, 0, Math.sin(a) * rad);
      chair.lookAt(0, 0, 0); chair.rotateY(Math.PI);
      g.add(chair);
    }
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x6b6584, transparent: true, opacity: 0.9 });
    const ring = new THREE.Mesh(geo.ring, ringMat); ring.rotation.x = Math.PI / 2; ring.position.y = 0.05;
    const discMat = new THREE.MeshBasicMaterial({ color: 0x6b6584, transparent: true, opacity: 0.12, depthWrite: false, blending: THREE.AdditiveBlending });
    const disc = new THREE.Mesh(geo.disc, discMat); disc.rotation.x = -Math.PI / 2; disc.position.y = 0.03;
    const beamMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending });
    const beam = new THREE.Mesh(geo.beam, beamMat); beam.position.y = 3.2;
    const light = new THREE.PointLight(0xffffff, 0, 6, 2); light.position.y = 2.2;
    const badge = new THREE.Mesh(geo.badge, mat.badge); badge.position.set(1.45, 3.3, 0); badge.visible = false;
    const plates = new THREE.Group(); plates.position.y = 1.03;
    for (let i = 0; i < 4; i++) {
      const p = new THREE.Mesh(geo.plate, mat.plate); const a = (i / 4) * Math.PI * 2 + Math.PI / 4;
      p.position.set(Math.cos(a) * 0.6, 0, Math.sin(a) * 0.6); p.castShadow = true; plates.add(p);
    }
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, depthWrite: false }));
    label.scale.set(2.3, 1.44, 1); label.position.y = 2.75;
    const hit = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 1.8, 3, 16), new THREE.MeshBasicMaterial({ visible: false }));
    hit.position.y = 1.2; hit.userData.tableId = view.id;
    g.add(ring, disc, beam, light, badge, plates, label, hit);
    this.scene.add(g);
    return { group: g, ring, disc, beam, light, badge, plates, label, hit, key: "", phase: Math.random() * 6, seats: view.seats || 4 };
  },

  update(views) {
    if (!this.ready) return;
    this.lastViews = views;
    const ids = new Set(views.map(v => v.id));
    this.tables.forEach((t, id) => { if (!ids.has(id)) { this.scene.remove(t.group); this.tables.delete(id); } });
    const n = views.length, cols = Math.ceil(Math.sqrt(n * 1.4)), gap = 4.1;
    const rowsN = Math.ceil(n / cols);
    const planned = n > 0 && views.every(v => v.pos_x != null && v.pos_y != null);
    const ar = this.bpAspect || 1.6;
    let S = Math.max(16, Math.sqrt(n) * gap * 1.7);
    if (planned) {  // scale the floor so the two closest tables (3D tables + chairs are ~3.6 wide) never overlap
      let dmin = Infinity;
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        const dx = (views[i].pos_x - views[j].pos_x) / 100 * Math.sqrt(ar), dz = (views[i].pos_y - views[j].pos_y) / 100 / Math.sqrt(ar);
        dmin = Math.min(dmin, Math.hypot(dx, dz));
      }
      if (isFinite(dmin) && dmin > 0) S = Math.min(60, Math.max(S, 3.9 / dmin));
    }
    const W = S * Math.sqrt(ar), D = S / Math.sqrt(ar);
    this.planSize = planned || this.layout ? [W, D] : null;
    this.fitBlueprint();
    if (this.layout && this.layoutBuilt !== this.layoutKey + "|" + W.toFixed(2) + "|" + D.toFixed(2)) this.buildLayout(W, D);
    views.forEach((v, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      const x = planned ? (v.pos_x / 100 - 0.5) * W : (c - (cols - 1) / 2) * gap, z = planned ? (v.pos_y / 100 - 0.5) * D : (r - (rowsN - 1) / 2) * gap;
      let t = this.tables.get(v.id);
      if (t && t.seats !== (v.seats || 4)) { this.scene.remove(t.group); this.tables.delete(v.id); t = null; }  // chairs changed: rebuild
      if (!t) { t = this.build(v, x, z); this.tables.set(v.id, t); t.group.scale.setScalar(0.01); t.grow = 0; }
      t.group.position.set(x, 0, z);
      t.view = v;
      const key = `${v.number}|${v.stateLabel}|${v.color}|${v.seats || ""}`;
      if (key !== t.key) {
        t.key = key;
        if (t.label.material.map) t.label.material.map.dispose();
        t.label.material.map = labelTexture(String(v.number), v.stateLabel.toUpperCase() + (v.seats ? ` · ${v.seats} SEATS` : ""), v.color);
        t.label.material.needsUpdate = true;
        const col = new THREE.Color(v.color);
        t.ring.material.color.copy(col); t.disc.material.color.copy(col);
        t.beam.material.color.copy(col); t.light.color.copy(col);
      }
      t.badge.visible = !!v.waiter;
      t.plates.visible = v.state !== "empty" && v.state !== "waiting";
    });
    const span = planned ? Math.max(W, D) * 0.8 : Math.max(cols, rowsN) * gap;
    this.controls.maxDistance = Math.max(20, span * 2.4);
    if (!this.framed) {
      this.framed = true;
      const aspect = this.camera.aspect || 1.6, fit = span / Math.min(1.6, aspect) * 0.95;
      this.camera.position.set(0, fit * 0.9 + 4, fit + 4.5);
    }
  },

  // 7: the owner's blueprint lies on the floor under the tables (positions are % of its width/height)
  setBlueprint(url) {
    if (!this.ready || url === this.bpUrl) return;
    this.bpUrl = url;
    if (this.bp) { this.scene.remove(this.bp); this.bp.material.map && this.bp.material.map.dispose(); this.bp = null; }
    if (!url) { this.bpAspect = null; return; }
    new THREE.TextureLoader().load(url, tex => {
      if (url !== this.bpUrl) return tex.dispose();
      tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
      this.bpAspect = tex.image.width / tex.image.height || 1.6;
      this.bp = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshStandardMaterial({ map: tex, transparent: true, opacity: 0.9, roughness: 0.9 }));
      this.bp.rotation.x = -Math.PI / 2; this.bp.position.y = 0.015; this.bp.receiveShadow = true;
      this.scene.add(this.bp);
      if (this.lastViews) this.update(this.lastViews); else this.fitBlueprint();
    });
  },
  // The blueprint, built in 3D: walls traced from the image, counters, room tints and names (from the AI reading,
  // checked against the drawing and applied by the owner). Coordinates are % of the image.
  setLayout(layout) {
    const key = layout ? JSON.stringify(layout) : "";
    if (key === this.layoutKey) return;
    this.layoutKey = key; this.layout = layout && (layout.walls || []).length + (layout.counters || []).length + (layout.rooms || []).length ? layout : null;
    if (!this.layout && this.layoutGroup) { this.scene.remove(this.layoutGroup); this.layoutGroup = null; this.layoutBuilt = null; }
    if (this.lastViews) this.update(this.lastViews);
  },
  buildLayout(W, D) {
    if (this.layoutGroup) { this.scene.remove(this.layoutGroup); this.layoutGroup.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } }); }
    const g = new THREE.Group(); this.layoutGroup = g; this.layoutBuilt = this.layoutKey + "|" + W.toFixed(2) + "|" + D.toFixed(2);
    const X = p => (p / 100 - 0.5) * W, Z = p => (p / 100 - 0.5) * D;
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xf2f6ff, roughness: 0.55, metalness: 0.05 });
    const capMat = new THREE.MeshStandardMaterial({ color: 0xffc145, roughness: 0.4, emissive: 0x6b4a00, emissiveIntensity: 0.35 });
    (this.layout.walls || []).forEach(w => {
      const x1 = X(w[0]), z1 = Z(w[1]), x2 = X(w[2]), z2 = Z(w[3]);
      const len = Math.hypot(x2 - x1, z2 - z1), th = Math.max(0.12, (w[4] || 0.6) / 100 * W);
      if (len < 0.2) return;
      const wall = new THREE.Mesh(new THREE.BoxGeometry(len + th * 0.9, 1.05, th), wallMat);
      wall.position.set((x1 + x2) / 2, 0.525, (z1 + z2) / 2); wall.rotation.y = -Math.atan2(z2 - z1, x2 - x1);
      wall.castShadow = wall.receiveShadow = true; g.add(wall);
      const cap = new THREE.Mesh(new THREE.BoxGeometry(len + th * 0.9, 0.04, th * 1.02), capMat);   // thin warm top edge
      cap.position.set(wall.position.x, 1.07, wall.position.z); cap.rotation.y = wall.rotation.y; g.add(cap);
    });
    (this.layout.counters || []).forEach(c => {
      const st = COUNTER_STYLE[c.kind] || COUNTER_STYLE.other;
      const w = Math.max(0.2, c.w / 100 * W * 0.94), d = Math.max(0.2, c.h / 100 * D * 0.94);
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, st.h, d), new THREE.MeshPhysicalMaterial({ color: st.color, metalness: st.metal, roughness: st.rough, clearcoat: 0.4 }));
      m.position.set(X(c.x + c.w / 2), st.h / 2, Z(c.y + c.h / 2)); m.castShadow = m.receiveShadow = true; g.add(m);
    });
    (this.layout.rooms || []).forEach(r => {
      const color = ROOM_TINT[r.type];
      if (color != null && r.type !== "dining") {
        const tint = new THREE.Mesh(new THREE.PlaneGeometry(r.w / 100 * W, r.h / 100 * D),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.13, depthWrite: false }));
        tint.rotation.x = -Math.PI / 2; tint.position.set(X(r.x + r.w / 2), 0.03, Z(r.y + r.h / 2)); g.add(tint);
      }
      const lab = new THREE.Sprite(new THREE.SpriteMaterial({ map: roomLabelTexture((r.label || r.type).toUpperCase(), "#" + (color != null ? color : 0xffffff).toString(16).padStart(6, "0")), transparent: true, depthWrite: false }));
      lab.scale.set(3.2, 0.8, 1); lab.position.set(X(r.x + r.w / 2), r.type === "dining" ? 0.6 : 1.9, Z(r.y + r.h / 2)); g.add(lab);
    });
    this.scene.add(g);
  },
  fitBlueprint() {
    if (!this.bp) return;
    const [W, D] = this.planSize || [16 * Math.sqrt(this.bpAspect), 16 / Math.sqrt(this.bpAspect)];
    this.bp.scale.set(W, D, 1);  // exactly the area tables and walls are placed on
  },

  frame() {
    const dt = Math.min(this.clock.getDelta(), 0.05), t = this.clock.elapsedTime;
    this.tables.forEach(tb => {
      if (tb.grow < 1) { tb.grow = Math.min(1, tb.grow + dt * 1.6); const e = 1 - Math.pow(1 - tb.grow, 3); tb.group.scale.setScalar(0.01 + e * 0.99); }
      const v = tb.view || {};
      const flash = v.flash ? 0.5 + 0.5 * Math.sin(t * 6 + tb.phase) : 0;
      const active = v.state && v.state !== "empty";
      tb.ring.material.opacity = active ? 0.65 + flash * 0.35 : 0.35;
      tb.disc.material.opacity = active ? 0.14 + flash * 0.2 : 0.05;
      tb.beam.material.opacity = v.flash ? 0.05 + flash * 0.13 : (v.state === "paid" ? 0.06 : 0);
      tb.light.intensity = active ? 6 + flash * 18 : 0;
      tb.label.position.y = 2.75 + Math.sin(t * 1.4 + tb.phase) * 0.08;
      tb.badge.position.y = 3.3 + Math.abs(Math.sin(t * 4)) * 0.3;
      if (tb.badge.visible) tb.badge.scale.setScalar(1 + Math.abs(Math.sin(t * 4)) * 0.25);
      const target = this.hover === v.id ? 1.06 : 1;
      if (tb.grow >= 1) tb.group.scale.lerp(new THREE.Vector3(target, target, target), 0.15);
    });
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  },
};

window.Floor3D = Floor3D;
window.dispatchEvent(new Event("floor3d-ready"));
