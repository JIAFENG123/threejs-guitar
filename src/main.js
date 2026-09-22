import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import * as C from './config.js';
import { GuitarAudio } from './audio.js';

// ---------------------------------------------------------------- renderer

const canvas = document.getElementById('app');
const statusEl = document.getElementById('status');

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1015);
scene.fog = new THREE.Fog(0x0d1015, 3.5, 9);

const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.01, 30);
camera.position.set(0.15, 1.05, 0.78);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 0.35;
controls.maxDistance = 2.8;
controls.minPolarAngle = 0.05;
controls.maxPolarAngle = 1.52;
controls.target.set(0, 0, 0);

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

// ---------------------------------------------------------------- lights / floor

const key = new THREE.DirectionalLight(0xfff4e5, 2.4);
key.position.set(1.4, 2.3, 1.1);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -1;
key.shadow.camera.right = 1;
key.shadow.camera.top = 1;
key.shadow.camera.bottom = -1;
key.shadow.camera.near = 0.5;
key.shadow.camera.far = 6;
key.shadow.bias = -0.00025;
key.shadow.radius = 4;
scene.add(key);

const fill = new THREE.DirectionalLight(0x9db8ff, 0.55);
fill.position.set(-1.6, 1.2, -0.9);
scene.add(fill);

scene.add(new THREE.HemisphereLight(0xffffff, 0x1a1d26, 0.4));

const floor = new THREE.Mesh(
  new THREE.CircleGeometry(3.2, 64),
  new THREE.ShadowMaterial({ opacity: 0.5 }),
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

// ---------------------------------------------------------------- guitar model

const audio = new GuitarAudio();
const strings = [];
const hitboxes = [];
const invisibleMat = new THREE.MeshBasicMaterial({ visible: false });

let currentFret = 0;
let hoverIdx = -1;
let dragging = false;

const fretIndicator = new THREE.Mesh(
  new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
  new THREE.MeshBasicMaterial({
    color: 0x5fd8ff, transparent: true, opacity: 0.9, depthWrite: false,
  }),
);

function segmentedCylinder(radius, len, segL, segR) {
  const pos = [];
  const norm = [];
  const u = [];
  const idx = [];
  for (let i = 0; i <= segL; i++) {
    const t = i / segL;
    const z = -len / 2 + t * len;
    for (let j = 0; j <= segR; j++) {
      const a = (j / segR) * Math.PI * 2;
      const cx = Math.cos(a);
      const sy = Math.sin(a);
      pos.push(cx * radius, sy * radius, z);
      norm.push(cx, sy, 0);
      u.push(t);
    }
  }
  const row = segR + 1;
  for (let i = 0; i < segL; i++) {
    for (let j = 0; j < segR; j++) {
      const a = i * row + j;
      const b = a + row;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(norm, 3));
  g.setAttribute('aU', new THREE.Float32BufferAttribute(u, 1));
  g.setIndex(idx);
  return g;
}

function setupString(node, idx) {
  node.material = node.material.clone();
  node.castShadow = false;

  // export_apply=True bakes transforms into the mesh: geometry lives in model
  // space along +Z, node transforms are identity.
  const old = node.geometry;
  old.computeBoundingBox();
  const bb = old.boundingBox;
  const len = bb.max.z - bb.min.z;
  const center = bb.getCenter(new THREE.Vector3());
  const geo = segmentedCylinder(C.STRING_R[idx], len, 44, 10);
  geo.translate(center.x, center.y, center.z);
  node.geometry = geo;
  old.dispose();

  const hitGeo = new THREE.CylinderGeometry(0.007, 0.007, len, 8, 1).rotateX(Math.PI / 2);
  const hit = new THREE.Mesh(hitGeo, invisibleMat);
  hit.position.copy(center);
  hit.userData.stringIdx = idx;
  node.add(hit);
  hitboxes.push(hit);

  strings[idx] = {
    idx, node, geo, len,
    base: geo.attributes.position.array.slice(),
    anim: null, lastPluck: -1e9,
  };
}

function setFret(n) {
  currentFret = Math.max(0, Math.min(C.MAX_FRET, n));
  const y = C.fretY(currentFret);
  fretIndicator.position.set(0, C.FB_TOP + 0.011, -y);
  fretIndicator.scale.set(C.fbHalfWidth(y) * 1.85, 1, 0.007);

  document.getElementById('fretNum').textContent = currentFret;
  document.getElementById('fretHint').textContent =
    currentFret === 0 ? '空弦' : `按住第 ${currentFret} 品`;

  const notesEl = document.getElementById('notes');
  notesEl.innerHTML = '';
  for (let i = 5; i >= 0; i--) {
    const note = C.noteName(C.noteFreq(i, currentFret));
    const span = document.createElement('span');
    span.innerHTML = `<b>${note}</b>${C.STRING_LABELS[i]}${6 - i}`;
    notesEl.appendChild(span);
  }
}

function doPluck(i, vel = 1) {
  const s = strings[i];
  if (!s) return;
  const now = performance.now();
  if (now - s.lastPluck < 70) return;
  s.lastPluck = now;
  const freq = C.noteFreq(i, currentFret);
  audio.pluck(i, currentFret, vel);
  s.anim = { t0: now / 1000, freq, vel };
}

function strumAll() {
  for (let i = 0; i < 6; i++) {
    setTimeout(() => doPluck(i, 0.9 - i * 0.03 + Math.random() * 0.06), i * 28);
  }
}

function initGuitar(model) {
  const guitar = new THREE.Group();
  guitar.rotation.y = 0.3;
  scene.add(guitar);
  guitar.add(model);

  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  model.position.sub(center);
  floor.position.y = box.min.y - center.y - 0.001;

  model.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = true;
    o.receiveShadow = true;
    if (o.material && 'envMapIntensity' in o.material) o.material.envMapIntensity = 1.15;
    const m = /^string_(\d)$/.exec(o.name);
    if (m) setupString(o, Number(m[1]));
  });

  model.add(fretIndicator);
  setFret(0);
  statusEl.style.display = 'none';
  animate();
}

// ---------------------------------------------------------------- pointer input

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let lastDragIdx = -1;

function updatePointer(e) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
}

function pickString() {
  if (!hitboxes.length) return -1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(hitboxes, false);
  return hits.length ? hits[0].object.userData.stringIdx : -1;
}

canvas.addEventListener('pointermove', (e) => {
  updatePointer(e);
  hoverIdx = pickString();
  canvas.style.cursor = hoverIdx >= 0 ? 'pointer' : 'grab';
  if (dragging && hoverIdx >= 0 && hoverIdx !== lastDragIdx) {
    lastDragIdx = hoverIdx;
    doPluck(hoverIdx);
  }
});

canvas.addEventListener('pointerdown', (e) => {
  audio.unlock();
  updateAudioHint();
  updatePointer(e);
  const idx = pickString();
  if (idx >= 0) {
    controls.enabled = false;
    dragging = true;
    lastDragIdx = idx;
    doPluck(idx);
  }
});

window.addEventListener('pointerup', () => {
  dragging = false;
  lastDragIdx = -1;
  controls.enabled = true;
});

// ---------------------------------------------------------------- keyboard

window.addEventListener('keydown', (e) => {
  audio.unlock();
  updateAudioHint();
  const c = e.code;
  if (c >= 'Digit1' && c <= 'Digit6') {
    doPluck(6 - Number(c.slice(5)));
  } else if (/^Key[A-Z]$/.test(c) && 'ASDFGH'.includes(c.slice(3))) {
    doPluck('ASDFGH'.indexOf(c.slice(3)));
  } else if (c === 'ArrowUp' || c === 'ArrowRight') {
    e.preventDefault();
    setFret(currentFret + 1);
  } else if (c === 'ArrowDown' || c === 'ArrowLeft') {
    e.preventDefault();
    setFret(currentFret - 1);
  } else if (c === 'Space') {
    e.preventDefault();
    strumAll();
  } else if (c === 'KeyR') {
    setFret(0);
  } else if (c === 'KeyM') {
    audio.setMuted(!audio.muted);
  }
});

function updateAudioHint() {
  const el = document.getElementById('audioHint');
  if (!el) return;
  if (audio.ctx && !audio.ctx.__hintBound) {
    audio.ctx.__hintBound = true;
    audio.ctx.onstatechange = updateAudioHint;
  }
  const st = audio.ctx ? audio.ctx.state : '';
  el.style.display = (st && st !== 'running') ? 'block' : 'none';
}

// ---------------------------------------------------------------- animation

function resetString(s) {
  s.geo.attributes.position.array.set(s.base);
  s.geo.attributes.position.needsUpdate = true;
  s.node.material.emissiveIntensity = 0;
}

function animate() {
  requestAnimationFrame(animate);
  const t = performance.now() / 1000;
  controls.update();

  for (const s of strings) {
    if (!s) continue;
    if (s.anim) {
      const dt = t - s.anim.t0;
      const env = Math.exp(-dt * 2.8);
      if (env < 0.006) {
        s.anim = null;
        resetString(s);
      } else {
        const fvis = Math.max(5, Math.min(17, s.anim.freq / 10));
        const amp = 0.0062 * s.anim.vel * env;
        const osc = Math.cos(2 * Math.PI * fvis * dt);
        const osc2 = Math.cos(2 * Math.PI * fvis * 1.98 * dt) * Math.exp(-dt * 5);
        const pos = s.geo.attributes.position.array;
        const base = s.base;
        const uArr = s.geo.attributes.aU.array;
        for (let k = 0; k < uArr.length; k++) {
          const u = uArr[k];
          const shape = Math.sin(Math.PI * u)
            + 0.35 * Math.sin(2 * Math.PI * u) * Math.exp(-dt * 6);
          const d = amp * (shape * osc + 0.25 * Math.sin(Math.PI * u) * osc2);
          const k3 = k * 3;
          pos[k3] = base[k3] + d;
          pos[k3 + 1] = base[k3 + 1] + d * 0.4;
        }
        s.geo.attributes.position.needsUpdate = true;
        s.node.material.emissive.setHex(0x4d9fff);
        s.node.material.emissiveIntensity = env * 0.5;
      }
    } else if (hoverIdx === s.idx) {
      s.node.material.emissive.setHex(0x4d9fff);
      s.node.material.emissiveIntensity = 0.3;
    } else if (s.node.material.emissiveIntensity !== 0) {
      s.node.material.emissiveIntensity = 0;
    }
  }

  renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ---------------------------------------------------------------- load

new GLTFLoader().load(
  '/guitar.glb',
  (gltf) => initGuitar(gltf.scene),
  undefined,
  () => {
    statusEl.textContent = '加载 public/guitar.glb 失败 — 请先运行 npm run model（Blender 导出）';
  },
);

window.__guitar = {
  strings, audio, setFret, doPluck, strumAll, camera, fretIndicator,
  get fret() { return currentFret; },
  pickClient(x, y) {
    pointer.set((x / innerWidth) * 2 - 1, -(y / innerHeight) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(hitboxes, false)
      .map((h) => `${h.object.userData.stringIdx}@${h.distance.toFixed(3)}`);
  },
  hitDebug() {
    const camPos = camera.position;
    return hitboxes.map((h) => {
      const w = h.getWorldPosition(camPos.clone());
      const d = w.distanceTo(camPos).toFixed(3);
      return `${h.userData.stringIdx}:world(${w.x.toFixed(3)},${w.y.toFixed(3)},${w.z.toFixed(3)})d=${d}`;
    });
  },
};
