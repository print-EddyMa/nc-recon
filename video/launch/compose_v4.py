"""NC Recon launch film v4, "The scan": `python3 video/launch/compose_v4.py [16x9|9x16]`.

Writes build/composition_v4_<aspect>.html: a deterministic page (`await window.render(t)`)
for render.py. Real material only: public-domain DVIDS footage of Helene (clips_v4.py),
Civil Air Patrol and NC OneMap imagery, USGS elevation, Swannanoa's building outlines
(prep_v4.py), the app itself, and the Blender logo reveal (logo_reveal.py).

Every building in the scan is neutral: the film shows buildings being read, and damage
only as the smoothed density the public site shows. The one per-building call on screen
is the showcase home the site already publishes.
"""
from __future__ import annotations

import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(HERE, "build")
A = os.path.join(HERE, "assets")
TERR = os.path.join(ROOT, "site", "assets", "terrain")
BEAT = 0.6                            # 100 bpm
SIZES = {"16x9": (1920, 1080), "9x16": (1080, 1920)}

# beat, end beat, clip
CLIPS = [(0, 3, "aerial"), (3, 5, "flood"), (5, 7, "river"), (7, 9, "wreck"), (9, 11, "fridge"),
         (11, 14, "balls"), (14, 17, "toycar"), (17, 19, "crew"), (19, 21, "cockpit"), (21, 23, "pallet")]
# beat, end beat, image, 16:9 [zoom, origin x, origin y], 9:16 [object-position x, zoom, origin x, origin y]
# App shots stay on panels: the map panes carry per-building colours, and the film shows
# per-building damage only for the showcase home.
PLATES = [(64, 66, "plates/swannanoa_home_pre.jpg", [1, 50, 50], [50, 1, 50, 50]),
          (66, 70, "plates/swannanoa_home_post.jpg", [1, 50, 50], [50, 1, 50, 50]),
          (70, 72, "app2/verify.png", [2, 34, 40], [30, 1.25, 30, 45]),
          (72, 74, "app2/stepper_found.png", [2.4, 100, 8], [100, 1.8, 100, 8]),
          (74, 76, "app2/stepper_found.png", [2.4, 0, 8], [0, 1.8, 0, 8]),
          (76, 78, "app2/respond.png", [3, 100, 10], [100, 2, 100, 10])]
# beat, end beat, text, class
CUES = [
    (0, 3, "September 27, 2024", "big"), (3, 7, "Hurricane Helene.<br>Western North Carolina.", "big"),
    (11, 17, "Swannanoa, five weeks after", "low"),
    (17, 19, "More than 100<br>search teams", "big"), (19, 21, "80,000 damage<br>assessments", "big"), (21, 23, "House by house.", "big"),
    (21, 23, "DHS Science and Technology, October 7, 2024", "low"),
    (23, 27, "After Helene and Milton,<br>4% of FEMA's incident workforce<br>was available.", "mid"),
    (24, 27, "GAO-25-108598", "src"),
    (27, 30, "The next storm<br>won't wait.", "mid"),
    (32, 36, "What if the map<br>came first?", "mid"),
    (50, 52, "893 buildings.", "huge"), (52, 54, "88 seconds.", "huge"), (54, 56, "One laptop.", "huge"),
    (56, 58, "Where the<br>damage is.", "big"), (58, 60, "Which roads<br>are cut.", "big"),
    (60, 62, "Where to land.", "big"), (62, 64, "Where to<br>search first.", "big"),
    (64, 66, "Before", "tag"), (66, 68, "After", "tag"),
    (68, 70, "Destroyed. 76%.", "big"), (70, 72, "People check<br>the hard calls.", "big"),
    (72, 74, "Type a FEMA<br>disaster<br>number.", "big"), (74, 76, "Any disaster.<br>Any state.", "big r"),
    (76, 78, "Ready for<br>the field.", "big"),
    (78, 80, "FEMA survey fields<br>GeoPackage<br>File Geodatabase<br>KML for TAK<br>CSV", "mid"),
    (88, 90, "Free.", "huge"), (90, 92, "Open source.", "huge"), (92, 96, "Built after Helene,<br>in North Carolina.", "mid"),
]


def rel(p: str) -> str:
    return os.path.relpath(p, BUILD)


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>NC Recon, the scan</title>
<style>
@font-face { font-family:"Disp"; font-weight:100 900; font-stretch:62% 125%; src:url(%%FONT%%); }
* { box-sizing:border-box; }
html,body { margin:0; width:%%W%%px; height:%%H%%px; overflow:hidden; background:#000; color:#F5F3EE; font-family:"Disp",Helvetica,Arial,sans-serif; }
.L { position:absolute; inset:0; }
#gl { position:absolute; inset:0; width:%%W%%px; height:%%H%%px; display:block; }
#pw { position:absolute; left:0; top:0; width:100%; height:100%; overflow:hidden; }
#clip,#plate { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:0; }
#shade { background:linear-gradient(180deg,rgba(0,0,0,0) 40%,rgba(0,0,0,.72) 100%); opacity:0; }
#logo { filter:contrast(1.1); position:absolute; left:50%; top:50%; width:%%LOGO%%px; height:%%LOGO%%px; margin:-%%LOGOH%%px 0 0 -%%LOGOH%%px; opacity:0; }
#flash { background:#fff; opacity:0; }
.t { position:absolute; opacity:0; font-stretch:112%; font-weight:640; letter-spacing:-.018em; line-height:1.0; text-transform:none; }
.big,.huge { left:%%PAD%%px; right:%%PAD%%px; bottom:%%BOT%%px; }
.big { font-size:%%BIG%%px; } .big.r { text-align:%%RALIGN%%; } .huge { font-size:%%HUGE%%px; letter-spacing:-.03em; }
.mid { left:%%PAD%%px; right:%%PAD%%px; top:50%; transform:translateY(-50%); text-align:center; font-size:%%MID%%px; line-height:1.14; }
.low { left:%%PAD%%px; right:%%PAD%%px; bottom:%%LOWB%%px; font-size:%%LOW%%px; font-weight:480; font-stretch:100%; letter-spacing:0; color:rgba(245,243,238,.82); }
.src { left:0; right:0; top:calc(50% + %%SRCY%%px); text-align:center; font-size:%%LOW%%px; font-weight:440; font-stretch:100%; letter-spacing:0; color:rgba(245,243,238,.6); }
.tag { left:%%PAD%%px; top:%%TAGT%%px; font-size:%%LOW%%px; font-weight:560; font-stretch:100%; letter-spacing:.02em; }
#hud { position:absolute; left:%%PAD%%px; top:%%HUDT%%px; opacity:0; font-stretch:100%; font-variant-numeric:tabular-nums; }
#hud .n { font-size:%%HUDN%%px; font-weight:640; letter-spacing:-.02em; line-height:1; font-stretch:112%; }
#hud .k { font-size:%%LOW%%px; font-weight:460; color:rgba(245,243,238,.7); margin:6px 0 %%HUDG%%px; }
#proof { background:#000; opacity:0; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:0 %%PAD%%px; }
#proof .p { font-size:%%PCT%%px; font-weight:680; letter-spacing:-.05em; line-height:.86; font-stretch:112%; }
#proof .p small { font-size:.42em; color:#FF5A1F; letter-spacing:-.02em; margin-left:.04em; }
#proof .a { margin-top:%%PG1%%px; font-size:%%PA%%px; font-weight:560; line-height:1.14; letter-spacing:-.012em; max-width:%%PMAX%%px; }
#proof .b { margin-top:%%PG2%%px; font-size:%%LOW%%px; font-weight:440; font-stretch:100%; color:rgba(245,243,238,.62); line-height:1.3; max-width:%%PMAX%%px; }
#end { opacity:0; }
#end .w { position:absolute; left:0; right:0; top:%%WT%%px; text-align:center; font-size:%%WORD%%px; font-weight:760; font-stretch:118%; letter-spacing:-.022em; opacity:0; }
#end .s { position:absolute; left:%%PAD%%px; right:%%PAD%%px; top:%%ST%%px; text-align:center; font-size:%%STAG%%px; font-weight:520; letter-spacing:-.008em; line-height:1.12; opacity:0; }
#end .u { position:absolute; left:0; right:0; top:%%UT%%px; text-align:center; font-size:%%LOW%%px; font-weight:480; font-stretch:100%; color:rgba(245,243,238,.8); opacity:0; }
#end .f { position:absolute; left:%%PAD%%px; right:%%PAD%%px; bottom:%%FB%%px; text-align:center; font-size:%%FINE%%px; font-weight:420; font-stretch:100%; line-height:1.34; color:rgba(245,243,238,.5); opacity:0; }
</style>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
</head><body>
<canvas id="gl" width="%%W%%" height="%%H%%"></canvas>
<div id="pw"><img id="plate" alt=""></div><img id="clip" alt="">
<div class="L" id="shade"></div>
<div id="hud"><div class="n" id="hn">000</div><div class="k">buildings read</div><div class="n" id="ht">00:00</div><div class="k">elapsed</div></div>
%%CUES%%
<div class="L" id="proof"><div class="p">96<small>%</small></div>
  <div class="a">of the time, CAL FIRE inspectors agreed when NC Recon called a building destroyed or badly damaged after the Eaton fire.</div>
  <div class="b">Precision 95.7%, recall 94.2%, on 2,246 buildings. Wildfire model, one pre-registered held-out test. Flood accuracy is still being validated.</div></div>
<img id="logo" alt="">
<div class="L" id="end"><div class="w">NC Recon</div><div class="s">Every building, after the disaster.</div><div class="u">github.com/print-EddyMa/nc-recon</div>
  <div class="f">Decision support. Verify on the ground. Built after the storm; not used in the Helene response.<br>Footage: DVIDS, public domain, no Department of Defense endorsement implied. Imagery: NC OneMap, Civil Air Patrol / FEMA. Elevation: USGS 3DEP. Roads: OpenStreetMap contributors.</div></div>
<div class="L" id="flash"></div>
<script type="module">
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

const $ = (id) => document.getElementById(id);
const W = %%W%%, H = %%H%%, TALL = H > W, BEAT = %%BEAT%%, DUR = %%DUR%%;
const B = (n) => n * BEAT;
const CLIPS = %%CLIPS%%, PLATES = %%PLATES%%, CUES = %%CUESJSON%%;
const L = %%LAYERS%%, FP = %%BUILDINGS%%;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lin = (t, a, b) => clamp((t - a) / (b - a));
const ss = (k) => k * k * (3 - 2 * k);
const out3 = (k) => 1 - Math.pow(1 - k, 3);

// ------------------------------------------------------------ terrain
const [X0, Y0, X1, Y1] = L.bbox_utm;
const KW = (X1 - X0) / 1000, KD = (Y1 - Y0) / 1000, EX = 2.1;
const dw = L.dem.w, dh = L.dem.h;
const demB64 = %%DEM%%;
const demBin = atob(demB64), demBytes = new Uint8Array(demBin.length);
for (let i = 0; i < demBin.length; i++) demBytes[i] = demBin.charCodeAt(i);
const demU = new Uint16Array(demBytes.buffer), dem = new Float32Array(demU.length);
let zmin = 1e9; for (let i = 0; i < dem.length; i++) { dem[i] = demU[i] / 10; if (dem[i] < zmin) zmin = dem[i]; }
function cat(a, b, c, d, t) { return 0.5 * ((2*b) + (-a+c)*t + (2*a-5*b+4*c-d)*t*t + (-a+3*b-3*c+d)*t*t*t); }
function demAt(u, v) {                         // bicubic, so the upsampled terrain has no facets
  const x = clamp(u, 0, 1) * (dw - 1), y = clamp(v, 0, 1) * (dh - 1), xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
  const g = (i, j) => dem[clamp(j, 0, dh - 1) * dw + clamp(i, 0, dw - 1)];
  const r = [];
  for (let j = -1; j <= 2; j++) r.push(cat(g(xi-1,yi+j), g(xi,yi+j), g(xi+1,yi+j), g(xi+2,yi+j), fx));
  return cat(r[0], r[1], r[2], r[3], fy);
}
const hy = (m) => (m - zmin) / 1000 * EX;
const CU = 0.537, CV = 0.455;                  // the middle of Swannanoa's outlines
const wx = (u) => (u - 0.5) * KW, wz = (v) => (v - 0.5) * KD;
const CX = wx(CU), CZ = wz(CV);

const renderer = new THREE.WebGLRenderer({ canvas: $("gl"), antialias: true, preserveDrawingBuffer: true, powerPreference: "high-performance" });
renderer.setPixelRatio(1); renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
const camera = new THREE.PerspectiveCamera(TALL ? 58 : 34, W / H, 0.02, 60);

const GW = 1296, GH = 900;
const geo = new THREE.PlaneGeometry(KW, KD, GW - 1, GH - 1); geo.rotateX(-Math.PI / 2);
const pos = geo.attributes.position, uva = geo.attributes.uv;
for (let i = 0; i < pos.count; i++) pos.setY(i, hy(demAt(uva.getX(i), 1 - uva.getY(i))));
geo.computeVertexNormals();

const texLoad = (src) => new Promise((res, rej) => { new THREE.TextureLoader().load(src, (t) => {
  t.colorSpace = THREE.NoColorSpace; t.anisotropy = 12; res(t); }, undefined, rej); });
const overlay = (draw) => { const c = document.createElement("canvas"); c.width = 2048; c.height = 1422; const x = c.getContext("2d");
  draw(x, c); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.NoColorSpace; t.anisotropy = 12; return t; };
const P = (x, c, pts) => { x.beginPath(); pts.forEach((p, i) => { const a = p[0]*c.width, b = p[1]*c.height; i ? x.lineTo(a, b) : x.moveTo(a, b); }); };
const uniforms = {
  uPost: { value: null }, uHeat: { value: null }, uRoads: { value: null }, uSec: { value: null }, uLz: { value: null },
  uR: { value: 0 }, uC: { value: new THREE.Vector2(CX, CZ) }, uRing: { value: 0 }, uImg: { value: 0 }, uKey: { value: 0 }, uRim: { value: 0 }, uCont: { value: 0 },
  uHeatA: { value: 0 }, uRoadA: { value: 0 }, uSecA: { value: 0 }, uLzA: { value: 0 }, uL: { value: new THREE.Vector3(1, 0.2, 0) }, uCam: { value: new THREE.Vector3() },
};
const terrain = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms,
  vertexShader: `varying vec2 vUv; varying vec3 vN; varying vec3 vP; void main(){ vUv = uv; vN = normal; vP = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: `
  uniform sampler2D uPost, uHeat, uRoads, uSec, uLz; uniform float uR, uRing, uImg, uKey, uRim, uCont, uHeatA, uRoadA, uSecA, uLzA;
  uniform vec2 uC; uniform vec3 uL, uCam; varying vec2 vUv; varying vec3 vN; varying vec3 vP;
  void main(){
    vec3 N = normalize(vN), V = normalize(uCam - vP), Ld = normalize(uL);
    float nv = max(dot(N, V), 0.0), rim = pow(1.0 - nv, 4.0), nl = max(dot(N, Ld), 0.0), key = pow(nl, 2.2);
    float m = vP.y / ${EX.toFixed(2)} * 1000.0 / 20.0, cl = abs(fract(m - 0.5) - 0.5) / max(fwidth(m), 1e-4), line = 1.0 - smoothstep(0.0, 1.1, cl);
    vec3 base = vec3(0.006, 0.0065, 0.0075) + vec3(0.62, 0.70, 0.84) * key * uKey + vec3(0.8, 0.84, 0.92) * rim * key * uRim * 1.4 + vec3(0.10, 0.12, 0.15) * line * uCont;
    float d = distance(vP.xz, uC);
    float mask = 1.0 - smoothstep(uR - 0.05, uR, d);
    vec3 im = texture2D(uPost, vUv).rgb;
    float g = dot(im, vec3(0.3, 0.59, 0.11)); im = mix(vec3(g), im, 0.82); im = pow(im, vec3(1.25)) * (0.42 + 1.05 * (0.25 + 0.75 * nl));
    vec3 col = mix(base, im, mask * uImg);
    vec4 h = texture2D(uHeat, vUv); col = mix(col, h.rgb * 0.92, clamp(h.a * 1.25, 0.0, 1.0) * uHeatA);
    vec4 r = texture2D(uRoads, vUv); col = mix(col, r.rgb * 1.6, r.a * uRoadA);
    vec4 s = texture2D(uSec, vUv); col = mix(col, s.rgb * 1.3, s.a * uSecA);
    vec4 z = texture2D(uLz, vUv); col = mix(col, z.rgb * 1.4, z.a * uLzA);
    float ring = exp(-pow((d - uR) / 0.030, 2.0)), halo = exp(-pow((d - uR) / 0.16, 2.0));
    col += (vec3(1.0, 0.92, 0.84) * ring * 2.4 + vec3(1.0, 0.36, 0.12) * halo * 0.42) * uRing;
    float fog = smoothstep(4.4, 10.0, length(uCam - vP));
    gl_FragColor = vec4(mix(col, vec3(0.0), fog), 1.0);
  }` }));
terrain.material.extensions = { derivatives: true };
scene.add(terrain);

// buildings: neutral blocks that rise as the ring reaches them
const BN = FP.length;
const box = new THREE.BoxGeometry(1, 1, 1); box.translate(0, 0.5, 0);
const bu = { uR: { value: 0 }, uAmt: { value: 0 }, uH: { value: 1 } };
const inst = new THREE.InstancedMesh(box, new THREE.ShaderMaterial({ uniforms: bu,
  vertexShader: `attribute float iD; varying float vH; varying float vT; varying float vUp; uniform float uR; uniform float uH;
    void main(){ float k = clamp((uR - iD) / 0.05, 0.0, 1.0); vH = k * uH; vT = exp(-max(uR - iD, 0.0) / 0.07); vUp = normal.y; vec3 p = position; p.y *= k * k * (3.0 - 2.0 * k); p *= uH;
      gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(p, 1.0); }`,
  fragmentShader: `varying float vH; varying float vT; varying float vUp; uniform float uAmt; void main(){ if (vH <= 0.0) discard;
    vec3 c = mix(vec3(0.26, 0.27, 0.30), vec3(0.74, 0.73, 0.70), clamp(vUp, 0.0, 1.0)); c = mix(c, vec3(1.0, 0.72, 0.5) * 2.4, vT); gl_FragColor = vec4(c * uAmt, 1.0); }` }), BN);
const iD = new Float32Array(BN), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s3 = new THREE.Vector3(), p3 = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
FP.forEach((b, i) => {
  const x = wx(b[0]), z = wz(b[1]);
  p3.set(x, hy(demAt(b[0], b[1])) - 0.002, z); q.setFromAxisAngle(up, b[4] * Math.PI / 180);
  s3.set(Math.max(b[2], 7) * 1.15 / 1000, 0.014, Math.max(b[3], 6) * 1.15 / 1000);
  m4.compose(p3, q, s3); inst.setMatrixAt(i, m4); iD[i] = Math.hypot(x - CX, z - CZ);
});
const sorted = Float32Array.from(iD).sort();
box.setAttribute("iD", new THREE.InstancedBufferAttribute(iD, 1));
inst.frustumCulled = false; scene.add(inst);

const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.5, 0.6, 0.82); composer.addPass(bloom);

// camera path: key frames in target-relative polar form [beat, azimuth, elevation, distance, target x, target z]
const CAM = %%CAM%%;
const tv = new THREE.Vector3(), cv = new THREE.Vector3();
function camAt(b) {
  let i = 0; while (i < CAM.length - 2 && b > CAM[i + 1][0]) i++;
  const a = CAM[i], c = CAM[i + 1], k = ss(lin(b, a[0], c[0])), v = (j) => a[j] + (c[j] - a[j]) * k;
  const az = v(1) * Math.PI / 180, el = v(2) * Math.PI / 180, d = v(3), tx = CX + v(4), tz = CZ + v(5);
  tv.set(tx, hy(demAt(tx / KW + 0.5, tz / KD + 0.5)), tz);
  cv.set(tv.x + d * Math.cos(el) * Math.sin(az), tv.y + d * Math.sin(el), tv.z + d * Math.cos(el) * Math.cos(az));
  camera.position.copy(cv); camera.lookAt(tv);
  camera.updateMatrixWorld();
}
const RSTART = B(36), RTOWN = B(47), REND = B(50), RM = sorted[BN - 1] + 0.06;
function ringR(t) { if (t < RSTART) return 0;
  if (t < RTOWN) return 0.002 + RM * Math.pow(lin(t, RSTART, RTOWN), 1.5);
  return RM + 7.0 * Math.pow(lin(t, RTOWN, REND), 2.0); }

async function drawTerrain(t) {
  const b = t / BEAT;
  camAt(b);
  const R = ringR(t);
  const u = uniforms;
  u.uR.value = R; bu.uR.value = R; bu.uAmt.value = lin(t, RSTART, RSTART + 0.1);
  u.uRing.value = lin(t, RSTART - 0.02, RSTART + 0.06) * (1 - lin(t, REND - 0.4, REND + 0.2));
  u.uImg.value = 1; u.uKey.value = 0.95 * ss(lin(b, 30, 33)); u.uRim.value = u.uKey.value; u.uCont.value = 0.8 * ss(lin(b, 31, 35));
  const a = (b - 30) * 0.022 + 2.5; u.uL.value.set(Math.cos(a), 0.17, Math.sin(a));
  u.uHeatA.value = ss(lin(b, 56, 57)) * (1 - 0.72 * ss(lin(b, 58, 58.8)) + 0.5 * ss(lin(b, 62, 62.8))); u.uRoadA.value = ss(lin(b, 58, 58.6)); u.uLzA.value = ss(lin(b, 60, 60.6)); u.uSecA.value = ss(lin(b, 62, 62.6));
  bu.uH.value = 1 - ss(lin(b, 55, 56.2)); inst.visible = bu.uH.value > 0.001;
  u.uCam.value.copy(camera.position);
  composer.render();
  const f = BN ? (() => { let lo = 0, hi = BN; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] <= R) lo = m + 1; else hi = m; } return lo; })() / BN : 0;
  const done = t >= B(47) ? 1 : f;
  $("hn").textContent = String(Math.round(893 * done)).padStart(3, "0");
  const s = Math.round(88 * done); $("ht").textContent = `0${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ------------------------------------------------------------ the edit
const pad = (n) => String(n).padStart(4, "0");
const clipBase = (n) => `%%CLIPDIR%%/${n}/`;
const cache = new Map();
function img(src) { if (!cache.has(src)) { const i = new Image(); i.src = src; cache.set(src, i.decode().catch(() => {}).then(() => i)); } return cache.get(src); }
async function setImg(el, src) { if (el.dataset.src !== src) { await img(src); el.src = src; el.dataset.src = src; await el.decode().catch(() => {}); } }
const cues = [...document.querySelectorAll(".t")];

window.DURATION = DUR;
window.render = async (t) => {
  const b = t / BEAT;
  // footage
  const c = CLIPS.find((x) => b >= x[0] && b < x[1]);
  if (c) { const f = Math.floor((t - B(c[0])) * 30) + 1, e = $("clip"); await setImg(e, clipBase(c[2]) + pad(Math.min(f, c[3])) + ".jpg");
    const k = lin(t, B(c[0]), B(c[1])); e.style.opacity = 1; e.style.transform = `scale(${1.07 - 0.07 * out3(k)})`;
  } else $("clip").style.opacity = 0;
  // stills and app screens
  const p = PLATES.find((x) => b >= x[0] && b < x[1]);
  if (p) { const e = $("plate"), app = p[2].includes("app2"), o = TALL ? p[4] : p[3], z = TALL ? o[1] : o[0], ox = TALL ? o[2] : o[1], oy = TALL ? o[3] : o[2];
    await setImg(e, p[2]); e.style.objectPosition = TALL ? `${o[0]}% 50%` : "50% 50%"; const pw = $("pw"); pw.style.height = TALL && app ? "1060px" : "100%";
    const mk = TALL && app ? "linear-gradient(to bottom,#000 86%,transparent 100%)" : "none"; pw.style.webkitMaskImage = mk; pw.style.maskImage = mk;
    const k = lin(t, B(p[0]), B(p[1])); e.style.opacity = 1; e.style.transformOrigin = `${ox}% ${oy}%`; e.style.transform = `scale(${z * (1.05 - 0.05 * out3(k))})`;
  } else $("plate").style.opacity = 0;
  // terrain
  const onT = b >= 30 && b < 64;
  if (onT) await drawTerrain(t);
  $("gl").style.opacity = onT ? 1 : 0;
  $("shade").style.opacity = (c || p || (b >= 50 && b < 64)) ? 1 : 0;
  // HUD
  $("hud").style.opacity = (b >= 37 && b < 50) ? 1 : 0;
  // type: it appears on the beat with a short settle, and cuts away
  cues.forEach((el) => { const a = +el.dataset.a * BEAT, z = +el.dataset.z * BEAT, on = t >= a && t < z;
    el.style.opacity = on ? 1 : 0;
    if (on) { const k = out3(lin(t, a, a + 0.22)); const mid = el.classList.contains("mid");
      el.style.transform = (mid ? "translateY(-50%) " : "") + `translateY(${(1 - k) * 22}px) scale(${1 + (1 - k) * 0.02})`; } });
  // proof
  $("proof").style.opacity = (b >= 80 && b < 88) ? 1 : 0;
  if (b >= 80 && b < 88) { const k = out3(lin(b, 80, 80.5));
    document.querySelector("#proof .p").style.transform = `scale(${1.08 - 0.08 * k})`;
    document.querySelector("#proof .a").style.opacity = b >= 82 ? 1 : 0; document.querySelector("#proof .b").style.opacity = b >= 84 ? 1 : 0; }
  // logo: the Blender plate, then it lifts to make room for the wordmark
  const LT = B(96), onL = t >= LT;
  $("logo").style.opacity = onL ? 1 : 0; $("end").style.opacity = onL ? 1 : 0;
  if (onL) { const f = Math.min(190, Math.floor((t - LT) * 30)); await setImg($("logo"), `%%LOGODIR%%/${pad(f)}.jpg`);
    const y = f <= 40 ? 39 : f <= 60 ? 39 - 6 * (f - 40) / 20 : f <= 72 ? 33 : f <= 100 ? 33 - 13 * (f - 72) / 28 : 20, mk = `linear-gradient(to bottom, transparent ${y}%, #000 ${y + 5}%, #000 90%, transparent 100%)`;
    $("logo").style.webkitMaskImage = mk; $("logo").style.maskImage = mk;
    const k = ss(lin(b, 106, 107.4)), pull = 1 - %%PULL%% * ss(lin(f, 100, 134)); $("logo").style.transform = `translateY(${-%%LIFT%% * k}px) scale(${pull * (1 - %%SHRINK%% * k)})`;
    const q = (s, a, d = 0.7) => document.querySelector("#end " + s).style.opacity = ss(lin(b, a, a + d));
    q(".w", 107); q(".s", 108.2); q(".u", 109.2); q(".f", 110); }
  // two-frame flashes on the biggest hits
  const fl = [[B(36), .9], [B(50), .35], [B(102), .2]].map(([a, v]) => (t >= a && t < a + 0.067) ? v : 0);
  $("flash").style.opacity = Math.max(...fl);
};
window.READY = (async () => {
  await document.fonts.load('700 40px "Disp"');
  const [post, heat] = await Promise.all([texLoad("%%POST%%"), texLoad("%%HEAT%%")]);
  uniforms.uPost.value = post; uniforms.uHeat.value = heat;
  uniforms.uRoads.value = overlay((x, c) => { x.lineCap = "round"; const st = { blocked: ["#FF3B1F", 13, []], debris: ["#FFB020", 11, [16, 14]], bridge: ["#FFD166", 11, [5, 15]] };
    for (const r of L.roads) { const s = st[r.s] || st.blocked; x.strokeStyle = s[0]; x.lineWidth = s[1]; x.setLineDash(s[2]); P(x, c, r.p); x.stroke(); } });
  uniforms.uSec.value = overlay((x, c) => { x.font = "700 44px Disp"; for (const s of L.sectors) { x.strokeStyle = "#F5F3EE"; x.lineWidth = 6; P(x, c, s.p); x.closePath(); x.stroke();
    const a = s.p[3][0]*c.width + 16, b = s.p[3][1]*c.height + 56; x.fillStyle = "#F5F3EE"; x.fillRect(a - 8, b - 44, x.measureText(String(s.priority)).width + 16, 56); x.fillStyle = "#000"; x.fillText(String(s.priority), a, b); } });
  uniforms.uLz.value = overlay((x, c) => { for (const p of L.lz) { const a = p.p[0]*c.width, b = p.p[1]*c.height; x.strokeStyle = "#7CFFCB"; x.lineWidth = 6; x.beginPath(); x.arc(a, b, 20, 0, 7); x.stroke(); x.fillStyle = "#7CFFCB"; x.beginPath(); x.arc(a, b, 6, 0, 7); x.fill(); } });
  return true;
})();
</script></body></html>
"""


def main() -> None:
    aspect = sys.argv[1] if len(sys.argv) > 1 else "16x9"
    W, H = SIZES[aspect]
    tall = H > W
    sz = dict(PAD=84 if tall else 110, BOT=620 if tall else 96, BIG=104 if tall else 112, HUGE=124 if tall else 190, MID=74 if tall else 84,
              LOW=32 if tall else 30, LOWB=430 if tall else 44, SRCY=250 if tall else 170, TAGT=260 if tall else 84, HUDT=280 if tall else 96,
              HUDN=128 if tall else 104, HUDG=30 if tall else 22, PCT=340 if tall else 330, PG1=56 if tall else 40, PG2=38 if tall else 24,
              PA=52 if tall else 44, PMAX=920 if tall else 1160, LOGO=1200 if tall else 1920, LOGOH=600 if tall else 960, WT=990 if tall else 566, WORD=170 if tall else 136,
              ST=1200 if tall else 716, STAG=62 if tall else 50, UT=1316 if tall else 796, FB=300 if tall else 40, FINE=24 if tall else 19,
              RALIGN="left" if tall else "right", LIFT=240 if tall else 226, SHRINK=0.2 if tall else 0.5, PULL=0.0 if tall else 0.2, )
    cam = [  # beat, azimuth, elevation, distance, target offset x, z (km from the town)
        [30, 118, 5.5, 2.7, -0.9, 0.5], [36, 96, 7.5, 2.5, -0.5, 0.2], [44, 70, 15, 2.5, 0, 0], [50, 44, 27, 3.1, 0, 0],
        [56, 18, 40, 3.5, 0, 0], [58, 8, 52, 4.0, 0.4, 0.35], [60, 0, 56, 4.1, 0.5, 0.4], [62, -6, 58, 4.2, 0.3, 0.2], [64, -12, 56, 3.9, 0.1, 0]]
    swap = {"After Helene and Milton,<br>4% of FEMA's incident workforce<br>was available.": "After Helene<br>and Milton,<br>4% of FEMA's<br>incident workforce<br>was available."} if tall else {}
    rows = CUES
    if tall:  # Reels and Shorts keep type clear of the right edge, so this line becomes two shots
        rows = [r for r in CUES if r[2] != "Hurricane Helene.<br>Western North Carolina."] + [(3, 5, "Hurricane<br>Helene.", "big"), (5, 7, "Western<br>North Carolina.", "big")]
    cues = "".join(f'<div class="t {c}" data-a="{a}" data-z="{z}">{swap.get(txt, txt)}</div>' for a, z, txt, c in rows)
    with open(os.path.join(TERR, "dem.u16"), "rb") as fh:
        dem = base64.b64encode(fh.read()).decode()
    L = json.load(open(os.path.join(TERR, "layers.json"), encoding="utf-8"))
    L = {k: L[k] for k in ("bbox_utm", "dem", "roads", "sectors", "lz")}
    fp = json.load(open(os.path.join(A, "v4", "buildings.json"), encoding="utf-8"))
    frames = {n: len(os.listdir(os.path.join(A, "v4", "clips", n))) for _a, _b, n in CLIPS}
    plates = [[a, b, rel(os.path.join(A, p)), w, t] for a, b, p, w, t in PLATES]
    subs = {"%%FONT%%": rel(os.path.join(A, "fonts", "archivo-latin-standard-normal.woff2")), "%%BEAT%%": repr(BEAT), "%%DUR%%": repr(116 * BEAT),
            "%%CLIPS%%": json.dumps([[a, b, n, frames[n]] for a, b, n in CLIPS]), "%%PLATES%%": json.dumps(plates), "%%CUESJSON%%": "[]",
            "%%LAYERS%%": json.dumps(L, separators=(",", ":")), "%%BUILDINGS%%": json.dumps(fp, separators=(",", ":")), "%%DEM%%": json.dumps(dem),
            "%%CAM%%": json.dumps(cam), "%%CUES%%": cues, "%%CLIPDIR%%": rel(os.path.join(A, "v4", "clips")), "%%LOGODIR%%": rel(os.path.join(A, "v4", "logo")),
            "%%POST%%": rel(os.path.join(TERR, "post.jpg")), "%%HEAT%%": rel(os.path.join(TERR, "heat.png")), "%%W%%": str(W), "%%H%%": str(H)}
    subs.update({f"%%{k}%%": str(v) for k, v in sz.items()})
    html = HTML
    for k, v in subs.items():
        html = html.replace(k, v)
    assert "%%" not in html.replace("100%%", ""), [x for x in html.split("%%")[1:6:2]]
    out = os.path.join(BUILD, f"composition_v4_{aspect}.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote", os.path.relpath(out, HERE), 116 * BEAT, "s", tall)


if __name__ == "__main__":
    main()
