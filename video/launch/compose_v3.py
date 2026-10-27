"""Launch film v3, the story cut: `python3 video/launch/compose_v3.py`.

Script: SCRIPT_v3.md. Dated text cards over real material, one serif family
(Source Serif 4), fades and cuts only, long holds. No narrator, no labels,
no monospace, no grain, whips or HUD. Per-building damage appears only for
the one showcase home the public site already shows.

Writes build/composition_v3.html. Render:
  python3 video/launch/render.py --html composition_v3.html --out picture_v3.mp4
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
A = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")
TERR = os.path.join(ROOT, "site", "assets", "terrain")
FONT = os.path.join(ROOT, "web", "node_modules", "@fontsource-variable", "source-serif-4", "files",
                    "source-serif-4-latin-opsz-normal.woff2")
DURATION = 101.0
SHOWCASE = "e874056f"


def rel(p: str) -> str:
    return os.path.relpath(p, BUILD)


MARK = (
    '<g fill="none" stroke="currentColor" stroke-linecap="round">'
    '<line x1="32" y1="9" x2="32" y2="55" stroke-width="2.2"/>'
    '<line x1="9" y1="15" x2="55" y2="15" stroke-width="2.2"/>'
    '<line x1="6" y1="56" x2="58" y2="56" stroke-width="2.2"/></g>'
    '<g id="plumbL"><line x1="12" y1="15" x2="12" y2="39" stroke="currentColor" stroke-width="1"/>'
    '<path d="M12 38.5 l-3.2 3 3.2 5.4 3.2-5.4z" fill="currentColor"/></g>'
    '<g id="plumbR"><line x1="52" y1="15" x2="52" y2="39" stroke="currentColor" stroke-width="1"/>'
    '<path d="M52 38.5 l-3.2 3 3.2 5.4 3.2-5.4z" fill="currentColor"/></g>'
)

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Groma, the story cut</title>
<style>
@font-face { font-family:"Serif"; font-weight:200 900; font-optical-sizing:auto; src:url(%%FONT%%); }
:root { --ink:#F2F0EA; --dim:#B8B5AD; --bg:#0B0C0C; }
* { box-sizing:border-box; margin:0; padding:0; }
html,body { width:1920px; height:1080px; overflow:hidden; background:var(--bg); color:var(--ink); font-family:"Serif",serif; -webkit-font-smoothing:antialiased; }
.L { position:absolute; inset:0; overflow:hidden; opacity:0; }
.full { position:absolute; left:50%; top:50%; width:1920px; height:1080px; object-fit:cover; transform-origin:50% 50%; }
.grade { filter: contrast(1.05) saturate(.92); }
.low { position:absolute; left:0; right:0; bottom:0; height:46%; background:linear-gradient(to top, rgba(6,7,7,.72), rgba(6,7,7,0)); }
.card { position:absolute; left:120px; bottom:150px; max-width:1240px; font-size:54px; line-height:1.28; font-weight:400; letter-spacing:-.005em; opacity:0; text-wrap:balance; }
.card b { font-weight:600; }
.mid { bottom:auto; top:50%; transform:translateY(-50%); left:160px; max-width:1300px; font-size:58px; }
.src { position:absolute; left:120px; bottom:84px; font-size:23px; color:var(--dim); opacity:0; }
.mid + .src, .src.mid2 { left:160px; bottom:auto; top:calc(50% + 140px); }
.plate { position:absolute; inset:0; }
.plate img { position:absolute; inset:0; width:1920px; height:1080px; }
svg.fp { position:absolute; inset:0; width:1920px; height:1080px; }
.chip { position:absolute; top:190px; width:460px; height:460px; object-fit:cover; }
.chipcap { position:absolute; top:668px; font-size:24px; color:var(--dim); }
.app { position:absolute; left:0; top:0; width:1920px; height:1080px; transform-origin:0 0; }
.crop { position:absolute; overflow:hidden; }
#gl { position:absolute; inset:0; width:1920px; height:1080px; }
.mark { position:absolute; left:50%; top:330px; width:180px; height:180px; transform:translateX(-50%); color:var(--ink); opacity:0; }
#black { position:absolute; inset:0; background:#000; z-index:99; }
</style></head><body>

<!-- 1-2: the storm, the photos -->
<div class="L" id="p1"><img class="full grade" id="p1i" src="%%CAP1%%"><div class="low"></div></div>
<div class="L" id="p2"><img class="full grade" id="p2i" src="%%CAP2%%"><div class="low"></div></div>
<div class="L" id="p3"><img class="full grade" id="p3i" src="%%CAP3%%"><div class="low"></div></div>
<div class="L" id="p4"><img class="full grade" id="p4i" src="%%CAP4%%"><div class="low"></div></div>

<!-- 5-6: the park -->
<div class="L" id="park"><div class="plate" id="parkp">
  <img src="%%PRE%%"><img id="parkpost" src="%%POST%%" style="opacity:0">
  <svg class="fp" viewBox="0 0 1920 1080"><polygon id="show" points="%%SHOW%%" fill="none" stroke="#F2F0EA" stroke-width="4" stroke-dasharray="4000" stroke-dashoffset="4000"/></svg></div>
  <div class="low"></div></div>

<!-- 7: one record -->
<div class="L" id="rec" style="background:var(--bg)">
  <img class="chip" src="%%CPRE%%" style="left:120px"><img class="chip" src="%%CPOST%%" style="left:600px">
  <div class="chipcap" style="left:120px">February 2023</div><div class="chipcap" style="left:600px">Spring 2025</div>
  <div style="position:absolute;left:1180px;top:250px">
    <div style="font-size:30px;color:var(--dim)">17S LV 7253 4080, Swannanoa</div>
    <div style="font-size:120px;font-weight:500;line-height:1;margin-top:28px">Destroyed</div>
    <div style="font-size:40px;color:var(--dim);margin-top:18px">76% likely · Major 22% · Minor 3%</div>
    <div style="display:flex;height:10px;width:560px;margin-top:34px"><i style="flex:.03;background:#FD8D3C"></i><i style="flex:.22;background:#F03B20"></i><i style="flex:.76;background:#BD0026"></i></div></div></div>

<!-- 8-9: the software -->
<div class="L" id="app"><div class="crop" style="inset:0"><img class="app" id="appi" src="%%AREA%%"></div></div>
<div class="L" id="ver" style="background:var(--bg)"><div class="crop" style="left:860px;top:0;width:1060px;height:1080px"><img class="app" id="veri" src="%%VERIFY%%"></div></div>

<!-- 11: the valley -->
<div class="L" id="val"><canvas id="gl" width="1920" height="1080"></canvas><div class="low"></div></div>

<!-- 12: end -->
<div class="L" id="end" style="background:var(--bg)">
  <svg class="mark" id="mark" viewBox="0 0 64 64">%%MARK%%</svg>
  <div id="ew" style="position:absolute;left:0;right:0;top:560px;text-align:center;font-size:96px;font-weight:500;letter-spacing:.02em;opacity:0">Groma</div>
  <div id="e2" style="position:absolute;left:0;right:0;top:700px;text-align:center;font-size:32px;opacity:0">github.com/print-EddyMa/nc-recon</div>
  <div id="e3" style="position:absolute;left:0;right:0;top:760px;text-align:center;font-size:28px;color:var(--dim);opacity:0">Decision support. Verify on the ground.</div>
  <div id="e4" style="position:absolute;left:0;right:0;bottom:44px;text-align:center;font-size:18px;color:#7d7a73;opacity:0">Photos: Civil Air Patrol / FEMA. Imagery: NC OneMap. Elevation: USGS 3DEP. Map: OpenStreetMap contributors, CARTO. Not an official FEMA assessment.</div></div>

<!-- cards (one idea each) -->
<div class="card mid" id="c1"><b>September 27, 2024.</b><br>Hurricane Helene floods the Swannanoa valley<br>in western North Carolina.</div>
<div class="card" id="c2">Two days later, Civil Air Patrol crews<br>photographed what was left.</div>
<div class="src" id="s2">Civil Air Patrol · September 28 and 29, 2024</div>
<div class="card" id="c3">On the ground, crews and search teams<br>went house to house.</div>
<div class="card" id="c4">By early October, more than 100 teams<br>had logged 80,000 damage assessments.</div>
<div class="src" id="s4">Source: DHS Science and Technology, October 7, 2024</div>
<div class="card mid" id="c5">After Helene and Milton, 4% of FEMA's<br>incident workforce was available to deploy.</div>
<div class="src mid2" id="s5">Source: U.S. Government Accountability Office, GAO-25-108598</div>
<div class="src" id="s6a">NC OneMap · February 2023</div>
<div class="src" id="s6b">NC OneMap · spring 2025</div>
<div class="card" id="c6">Every building still needed a damage call,<br>one at a time.</div>
<div class="card" id="c7">We built Groma after the storm,<br>from that same public imagery.</div>
<div class="card" id="c8" style="bottom:120px">It reads every building it can see:<br>a damage level, and how sure it is.</div>
<div class="card" id="c9" style="bottom:110px;background:rgba(8,9,9,.86);padding:26px 34px;left:90px">893 buildings in 88 seconds, on a laptop.</div>
<div class="card mid" id="c10" style="max-width:640px;font-size:54px">The calls it is least sure of go to people first, who judge them blind.</div>
<div class="card mid" id="c11" style="max-width:1460px">After the Eaton fire, CAL FIRE inspectors checked 2,246 buildings Groma had assessed. When Groma called one destroyed or badly damaged, they agreed <b>96% of the time.</b></div>
<div class="src mid2" id="s11" style="top:calc(50% + 190px)">Eaton fire, Los Angeles County, 2025: one pre-registered held-out test of Groma's wildfire model (95.7%). Flood accuracy is still being validated.</div>
<div class="card" id="c12">Groma is free and open source,<br>for emergency managers, insurers and lenders,<br>and the National Guard.</div>
<div id="black"></div>

<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}</script>
<script type="module">
import * as THREE from "three";
const $ = id => document.getElementById(id);
const DUR = %%DUR%%;
const cl = (x,a=0,b=1) => Math.max(a, Math.min(b, x));
const lin = (t,a,b) => cl((t-a)/(b-a));
const ss = x => x*x*(3-2*x);
function win(t, a, b, f=.6) { return Math.min(ss(lin(t, a, a+f)), 1 - ss(lin(t, b-f, b))); }
function op(id, t, a, b, f=.6) { const o = win(t, a, b, f); $(id).style.opacity = o; return o; }
function drift(id, t, a, b, s0, s1, x0=0, x1=0) { const p = lin(t, a, b);
  $(id).style.transform = `translate(-50%,-50%) translate(${x0+(x1-x0)*p}px,0) scale(${s0+(s1-s0)*p})`; }
function cam(img, t, a, b, f, g) { const p = ss(lin(t, a, b)); const v = f.map((x,i)=>x+(g[i]-x)*p);
  img.style.transform = `translate(${-v[0]*v[2]}px,${-v[1]*v[2]}px) scale(${v[2]})`; }

// the valley: USGS 3DEP + NC OneMap, locked off, a slow push
const L = await (await fetch("%%LAYERS%%")).json();
const [X0, Y0, X1, Y1] = L.bbox_utm, W = (X1-X0)/1000, D = (Y1-Y0)/1000, EX = 1.6, dw = L.dem.w, dh = L.dem.h;
const zb = new Uint16Array(await (await fetch("%%DEM%%")).arrayBuffer());
const z = new Float32Array(zb.length); let zmin = 1e9; for (let i = 0; i < z.length; i++) { z[i] = zb[i]/10; zmin = Math.min(zmin, z[i]); }
const post = await new Promise((r, j) => { const i = new Image(); i.onload = () => r(i); i.onerror = j; i.src = "%%TPOST%%"; });
const renderer = new THREE.WebGLRenderer({ canvas: $("gl"), antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1); renderer.setSize(1920, 1080, false);
const scene = new THREE.Scene(); const bg = new THREE.Color("#0B0C0C"); scene.background = bg; scene.fog = new THREE.Fog(bg, 7, 15);
const camera = new THREE.PerspectiveCamera(32, 1920/1080, 0.03, 60);
const geo = new THREE.PlaneGeometry(W, D, dw-1, dh-1); geo.rotateX(-Math.PI/2);
const pos = geo.attributes.position; for (let i = 0; i < pos.count; i++) pos.setY(i, (z[i]-zmin)/1000*EX); geo.computeVertexNormals();
const tx = new THREE.Texture(post); tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = renderer.capabilities.getMaxAnisotropy(); tx.needsUpdate = true;
scene.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: tx, roughness: 1, metalness: 0 })));
scene.add(new THREE.HemisphereLight(0xffffff, 0x2a2622, 1.35));
const sun = new THREE.DirectionalLight(0xfff0dc, 1.2); sun.position.set(-5, 4, -2); scene.add(sun);
const aoi = [(L.aoi_uv[0][0]+L.aoi_uv[1][0])/2, (L.aoi_uv[0][1]+L.aoi_uv[1][1])/2];
const T = new THREE.Vector3((aoi[0]-0.5)*W, 0.25, (aoi[1]-0.5)*D);
function valley(t) { const p = lin(t, 86, 94.5);
  camera.position.set(T.x - 2.6 + 0.35*p, 1.55 - 0.08*p, T.z + 3.4 - 0.45*p); camera.lookAt(T); renderer.render(scene, camera); }

window.DURATION = DUR;
window.render = function (t) {
  $("black").style.opacity = 1 - ss(lin(t, 0, 0.8)) + ss(lin(t, DUR - 1.2, DUR));
  // 1-2 photographs
  op("p1", t, 4.6, 10.6, 1.4); drift("p1i", t, 4.6, 10.6, 1.12, 1.08, 20, -20);
  op("p2", t, 10.1, 14.1, .5);  drift("p2i", t, 10.1, 14.1, 1.06, 1.10);
  op("p3", t, 13.6, 17.4, .5);  drift("p3i", t, 13.6, 17.4, 1.10, 1.06, -20, 10);
  op("p4", t, 16.9, 27.4, .6);  drift("p4i", t, 16.9, 27.4, 1.04, 1.09);
  op("c1", t, 0.7, 5.6, .7);
  op("c2", t, 7.4, 12.9); op("s2", t, 7.6, 16.8);
  op("c3", t, 17.6, 21.9); op("c4", t, 22.3, 26.8); op("s4", t, 22.5, 26.8);
  op("c5", t, 27.8, 32.7); op("s5", t, 28.4, 32.7);
  // 5-6 the park: hold, dissolve, then the one home
  op("park", t, 33.2, 52.4, .9); $("parkp").style.transform = `scale(${1.0 + 0.035*lin(t, 33.2, 52.4)})`;
  $("parkpost").style.opacity = ss(lin(t, 38.4, 40.4));
  op("s6a", t, 33.8, 39.0, .5); op("s6b", t, 40.2, 51.8, .5);
  op("c6", t, 41.0, 45.2); op("c7", t, 46.0, 51.9);
  $("show").setAttribute("stroke-dashoffset", String(4000 * (1 - ss(lin(t, 45.4, 46.8)))));
  // 7 one record
  op("rec", t, 52.2, 60.4, .7); op("c8", t, 54.0, 59.9);
  // 8 the app
  if (op("app", t, 60.2, 66.4, .5) > 0) cam($("appi"), t, 60.2, 66.4, [0, 0, 1.0], [380, 90, 1.25]);
  op("c9", t, 61.0, 66.0);
  // 9 verify
  if (op("ver", t, 66.2, 74.4, .5) > 0) cam($("veri"), t, 66.4, 74.2, [376, 90, 1.5], [376, 428, 1.5]);
  op("c10", t, 66.8, 73.9);
  // 10 proof
  op("c11", t, 74.8, 85.4, .8); op("s11", t, 76.4, 85.4, .8);
  // 11 the valley
  if (op("val", t, 85.8, 94.6, 1.0) > 0) valley(t);
  op("c12", t, 87.0, 93.9, .8);
  // 12 the mark
  if (op("end", t, 94.4, DUR + 1, .8) > 0) {
    $("mark").style.opacity = ss(lin(t, 94.6, 95.6));
    const u = Math.max(0, t - 94.8), a = 7*Math.exp(-u*1.1)*Math.cos(u*4.0);
    $("plumbL").setAttribute("transform", `rotate(${a} 12 15)`); $("plumbR").setAttribute("transform", `rotate(${a} 52 15)`);
    $("ew").style.opacity = ss(lin(t, 95.6, 96.6)); $("e2").style.opacity = ss(lin(t, 96.6, 97.4));
    $("e3").style.opacity = ss(lin(t, 97.2, 98.0)); $("e4").style.opacity = ss(lin(t, 97.6, 98.4)); }
};
window.render(0);
window.READY = Promise.resolve(true);
</script>
<script>window.READY = new Promise(r => { const iv = setInterval(() => { if (window.render) { clearInterval(iv); r(true); } }, 50); });</script>
</body></html>"""


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    chips = json.load(open(os.path.join(ROOT, "site", "assets", "chips.json")))[SHOWCASE]
    home = json.load(open(os.path.join(A, "overlays", "swannanoa_home.json")))
    show = next(r for r in home if r["id"] == SHOWCASE)
    sub = {
        "%%FONT%%": rel(FONT),
        "%%CAP1%%": rel(os.path.join(A, "cap_3200", "3e4341f10f55e585.jpg")),
        "%%CAP2%%": rel(os.path.join(A, "cap_3200", "b74798641e3c5744.jpg")),
        "%%CAP3%%": rel(os.path.join(A, "cap_3200", "c12cece8353397b5.jpg")),
        "%%CAP4%%": rel(os.path.join(A, "cap_3200", "0d55dc25ac623808.jpg")),
        "%%PRE%%": rel(os.path.join(A, "plates", "swannanoa_home_pre.jpg")),
        "%%POST%%": rel(os.path.join(A, "plates", "swannanoa_home_post.jpg")),
        "%%SHOW%%": " ".join(f"{x},{y}" for x, y in show["pts"]),
        "%%CPRE%%": chips["pre"], "%%CPOST%%": chips["post"],
        "%%AREA%%": rel(os.path.join(A, "app2", "area.png")),
        "%%VERIFY%%": rel(os.path.join(A, "app2", "verify.png")),
        "%%LAYERS%%": rel(os.path.join(TERR, "layers.json")), "%%DEM%%": rel(os.path.join(TERR, "dem.u16")),
        "%%TPOST%%": rel(os.path.join(TERR, "post.jpg")),
        "%%MARK%%": MARK, "%%DUR%%": repr(DURATION),
    }
    html = HTML
    for k, v in sub.items():
        html = html.replace(k, v)
    assert "%%" not in html
    assert "—" not in html
    with open(os.path.join(BUILD, "composition_v3.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote build/composition_v3.html", DURATION, "s")


if __name__ == "__main__":
    main()
