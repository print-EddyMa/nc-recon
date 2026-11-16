"""NC Recon launch film v7: `python3 video/launch/compose_v7.py [16x9|9x16]`.

The calmer cut. Real launch films were measured first: product launches hold a shot for about
2.4 to 6.5 s, the last cut held for about 1.2 s, so scenes now change on the bar of the music and
every line of type stays up for at least 1.7 s. "Horizons" by Scott Buckley has a beat of 0.5625 s;
slowed 0.7% that is 17 frames at 30 fps, the beat here. Lines stay up for 2 to 4.5 s. The music peaks on the logo.
Writes build/composition_v7_<aspect>.html and build/cues_v7.json for score_v8.py.

Real material only: NOAA GOES-16 frames, public-domain DVIDS footage, Civil Air Patrol
photographs, NVIDIA SimReady models (CC BY 4.0), our own data and app. Per-building damage
appears only for the showcase home.
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
V5 = os.path.join(A, "v5")
TERR = os.path.join(ROOT, "site", "assets", "terrain")
BEAT = 17 / 30
END_B = 127
SIZES = {"16x9": (1920, 1080), "9x16": (1080, 1920)}

# paper tones: close in brightness, so the fast cuts do not strobe
CREAM, BONE, SAND, SAGE, SKY, CLAY = "#E9DFC9", "#DCD8CC", "#D9C7A4", "#C9CFB4", "#BCCBD0", "#D8B79A"
DARK = "#17171A"
# The flash is the job itself: one print for each damage assessment, landing on a growing pile
# while the tally runs to the real total. Each print holds for a full beat or two.
LENS = [34, 34, 17, 17, 17, 17, 17, 17, 17, 17]
PRINTS = [4, 9, 19, 18, 22, 28, 35, 46, 49, 51]
FLASH = [(n, "photo", f"{i:02d}", CREAM, "") for n, i in zip(LENS, PRINTS)]
# the field kit, as 3D objects, under "Ready for the field"
KIT = [(88 * 17, 34, "3d", "ppe_helmet_hardHat_a01", DARK, ""), (90 * 17, 34, "3d", "safety_firstAidKit_case_plastic_a01", DARK, "")]
FLASH_B0 = 8
assert sum(s[0] for s in FLASH) == 204, sum(s[0] for s in FLASH)

# beat, end beat, clip:start frame, speed
FOOT = [(20, 24, "wreck:0", 1.0), (24, 28, "river:30", 0.8), (28, 30, "balls:10", 1.0), (30, 32, "toycar:20", 1.0)]
# beat, end beat, image, 16:9 [zoom, ox, oy], 9:16 [pos x, zoom, ox, oy]
PLATES = [(72, 74, "plates/swannanoa_home_pre.jpg", [1.15, 40, 45], [50, 1.15, 40, 45]), (74, 76, "plates/swannanoa_home_post.jpg", [1.15, 40, 45], [50, 1.15, 40, 45]), (76, 80, "plates/swannanoa_home_post.jpg", [2.2, 50, 50], [50, 1.5, 50, 50]),
          (80, 84, "app2/verify.png", [2, 34, 40], [30, 1.25, 30, 45]), (84, 88, "app2/stepper_found.png", [2.4, 100, 8], [100, 1.8, 100, 8])]
# beat, end beat, text (* marks the orange period), class
CUES = [
    (0, 4, "Hurricane<br>Helene*", "slam"), (0, 8, "NOAA GOES-16. September 26, 2024.", "tag"), (4, 8, "Headed for<br>the mountains*", "slam"),
    (8, 16, "Then someone<br>has to check<br>every one<b>.</b>", "ink"),
    (20, 24, "80,000 damage<br>assessments*", "slam fit"), (24, 28, "House<br>by house*", "slam"), (20, 28, "DHS Science and Technology, October 7, 2024", "tag"),
    (28, 32, "Everything<br>in its path*", "slam"), (28, 32, "Swannanoa, five weeks after", "tag"),
    (36, 40, "What if the map<br>came first?", "mid"),
    (52, 60, "893 buildings<b>.</b><br>88 seconds<b>.</b><br>One laptop*", "slam small"),
    (60, 63, "Damage*", "slam"), (63, 66, "Roads<br>cut*", "slam"), (66, 69, "Landing<br>zones*", "slam"), (69, 72, "Search<br>sectors*", "slam"),
    (72, 74, "Before", "tag"), (74, 76, "After", "tag"), (76, 80, "Destroyed*<br>76% likely", "slam"), (76, 80, "This home", "tag"),
    (80, 84, "People check<br>the hard calls*", "slam small"), (84, 88, "Type a FEMA<br>disaster<br>number*", "slam small"), (88, 92, "Ready for<br>the field*", "slam small"),
    (92, 94, "FEMA survey fields<br>GeoPackage<br>KML for TAK", "mid"),
    (102, 105, "Free and<br>open source*", "slam small"), (105, 108, "Built after Helene,<br>in North Carolina*", "slam tiny"),
]
# small picture punches, only on the big moments
HITS = [(40, "ring", 0.4), (52, "hit", 0.2), (76, "hit", 0.2), (112, "drop", 0.3)]


def rel(p: str) -> str:
    return os.path.relpath(p, BUILD)


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>NC Recon launch</title>
<style>
@font-face { font-family:"Disp"; font-weight:100 900; font-stretch:62% 125%; src:url(%%FONT%%); }
* { box-sizing:border-box; }
html,body { margin:0; width:%%W%%px; height:%%H%%px; overflow:hidden; background:#000; color:#F5F3EE; font-family:"Disp",Helvetica,Arial,sans-serif; }
.L { position:absolute; inset:0; }
#stage { position:absolute; inset:0; transform-origin:50% 50%; overflow:hidden; }
#gl { position:absolute; inset:0; width:%%W%%px; height:%%H%%px; display:block; }
#goes,#clip,#plate,#cov { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:0; }
#pw { position:absolute; left:0; top:0; width:100%; height:100%; overflow:hidden; }
#ring { position:absolute; inset:0; opacity:0; }
#ring i { position:absolute; left:50%; top:50%; width:%%RING%%px; height:%%RING%%px; margin:calc(%%RING%%px / -2) 0 0 calc(%%RING%%px / -2); border:%%RINGW%%px solid #F5F3EE; border-radius:50%; }
#spec { opacity:0; }
.ph { position:absolute; left:%%PHX%%px; top:%%PHY%%px; width:%%PHW%%px; height:%%PHH%%px; object-fit:cover; border:12px solid #FBF8F0; box-shadow:0 12px 34px rgba(30,24,16,.3); }
#tally { position:absolute; left:%%TX%%px; top:%%TY%%px; opacity:0; color:#17171A; }
#tally .n { font-size:%%TN%%px; font-weight:840; font-stretch:125%; letter-spacing:-.04em; line-height:.95; font-variant-numeric:tabular-nums; }
#tally .k { font-size:%%TK%%px; font-weight:640; margin-top:10px; }
.ink { left:%%TX%%px; top:%%IY%%px; width:%%IW%%px; font-size:%%IF%%px; font-weight:820; font-stretch:125%; letter-spacing:-.025em; line-height:1.0; text-transform:uppercase; color:#17171A; }
.ink b { color:#FF5A1F; font-weight:820; }
#specimg { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); max-width:%%SPW%%px; max-height:%%SPH%%px; }
#grain { background:url(%%PAPER%%); mix-blend-mode:multiply; opacity:0; }
#shade { background:linear-gradient(180deg,rgba(0,0,0,.05) 30%,rgba(0,0,0,.66) 100%); opacity:0; }
#lab { position:absolute; left:%%PAD%%px; bottom:%%LABB%%px; opacity:0; font-size:%%LAB%%px; font-weight:560; color:#17171A; letter-spacing:.005em; display:flex; gap:.7em; align-items:center; }
#lab i { display:inline-block; width:.62em; height:.62em; background:#FF5A1F; transform:rotate(19deg); }
#lab span { font-variant-numeric:tabular-nums; opacity:.62; }
#logo { position:absolute; left:50%; top:50%; width:%%LOGO%%px; height:%%LOGO%%px; margin:-%%LOGOH%%px 0 0 -%%LOGOH%%px; opacity:0; filter:contrast(1.1); }
#flash { background:#fff; opacity:0; }
.t { position:absolute; opacity:0; }
.slam { left:%%PAD%%px; right:%%PAD%%px; bottom:%%BOT%%px; font-size:%%SLAM%%px; font-weight:820; font-stretch:125%; letter-spacing:-.03em; line-height:.92; text-transform:uppercase; overflow:hidden; padding-bottom:.08em; }
.slam.small { font-size:%%SMALL%%px; } .slam.tiny { font-size:%%TINY%%px; } .slam.fit { font-size:%%FIT%%px; } .slam.r { text-align:%%RALIGN%%; }
.slam b { color:#FF5A1F; font-weight:820; }
.slam .in { display:block; will-change:transform; }
.mid { left:%%PAD%%px; right:%%PAD%%px; top:50%; transform:translateY(-50%); text-align:center; font-size:%%MID%%px; font-weight:800; font-stretch:125%; letter-spacing:-.025em; line-height:1.0; text-transform:uppercase; }
.tag { left:%%PAD%%px; right:%%PAD%%px; top:%%TAGT%%px; font-size:%%LOW%%px; font-weight:520; }
#hud { position:absolute; left:%%PAD%%px; top:%%HUDT%%px; opacity:0; font-variant-numeric:tabular-nums; }
#hud .n { font-size:%%HUDN%%px; font-weight:820; letter-spacing:-.03em; line-height:.95; font-stretch:125%; }
#hud .k { font-size:%%LOW%%px; font-weight:500; color:rgba(245,243,238,.8); margin:4px 0 %%HUDG%%px; }
.card { background:#000; opacity:0; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:0 %%PAD%%px; }
#four .p,#proof .p { font-size:%%PCT%%px; font-weight:840; letter-spacing:-.06em; line-height:.84; font-stretch:125%; }
#four .p { color:#FF5A1F; }
#proof .p small { font-size:.42em; color:#FF5A1F; margin-left:.04em; letter-spacing:-.02em; }
.a { margin-top:%%PG1%%px; font-size:%%PA%%px; font-weight:620; line-height:1.1; letter-spacing:-.012em; max-width:%%PMAX%%px; }
.b { margin-top:%%PG2%%px; font-size:%%LOW%%px; font-weight:460; color:rgba(245,243,238,.68); line-height:1.3; max-width:%%PMAX%%px; }
#end { opacity:0; }
#end .w { position:absolute; left:0; right:0; top:%%WT%%px; text-align:center; font-size:%%WORD%%px; font-weight:820; font-stretch:125%; letter-spacing:-.025em; white-space:pre; font-variant-numeric:tabular-nums; }
#end .s { position:absolute; left:%%PAD%%px; right:%%PAD%%px; top:%%ST%%px; text-align:center; font-size:%%STAG%%px; font-weight:620; letter-spacing:-.01em; opacity:0; }
</style>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
</head><body><div id="stage">
<canvas id="gl" width="%%W%%" height="%%H%%"></canvas>
<img id="goes" alt=""><div id="pw"><img id="plate" alt=""><div id="ring"><i></i></div></div><img id="clip" alt=""><img id="cov" alt="">
<div class="L" id="spec"><img id="specimg" alt=""><img class="ph" id="ph0" alt=""><img class="ph" id="ph1" alt=""></div><div class="L" id="grain"></div>
<div id="lab"><i></i><b id="labt"></b><span id="labn"></span></div>
<div id="tally"><div class="n" id="tn">0</div><div class="k">damage assessments</div></div>
<div class="L" id="shade"></div>
<div id="hud"><div class="n" id="hn">000</div><div class="k">buildings read</div><div class="n" id="ht">00:00</div><div class="k">elapsed</div></div>
%%CUEHTML%%
<div class="L card" id="four"><div class="p">4%</div><div class="a">of FEMA's incident workforce was available after Helene and Milton.</div><div class="b">GAO-25-108598</div></div>
<div class="L card" id="proof"><div class="p">96<small>%</small></div>
  <div class="a">of the time, CAL FIRE inspectors agreed when NC Recon called a building destroyed or badly damaged after the Eaton fire.</div>
  <div class="b">Precision 95.7%, recall 94.2%, 2,246 buildings. Wildfire model, one held-out test. Flood accuracy still being validated.</div></div>
<img id="logo" alt="">
<div class="L" id="end"><div class="w" id="word"></div><div class="s">Every building, after the disaster.</div></div>
<div class="L" id="flash"></div>
</div>
<script type="module">
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const $ = (id) => document.getElementById(id);
const W = %%W%%, H = %%H%%, TALL = H > W, BEAT = %%BEAT%%, DUR = %%DUR%%;
const B = (n) => n * BEAT;
const FOOT = %%FOOT%%, PLATES = %%PLATES%%, SHOTS = %%SHOTS%%, HITS = %%HITS%%, F0 = %%F0%%;
const L = %%LAYERS%%, FP = %%BUILDINGS%%;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lin = (t, a, b) => clamp((t - a) / (b - a));
const ss = (k) => k * k * (3 - 2 * k);
const out3 = (k) => 1 - Math.pow(1 - k, 3);
const out5 = (k) => 1 - Math.pow(1 - k, 5);

// ------------------------------------------------------------ terrain, as in v4
const [X0, Y0, X1, Y1] = L.bbox_utm;
const KW = (X1 - X0) / 1000, KD = (Y1 - Y0) / 1000, EX = 2.1;
const dw = L.dem.w, dh = L.dem.h;
const demBin = atob(%%DEM%%), demBytes = new Uint8Array(demBin.length);
for (let i = 0; i < demBin.length; i++) demBytes[i] = demBin.charCodeAt(i);
const demU = new Uint16Array(demBytes.buffer), dem = new Float32Array(demU.length);
let zmin = 1e9; for (let i = 0; i < dem.length; i++) { dem[i] = demU[i] / 10; if (dem[i] < zmin) zmin = dem[i]; }
function cat(a, b, c, d, t) { return 0.5 * ((2*b) + (-a+c)*t + (2*a-5*b+4*c-d)*t*t + (-a+3*b-3*c+d)*t*t*t); }
function demAt(u, v) {
  const x = clamp(u, 0, 1) * (dw - 1), y = clamp(v, 0, 1) * (dh - 1), xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
  const g = (i, j) => dem[clamp(j, 0, dh - 1) * dw + clamp(i, 0, dw - 1)];
  const r = []; for (let j = -1; j <= 2; j++) r.push(cat(g(xi-1,yi+j), g(xi,yi+j), g(xi+1,yi+j), g(xi+2,yi+j), fx));
  return cat(r[0], r[1], r[2], r[3], fy);
}
const hy = (m) => (m - zmin) / 1000 * EX;
const CU = 0.537, CV = 0.455, wx = (u) => (u - 0.5) * KW, wz = (v) => (v - 0.5) * KD, CX = wx(CU), CZ = wz(CV);
const renderer = new THREE.WebGLRenderer({ canvas: $("gl"), antialias: true, preserveDrawingBuffer: true, powerPreference: "high-performance", alpha: false });
renderer.setPixelRatio(1); renderer.setSize(W, H, false); renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
const camera = new THREE.PerspectiveCamera(TALL ? 58 : 34, W / H, 0.02, 60);
const GW = 1296, GH = 900;
const geo = new THREE.PlaneGeometry(KW, KD, GW - 1, GH - 1); geo.rotateX(-Math.PI / 2);
const pos = geo.attributes.position, uva = geo.attributes.uv;
for (let i = 0; i < pos.count; i++) pos.setY(i, hy(demAt(uva.getX(i), 1 - uva.getY(i))));
geo.computeVertexNormals();
const texLoad = (src) => new Promise((res, rej) => { new THREE.TextureLoader().load(src, (t) => { t.colorSpace = THREE.NoColorSpace; t.anisotropy = 12; res(t); }, undefined, rej); });
const overlay = (draw) => { const c = document.createElement("canvas"); c.width = 2048; c.height = 1422; const x = c.getContext("2d"); draw(x, c); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.NoColorSpace; t.anisotropy = 12; return t; };
const P = (x, c, pts) => { x.beginPath(); pts.forEach((p, i) => { const a = p[0]*c.width, b = p[1]*c.height; i ? x.lineTo(a, b) : x.moveTo(a, b); }); };
const uniforms = { uPost:{value:null}, uHeat:{value:null}, uRoads:{value:null}, uSec:{value:null}, uLz:{value:null}, uR:{value:0}, uC:{value:new THREE.Vector2(CX,CZ)}, uRing:{value:0}, uImg:{value:0}, uKey:{value:0}, uRim:{value:0}, uCont:{value:0}, uHeatA:{value:0}, uRoadA:{value:0}, uSecA:{value:0}, uLzA:{value:0}, uL:{value:new THREE.Vector3(1,0.2,0)}, uCam:{value:new THREE.Vector3()} };
const terrain = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms,
  vertexShader: `varying vec2 vUv; varying vec3 vN; varying vec3 vP; void main(){ vUv = uv; vN = normal; vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: `uniform sampler2D uPost, uHeat, uRoads, uSec, uLz; uniform float uR, uRing, uImg, uKey, uRim, uCont, uHeatA, uRoadA, uSecA, uLzA; uniform vec2 uC; uniform vec3 uL, uCam; varying vec2 vUv; varying vec3 vN; varying vec3 vP;
  void main(){ vec3 N = normalize(vN), V = normalize(uCam - vP), Ld = normalize(uL);
    float nv = max(dot(N, V), 0.0), rim = pow(1.0 - nv, 4.0), nl = max(dot(N, Ld), 0.0), key = pow(nl, 2.2);
    float m = vP.y / ${EX.toFixed(2)} * 1000.0 / 20.0, cl = abs(fract(m - 0.5) - 0.5) / max(fwidth(m), 1e-4), line = 1.0 - smoothstep(0.0, 1.1, cl);
    vec3 base = vec3(0.006, 0.0065, 0.0075) + vec3(0.62, 0.70, 0.84) * key * uKey + vec3(0.8, 0.84, 0.92) * rim * key * uRim * 1.4 + vec3(0.10, 0.12, 0.15) * line * uCont;
    float d = distance(vP.xz, uC), mask = 1.0 - smoothstep(uR - 0.05, uR, d);
    vec3 im = texture2D(uPost, vUv).rgb; float g = dot(im, vec3(0.3, 0.59, 0.11)); im = mix(vec3(g), im, 0.82); im = pow(im, vec3(1.25)) * (0.42 + 1.05 * (0.25 + 0.75 * nl));
    vec3 col = mix(base, im, mask * uImg);
    vec4 h = texture2D(uHeat, vUv); col = mix(col, h.rgb * 0.92, clamp(h.a * 1.25, 0.0, 1.0) * uHeatA);
    vec4 r = texture2D(uRoads, vUv); col = mix(col, r.rgb * 1.6, r.a * uRoadA);
    vec4 s = texture2D(uSec, vUv); col = mix(col, s.rgb * 1.3, s.a * uSecA);
    vec4 z = texture2D(uLz, vUv); col = mix(col, z.rgb * 1.4, z.a * uLzA);
    float ring = exp(-pow((d - uR) / 0.030, 2.0)), halo = exp(-pow((d - uR) / 0.16, 2.0));
    col += (vec3(1.0, 0.92, 0.84) * ring * 2.4 + vec3(1.0, 0.36, 0.12) * halo * 0.42) * uRing;
    float fog = smoothstep(4.4, 10.0, length(uCam - vP)); gl_FragColor = vec4(mix(col, vec3(0.0), fog), 1.0); }` }));
terrain.material.extensions = { derivatives: true }; scene.add(terrain);
const BN = FP.length, box = new THREE.BoxGeometry(1, 1, 1); box.translate(0, 0.5, 0);
const bu = { uR: { value: 0 }, uAmt: { value: 0 }, uH: { value: 1 } };
const inst = new THREE.InstancedMesh(box, new THREE.ShaderMaterial({ uniforms: bu,
  vertexShader: `attribute float iD; varying float vH; varying float vT; varying float vUp; uniform float uR; uniform float uH;
    void main(){ float k = clamp((uR - iD) / 0.05, 0.0, 1.0); vH = k * uH; vT = exp(-max(uR - iD, 0.0) / 0.07); vUp = normal.y; vec3 p = position; p.y *= k * k * (3.0 - 2.0 * k); p *= uH; gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(p, 1.0); }`,
  fragmentShader: `varying float vH; varying float vT; varying float vUp; uniform float uAmt; void main(){ if (vH <= 0.0) discard;
    vec3 c = mix(vec3(0.26, 0.27, 0.30), vec3(0.74, 0.73, 0.70), clamp(vUp, 0.0, 1.0)); c = mix(c, vec3(1.0, 0.72, 0.5) * 2.4, vT); gl_FragColor = vec4(c * uAmt, 1.0); }` }), BN);
const iD = new Float32Array(BN), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s3 = new THREE.Vector3(), p3 = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
FP.forEach((b, i) => { const x = wx(b[0]), z = wz(b[1]); p3.set(x, hy(demAt(b[0], b[1])) - 0.002, z); q.setFromAxisAngle(up, b[4] * Math.PI / 180);
  s3.set(Math.max(b[2], 7) * 1.15 / 1000, 0.014, Math.max(b[3], 6) * 1.15 / 1000); m4.compose(p3, q, s3); inst.setMatrixAt(i, m4); iD[i] = Math.hypot(x - CX, z - CZ); });
const sorted = Float32Array.from(iD).sort();
box.setAttribute("iD", new THREE.InstancedBufferAttribute(iD, 1)); inst.frustumCulled = false; scene.add(inst);
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera)); composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), 0.55, 0.6, 0.82));
const CAM = %%CAM%%, tv = new THREE.Vector3(), cv = new THREE.Vector3();
function camAt(b) { let i = 0; while (i < CAM.length - 2 && b > CAM[i + 1][0]) i++;
  const a = CAM[i], c = CAM[i + 1], k = ss(lin(b, a[0], c[0])), v = (j) => a[j] + (c[j] - a[j]) * k, az = v(1) * Math.PI / 180, el = v(2) * Math.PI / 180, d = v(3), tx = CX + v(4), tz = CZ + v(5);
  tv.set(tx, hy(demAt(tx / KW + 0.5, tz / KD + 0.5)), tz); cv.set(tv.x + d * Math.cos(el) * Math.sin(az), tv.y + d * Math.sin(el), tv.z + d * Math.cos(el) * Math.cos(az));
  camera.position.copy(cv); camera.lookAt(tv); camera.updateMatrixWorld(); }
const RSTART = B(40), RTOWN = B(48), REND = B(52), RM = sorted[BN - 1] + 0.06;
function ringR(t) { if (t < RSTART) return 0; if (t < RTOWN) return 0.002 + RM * Math.pow(lin(t, RSTART, RTOWN), 1.5); return RM + 7.0 * Math.pow(lin(t, RTOWN, REND), 2.0); }
function drawTerrain(t) { const b = t / BEAT; camAt(b); const R = ringR(t), u = uniforms;
  u.uR.value = R; bu.uR.value = R; bu.uAmt.value = lin(t, RSTART, RSTART + 0.08);
  u.uRing.value = lin(t, RSTART - 0.02, RSTART + 0.06) * (1 - lin(t, REND - 0.4, REND + 0.2));
  u.uImg.value = 1; u.uKey.value = 0.95 * ss(lin(b, 36, 38)); u.uRim.value = u.uKey.value; u.uCont.value = 0.8 * ss(lin(b, 36.5, 39));
  const a = (b - 36) * 0.05 + 2.5; u.uL.value.set(Math.cos(a), 0.17, Math.sin(a));
  u.uHeatA.value = ss(lin(b, 60, 60.5)) * (1 - 0.72 * ss(lin(b, 63, 63.5)) + 0.5 * ss(lin(b, 69, 69.5))); u.uRoadA.value = ss(lin(b, 63, 63.4)); u.uLzA.value = ss(lin(b, 66, 66.4)); u.uSecA.value = ss(lin(b, 69, 69.4));
  bu.uH.value = 1 - ss(lin(b, 59, 60)); inst.visible = bu.uH.value > 0.001; u.uCam.value.copy(camera.position); composer.render();
  let lo = 0, hi = BN; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] <= R) lo = m + 1; else hi = m; }
  const done = t >= RTOWN ? 1 : lo / BN; $("hn").textContent = String(Math.round(893 * done)).padStart(3, "0");
  const s = Math.round(88 * done); $("ht").textContent = `0${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }

// ------------------------------------------------------------ the 3D specimens, one scene each
const models = {}, sCam = new THREE.PerspectiveCamera(TALL ? 30 : 24, W / H, 0.05, 40), sScene = new THREE.Scene();
const key = new THREE.DirectionalLight(0xffffff, 3.2); key.position.set(2.4, 3.4, 3); sScene.add(key);
const fill = new THREE.DirectionalLight(0xfff2e0, 1.1); fill.position.set(-3, 1, 2); sScene.add(fill); sScene.add(new THREE.HemisphereLight(0xffffff, 0x8a8074, 1.2));
async function loadModels(names) { const lo = new GLTFLoader(); lo.setMeshoptDecoder(MeshoptDecoder);
  await Promise.all(names.map(async (n) => { const g = await lo.loadAsync(`%%SIM%%/${n}.glb`); const o = g.scene, bb = new THREE.Box3().setFromObject(o), sz = bb.getSize(new THREE.Vector3()), c = bb.getCenter(new THREE.Vector3());
    const piv = new THREE.Group(); o.position.sub(c); piv.add(o); piv.scale.setScalar(1 / Math.max(sz.x, sz.y, sz.z)); piv.visible = false; sScene.add(piv); models[n] = piv; })); }
function draw3D(name, col, k) { for (const n in models) models[n].visible = n === name; const m = models[name]; m.rotation.set(0.32, 2.2 + k * 1.1, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace; sScene.background = new THREE.Color(col).convertLinearToSRGB().convertSRGBToLinear();
  sScene.background = new THREE.Color(col); sCam.position.set(0, 0.25, (TALL ? 4.6 : 2.9) - k * 0.35); sCam.lookAt(0, TALL ? -0.32 : 0, 0); renderer.render(sScene, sCam); renderer.outputColorSpace = THREE.LinearSRGBColorSpace; }

// ------------------------------------------------------------ the edit
const pad = (n) => String(n).padStart(4, "0");
const cache = new Map();
// decode() can stall for good on a headless page, which killed whole renders: never wait on it for long
const dec = (e) => Promise.race([e.decode().catch(() => {}), new Promise((r) => setTimeout(r, 1500))]);
function img(src) { if (!cache.has(src)) { const i = new Image(); i.src = src; cache.set(src, dec(i).then(() => i)); } return cache.get(src); }
async function setImg(el, src) { if (el.dataset.src !== src) { await img(src); el.src = src; el.dataset.src = src; await dec(el); } }
const cues = [...document.querySelectorAll(".t")];
const hide = (...ids) => ids.forEach((i) => { $(i).style.opacity = 0; });
const noise = (t, s) => Math.sin(t * 91.7 + s) * Math.cos(t * 61.3 + s * 2.1);
const WORD = "NC Recon", GLYPH = "01#/%X7+";

window.DURATION = DUR;
window.render = async (t0) => {
  const t = t0 + 1e-6, b = t / BEAT, fr = Math.round(t * 30 * 5) / 5;     // the nudge keeps cuts from falling between shots on float error
  hide("goes", "clip", "cov", "plate", "ring", "spec", "grain", "lab", "shade", "hud", "four", "proof", "tally", "ph0", "ph1");
  let glOn = false;
  // Helene
  if (b < 8) { const e = $("goes"), n = Math.min(100, Math.floor(t * 30)); await setImg(e, `%%GOES%%/${pad(n)}.jpg`); e.style.opacity = 1;
    e.style.transformOrigin = "50% 50%"; e.style.transform = `scale(${1.06 + 0.3 * ss(lin(b, 0, 8))}) rotate(${-2 * lin(b, 0, 8)}deg)`; $("shade").style.opacity = 1; }
  // the flash
  const s = SHOTS.find((x) => fr >= x.f && fr < x.f + x.n);
  if (s) { const k = (fr - s.f) / s.n; $("lab").style.opacity = s.label ? 1 : 0;
    if (s.kind === "photo") { const e = $("spec"), i = SHOTS.indexOf(s), a = $("ph1"), u = $("ph0"), rot = (n) => ((n * 37) % 7 - 3) * 0.8, off = (n) => ((n * 53) % 9 - 4) * 3;
      e.style.background = s.bg; e.style.opacity = 1; $("specimg").style.opacity = 0; $("grain").style.opacity = 0.5; $("lab").style.opacity = 0;
      await setImg(a, `%%V5%%/photos/${s.src}.jpg`); a.style.opacity = 1;
      const land = out5(clamp((fr - s.f) / 2));
      a.style.transform = `translate(${off(i)}px,${off(i + 3)}px) rotate(${rot(i)}deg) scale(${1.035 - 0.035 * land})`;
      if (i > 0) { await setImg(u, `%%V5%%/photos/${SHOTS[i - 1].src}.jpg`); u.style.opacity = 1; u.style.transform = `translate(${off(i - 1)}px,${off(i + 2)}px) rotate(${rot(i - 1)}deg)`; } }
    else if (s.kind === "clip") { const e = $("clip"), [c, off] = s.src.split(":"); await setImg(e, `%%CLIPS%%/${c}/${pad(+off + Math.floor(k * s.n * 2) + 1)}.jpg`); e.style.opacity = 1; e.style.transform = `scale(${1.12 - 0.06 * k})`; $("lab").style.opacity = 0; }
    else if (s.kind === "cover") { const e = $("cov"); await setImg(e, `%%V5%%/${s.src}.jpg`); e.style.opacity = 1; e.style.transform = `scale(${1.16 - 0.1 * out3(k)})`; }
    else if (s.kind === "3d") { draw3D(s.src, s.bg, k); glOn = true; $("grain").style.opacity = s.bg === "#17171A" ? 0 : 0.55; }
    else { const e = $("spec"), i = $("specimg"); await setImg(i, s.kind === "plate" ? `%%V5%%/plates_pd/${s.src}.jpg` : `%%V5%%/glyph/${s.src}.png`); e.style.background = s.bg; e.style.opacity = 1; i.style.transform = `translate(-50%,-50%) scale(${1.0 + 0.06 * k})`; $("grain").style.opacity = 0.55; }
    if (s.label) { $("labt").textContent = s.label; $("labn").textContent = "No. " + String(s.no).padStart(3, "0"); } }
  // the tally: slow at first, then running away, landing on the real total as the music drops
  if (b >= 8 && b < 20) { $("tally").style.opacity = 1; const q = Math.floor(fr) / 30 / BEAT; $("tn").textContent = Math.round(80000 * Math.pow(lin(q, 8, 19.9), 3.4)).toLocaleString("en-US"); }   // holds for a whole frame, so the shutter does not smear the digits
  // footage
  const c = FOOT.find((x) => b >= x[0] && b < x[1]);
  if (c) { const [nm, off] = c[2].split(":"), e = $("clip"), k = lin(t, B(c[0]), B(c[1])), f = +off + Math.floor((t - B(c[0])) * 30 * c[3]) + 1; await setImg(e, `%%CLIPS%%/${nm}/${pad(f)}.jpg`);
    e.style.opacity = 1; e.style.transform = `scale(${1.08 - 0.08 * ss(k)})`; $("shade").style.opacity = 1; }
  // plates and app
  const p = PLATES.find((x) => b >= x[0] && b < x[1]);
  if (p) { const e = $("plate"), app = p[2].includes("app2"), o = TALL ? p[4] : p[3], z = TALL ? o[1] : o[0], ox = TALL ? o[2] : o[1], oy = TALL ? o[3] : o[2], pw = $("pw");
    await setImg(e, p[2]); e.style.objectPosition = TALL ? `${o[0]}% 50%` : "50% 50%"; pw.style.height = TALL && app ? "1060px" : "100%";
    const mk = TALL && app ? "linear-gradient(to bottom,#000 86%,transparent 100%)" : "none"; pw.style.webkitMaskImage = mk; pw.style.maskImage = mk;
    const k = lin(t, B(p[0]), B(p[1])), r = $("ring"); e.style.opacity = 1; e.style.transformOrigin = `${ox}% ${oy}%`; e.style.transform = `scale(${z * (1.04 - 0.04 * ss(k))})`; $("shade").style.opacity = 1;
    r.style.opacity = (b >= 74 && b < 80) ? 1 : 0; r.style.transformOrigin = e.style.transformOrigin; r.style.transform = e.style.transform; }
  // terrain
  if (b >= 36 && b < 72) { drawTerrain(t); glOn = true; if (b >= 52) $("shade").style.opacity = 1; }
  $("gl").style.opacity = glOn ? 1 : 0;
  $("hud").style.opacity = (b >= 41 && b < 52) ? 1 : 0;
  // type rolls up out of a mask, then cuts on the beat
  cues.forEach((el) => { const a = +el.dataset.a * BEAT, z = +el.dataset.z * BEAT, on = t >= a && t < z; el.style.opacity = on ? 1 : 0;
    if (on && el.classList.contains("slam")) el.querySelector(".in").style.transform = `translateY(${(1 - out5(lin(t, a, a + 0.3))) * 104}%)`; });
  $("four").style.opacity = (b >= 32 && b < 36) ? 1 : 0;
  if (b >= 32 && b < 36) { document.querySelector("#four .p").style.transform = `scale(${1.1 - 0.1 * out5(lin(b, 32, 32.8))})`; }
  $("proof").style.opacity = (b >= 94 && b < 102) ? 1 : 0;
  if (b >= 94 && b < 102) { document.querySelector("#proof .p").style.transform = `scale(${1.1 - 0.1 * out5(lin(b, 94, 94.8))})`; }
  // the logo: the ring crosses the tiles, one is knocked out on the track's last hit
  const LB = 108, onL = b >= LB; $("logo").style.opacity = onL ? 1 : 0; $("end").style.opacity = onL ? 1 : 0;
  if (onL) { const f = Math.min(190, Math.floor(40 + (t - B(LB)) * 30)); await setImg($("logo"), `%%LOGODIR%%/${pad(f)}.jpg`);
    const y = f <= 40 ? 39 : f <= 60 ? 39 - 6 * (f - 40) / 20 : f <= 72 ? 33 : f <= 100 ? 33 - 13 * (f - 72) / 28 : 20, e0 = f < 120 ? 90 : 74, mk = `linear-gradient(to bottom, transparent ${y}%, #000 ${y + 5}%, #000 ${e0}%, transparent ${e0 + 6}%)`;
    $("logo").style.webkitMaskImage = mk; $("logo").style.maskImage = mk;
    const k = ss(lin(b, 116.8, 117.8)), pull = 1 - %%PULL%% * ss(lin(f, 100, 134)); $("logo").style.transform = `translateY(${-%%LIFT%% * k}px) scale(${pull * (1 - %%SHRINK%% * k)})`;
    const nw = Math.floor(lin(b, 117.5, 119.5) * (WORD.length + 1)); let w = WORD.slice(0, nw);          // the name resolves letter by letter
    if (nw > 0 && nw < WORD.length && b >= 117.5) w += GLYPH[Math.floor(t * 30) % GLYPH.length];
    $("word").textContent = w;
    const q = (sel, a, d = 0.5) => document.querySelector("#end " + sel).style.opacity = ss(lin(b, a, a + d));
    q(".s", 120); }
  // punches and shake on the hits
  let dx = 0, dy = 0, zoom = 1.015;
  for (const [hb, kind, amp] of HITS) { const dt = t - B(hb); if (dt < 0 || dt > 0.5 || kind === "paper") continue; const e = amp * Math.exp(-dt / 0.14);
    dx += noise(t, hb) * 10 * e; dy += noise(t, hb + 9) * 10 * e; zoom += 0.03 * e; }
  $("stage").style.transform = `translate(${dx}px,${dy}px) scale(${zoom})`;
  // flashes kept rare: three in the film
  const fl = [[B(40), 0.35]].map(([a, v]) => (t >= a && t < a + 0.067) ? v : 0); $("flash").style.opacity = Math.max(...fl);
};
window.READY = (async () => {
  await document.fonts.load('800 40px "Disp"');
  const [post, heat] = await Promise.all([texLoad("%%POST%%"), texLoad("%%HEAT%%")]); uniforms.uPost.value = post; uniforms.uHeat.value = heat;
  uniforms.uRoads.value = overlay((x, c) => { x.lineCap = "round"; const st = { blocked: ["#FF3B1F", 13, []], debris: ["#FFB020", 11, [16, 14]], bridge: ["#FFD166", 11, [5, 15]] }; for (const r of L.roads) { const s = st[r.s] || st.blocked; x.strokeStyle = s[0]; x.lineWidth = s[1]; x.setLineDash(s[2]); P(x, c, r.p); x.stroke(); } });
  uniforms.uSec.value = overlay((x, c) => { x.font = "700 44px Disp"; for (const s of L.sectors) { x.strokeStyle = "#F5F3EE"; x.lineWidth = 6; P(x, c, s.p); x.closePath(); x.stroke(); const a = s.p[3][0]*c.width + 16, b = s.p[3][1]*c.height + 56; x.fillStyle = "#F5F3EE"; x.fillRect(a - 8, b - 44, x.measureText(String(s.priority)).width + 16, 56); x.fillStyle = "#000"; x.fillText(String(s.priority), a, b); } });
  uniforms.uLz.value = overlay((x, c) => { for (const p of L.lz) { const a = p.p[0]*c.width, b = p.p[1]*c.height; x.strokeStyle = "#7CFFCB"; x.lineWidth = 6; x.beginPath(); x.arc(a, b, 20, 0, 7); x.stroke(); x.fillStyle = "#7CFFCB"; x.beginPath(); x.arc(a, b, 6, 0, 7); x.fill(); } });
  await loadModels(%%MODELS%%);
  return true;
})();
</script></body></html>
"""


def main() -> None:
    aspect = sys.argv[1] if len(sys.argv) > 1 else "16x9"
    W, H = SIZES[aspect]
    tall = H > W
    sz = dict(PAD=76 if tall else 96, BOT=600 if tall else 84, SLAM=106 if tall else 186, SMALL=84 if tall else 118, TINY=66 if tall else 118, FIT=86 if tall else 158, MID=84 if tall else 120, LOW=34 if tall else 30, TAGT=250 if tall else 66,
              LAB=30 if tall else 28, LABB=600 if tall else 56, SPW=940 if tall else 1500, SPH=1200 if tall else 960, HUDT=270 if tall else 84, HUDN=156 if tall else 136, HUDG=34 if tall else 22,
              PCT=380 if tall else 340, PG1=56 if tall else 36, PG2=36 if tall else 22, PA=52 if tall else 44, PMAX=920 if tall else 1240, LOGO=1200 if tall else 1920, LOGOH=600 if tall else 960,
              WT=950 if tall else 626, WORD=148 if tall else 142, ST=1132 if tall else 782, STAG=60 if tall else 50, PHX=64 if tall else 80, PHY=250 if tall else 165, PHW=952 if tall else 1110, PHH=640 if tall else 750, TX=76 if tall else 1330, TY=1180 if tall else 590, TN=150 if tall else 130, TK=38 if tall else 34, IY=950 if tall else 170, IW=928 if tall else 520, IF=54 if tall else 60, FB=480 if tall else 34, FINE=22 if tall else 18, FP=180 if tall else 96, RING=170 if tall else 110, RINGW=6 if tall else 4,
              RALIGN="left" if tall else "right", LIFT=300 if tall else 166, SHRINK=0.2 if tall else 0.5, PULL=0.0 if tall else 0.2)
    cam = [[36, 118, 5.5, 2.7, -0.9, 0.5], [40, 96, 7.5, 2.5, -0.5, 0.2], [46, 70, 15, 2.5, 0, 0], [52, 44, 27, 3.1, 0, 0], [60, 18, 40, 3.5, 0, 0],
           [63, 8, 52, 4.0, 0.4, 0.35], [66, 0, 56, 4.1, 0.5, 0.4], [69, -6, 58, 4.2, 0.3, 0.2], [72, -12, 56, 3.9, 0.1, 0]]
    swap = {"Type a FEMA<br>disaster<br>number*": "FEMA<br>disaster<br>number*", "Then someone<br>has to check<br>every one<b>.</b>": "Then someone has<br>to check every one<b>.</b>"} if tall else {}
    def cue(a, z, txt, c):
        txt = swap.get(txt, txt).replace("*", "<b>.</b>")
        body = f'<span class="in">{txt}</span>' if "slam" in c else txt
        return f'<div class="t {c}" data-a="{a}" data-z="{z}">{body}</div>'
    cuehtml = "".join(cue(*r) for r in CUES)
    with open(os.path.join(TERR, "dem.u16"), "rb") as fh:
        dem = base64.b64encode(fh.read()).decode()
    L = json.load(open(os.path.join(TERR, "layers.json"), encoding="utf-8"))
    L = {k: L[k] for k in ("bbox_utm", "dem", "roads", "sectors", "lz")}
    fp = json.load(open(os.path.join(A, "v4", "buildings.json"), encoding="utf-8"))
    shots, f, no = [], FLASH_B0 * 17, 0
    for n, kind, src, bg, label in FLASH:
        no += 3 if n > 6 else 7
        shots.append({"f": f, "n": n, "kind": kind, "src": src, "bg": bg, "label": label, "no": no})
        f += n
    shots += [{"f": f0, "n": n, "kind": kind, "src": src, "bg": bg, "label": label, "no": 0} for f0, n, kind, src, bg, label in KIT]
    models = sorted({s["src"] for s in shots if s["kind"] == "3d"})
    plates = [[a, b, rel(os.path.join(A, p)), w, t] for a, b, p, w, t in PLATES]
    subs = {"%%FONT%%": rel(os.path.join(A, "fonts", "archivo-latin-standard-normal.woff2")), "%%BEAT%%": repr(BEAT), "%%DUR%%": repr(END_B * BEAT), "%%FOOT%%": json.dumps(FOOT), "%%PLATES%%": json.dumps(plates),
            "%%SHOTS%%": json.dumps(shots), "%%HITS%%": json.dumps(HITS), "%%F0%%": str(FLASH_B0 * 17), "%%LAYERS%%": json.dumps(L, separators=(",", ":")), "%%BUILDINGS%%": json.dumps(fp, separators=(",", ":")),
            "%%DEM%%": json.dumps(dem), "%%CAM%%": json.dumps(cam), "%%CUEHTML%%": cuehtml, "%%MODELS%%": json.dumps(models), "%%SIM%%": rel(os.path.join(V5, "simready")), "%%GOES%%": rel(os.path.join(V5, "goes_c")),
            "%%V5%%": rel(V5), "%%PAPER%%": rel(os.path.join(V5, "paper.png")), "%%CLIPS%%": rel(os.path.join(A, "v4", "clips")), "%%LOGODIR%%": rel(os.path.join(A, "v4", "logo")), "%%POST%%": rel(os.path.join(TERR, "post.jpg")),
            "%%HEAT%%": rel(os.path.join(TERR, "heat.png")), "%%W%%": str(W), "%%H%%": str(H)}
    subs.update({f"%%{k}%%": str(v) for k, v in sz.items()})
    html = HTML
    for k, v in subs.items():
        html = html.replace(k, v)
    left = [p for p in html.split("%%")[1:-1:2] if len(p) < 12 and p.isupper()]
    assert not left, left
    out = os.path.join(BUILD, f"composition_v7_{aspect}.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    json.dump({"beat": BEAT, "end": END_B, "hits": HITS, "flash": [[s["f"], s["n"], s["kind"]] for s in shots if s["f"] < 20 * 17]}, open(os.path.join(BUILD, "cues_v7.json"), "w"))
    print("wrote", os.path.relpath(out, HERE), END_B * BEAT, "s,", len(shots), "flash shots,", len(models), "models")


if __name__ == "__main__":
    main()
