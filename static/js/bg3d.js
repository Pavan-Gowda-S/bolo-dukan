// Animated 3D background: glossy floating shapes, spice-dust particles, mouse parallax.
// Pure decoration: if WebGL or the CDN is missing, the CSS gradient background stays.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const mode = document.body.dataset.bg || "full";
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const small = Math.min(innerWidth, innerHeight) < 700;

function start() {
  const canvas = document.createElement("canvas");
  canvas.id = "bg3d";
  document.body.prepend(canvas);

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: !small, alpha: true, powerPreference: "low-power" });
  } catch (e) { canvas.remove(); return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, small ? 1.5 : 2));
  renderer.setSize(innerWidth, innerHeight, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x0a0613, 0.045);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

  const camera = new THREE.PerspectiveCamera(42, innerWidth / innerHeight, 0.1, 100);
  camera.position.set(0, 0, 14);

  // lights: warm key, magenta rim, cool fill
  scene.add(new THREE.AmbientLight(0x6a4a8a, 0.5));
  const key = new THREE.PointLight(0xffa64d, 140, 40); key.position.set(6, 5, 8); scene.add(key);
  const rim = new THREE.PointLight(0xff3d9a, 110, 40); rim.position.set(-8, -3, 4); scene.add(rim);
  const fill = new THREE.PointLight(0x4cc9f0, 70, 40); fill.position.set(0, -6, 6); scene.add(fill);

  const palette = [0xff9f1c, 0xff4d6d, 0xffc145, 0x9b5cff, 0x2ee6a6, 0xff3d9a, 0x4cc9f0];
  const geos = [
    new THREE.TorusKnotGeometry(0.9, 0.3, 160, 24),
    new THREE.IcosahedronGeometry(1.1, 0),
    new THREE.TorusGeometry(1.0, 0.36, 32, 96),
    new THREE.SphereGeometry(0.9, 48, 48),
    new THREE.CylinderGeometry(1.25, 1.05, 0.22, 64),   // a plate
    new THREE.OctahedronGeometry(1.0, 0),
    new THREE.CapsuleGeometry(0.45, 1.1, 8, 24),
  ];

  const count = mode === "calm" ? 7 : small ? 8 : 13;
  const shapes = [];
  for (let i = 0; i < count; i++) {
    const color = palette[i % palette.length];
    const mat = new THREE.MeshPhysicalMaterial({
      color, metalness: 0.25, roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.08,
      sheen: 0.6, sheenColor: new THREE.Color(0xffffff), iridescence: i % 3 === 0 ? 0.8 : 0,
    });
    const mesh = new THREE.Mesh(geos[i % geos.length], mat);
    // Keep shapes toward the sides so they never sit right behind text.
    const spread = small ? 7 : 12, inner = small ? 3.2 : 5.5;
    const side = i % 2 ? 1 : -1;
    const z = -Math.random() * 10 - 2;
    mesh.position.set(side * (inner + Math.random() * (spread - inner)) - z * side * 0.25, (Math.random() - 0.5) * 10, z);
    const s = 0.55 + Math.random() * 0.85;
    mesh.scale.setScalar(s);
    mesh.rotation.set(Math.random() * 6, Math.random() * 6, Math.random() * 6);
    mesh.userData = {
      base: mesh.position.clone(), spin: new THREE.Vector3((Math.random() - .5) * .5, (Math.random() - .5) * .5, (Math.random() - .5) * .3),
      phase: Math.random() * Math.PI * 2, amp: 0.3 + Math.random() * 0.6, speed: 0.25 + Math.random() * 0.35,
    };
    scene.add(mesh);
    shapes.push(mesh);
  }

  // spice-dust particles
  const N = mode === "calm" ? 350 : small ? 450 : 900;
  const pos = new Float32Array(N * 3), col = new Float32Array(N * 3), seeds = new Float32Array(N);
  const tmp = new THREE.Color();
  for (let i = 0; i < N; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 34;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 22;
    pos[i * 3 + 2] = -Math.random() * 18 + 3;
    tmp.setHex(palette[i % palette.length]).lerp(new THREE.Color(0xffffff), 0.3);
    col.set([tmp.r, tmp.g, tmp.b], i * 3);
    seeds[i] = Math.random();
  }
  const pgeo = new THREE.BufferGeometry();
  pgeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  pgeo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const dot = document.createElement("canvas"); dot.width = dot.height = 64;
  const g = dot.getContext("2d"); const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.35, "rgba(255,255,255,.5)"); grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  const points = new THREE.Points(pgeo, new THREE.PointsMaterial({
    size: 0.16, map: new THREE.CanvasTexture(dot), vertexColors: true, transparent: true, opacity: 0.8,
    depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  scene.add(points);

  // soft glowing halo behind content
  const halo = new THREE.Mesh(
    new THREE.CircleGeometry(9, 64),
    new THREE.MeshBasicMaterial({ color: 0xff7a3d, transparent: true, opacity: 0.07, depthWrite: false, blending: THREE.AdditiveBlending })
  );
  halo.position.set(3, 2, -12); scene.add(halo);

  const mouse = { x: 0, y: 0, tx: 0, ty: 0 };
  addEventListener("pointermove", e => { mouse.tx = (e.clientX / innerWidth - 0.5) * 2; mouse.ty = (e.clientY / innerHeight - 0.5) * 2; }, { passive: true });
  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight, false);
  });

  const clock = new THREE.Clock();
  let running = true;
  document.addEventListener("visibilitychange", () => { running = !document.hidden; if (running) { clock.getDelta(); loop(); } });

  function frame(t, dt) {
    mouse.x += (mouse.tx - mouse.x) * 0.04; mouse.y += (mouse.ty - mouse.y) * 0.04;
    const scrollY = (window.scrollY || 0) / innerHeight;
    camera.position.x = mouse.x * 1.4;
    camera.position.y = -mouse.y * 0.9 - scrollY * 1.6;
    camera.lookAt(0, -scrollY * 1.6, 0);
    for (const m of shapes) {
      const u = m.userData;
      m.rotation.x += u.spin.x * dt; m.rotation.y += u.spin.y * dt; m.rotation.z += u.spin.z * dt;
      m.position.y = u.base.y + Math.sin(t * u.speed + u.phase) * u.amp;
      m.position.x = u.base.x + Math.cos(t * u.speed * 0.7 + u.phase) * u.amp * 0.5;
    }
    const p = pgeo.attributes.position.array;
    for (let i = 0; i < N; i++) {
      p[i * 3 + 1] += (0.15 + seeds[i] * 0.35) * dt;
      p[i * 3] += Math.sin(t * 0.5 + seeds[i] * 10) * 0.004;
      if (p[i * 3 + 1] > 11) p[i * 3 + 1] = -11;
    }
    pgeo.attributes.position.needsUpdate = true;
    points.rotation.z = Math.sin(t * 0.05) * 0.05;
    key.position.x = 6 + Math.sin(t * 0.3) * 3;
    rim.position.y = -3 + Math.cos(t * 0.25) * 3;
    halo.material.opacity = 0.06 + Math.sin(t * 0.6) * 0.02;
    renderer.render(scene, camera);
  }

  function loop() {
    if (!running) return;
    const dt = Math.min(clock.getDelta(), 0.05);
    frame(clock.elapsedTime, dt);
    if (!reduced) requestAnimationFrame(loop);
  }
  loop();
  requestAnimationFrame(() => canvas.classList.add("ready"));
}

if (mode !== "none") {
  try { start(); } catch (e) { console.warn("3D background off:", e); }
}
