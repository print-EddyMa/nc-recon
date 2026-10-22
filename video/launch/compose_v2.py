"""Launch film v2 composition: `python3 video/launch/compose_v2.py`.

75 s at 112 bpm (every cut lands on a beat). Topographic-sheet look, as on the
site: paper and contour brown, hydro blue, the FEMA ramp; Barlow Condensed,
Overpass, Overpass Mono. Real material only:

  * the Swannanoa valley in 3D, rebuilt in three.js from the site's own baked
    assets (USGS 3DEP relief, NC OneMap before/after imagery, the smoothed
    damage density, published roads, USNG sectors and landing-zone candidates
    from site/assets/terrain/layers.json); contours are traced from the DEM;
  * the app itself (assets/app2: Respond, 3D orbit, stepper, Verify, offline);
  * Civil Air Patrol obliques, NC OneMap plates (assets from v1);
  * every number from a real output (see CREDITS.md).

Writes build/composition_v2.html. Render: `python3 video/launch/render.py --html composition_v2.html --out picture_v2.mp4`.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
A = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")
TERR = os.path.join(ROOT, "site", "assets", "terrain")

BPM = 112
B = 60 / BPM
DURATION = round(140 * B, 3)          # 75.0 s


def rel(p: str) -> str:
    return os.path.relpath(p, BUILD)


MARK = (
    '<g fill="none" stroke="currentColor" stroke-linecap="round">'
    '<line x1="32" y1="9" x2="32" y2="55" stroke-width="2.6"/>'
    '<line x1="9" y1="15" x2="55" y2="15" stroke-width="2.6"/>'
    '<line x1="6" y1="56" x2="58" y2="56" stroke-width="2.6"/></g>'
    '<g id="plumbL"><line x1="12" y1="15" x2="12" y2="39" stroke="currentColor" stroke-width="1.2"/>'
    '<path d="M12 38.5 l-3.6 3.4 3.6 6 3.6-6z" fill="var(--contour)"/></g>'
    '<g id="plumbR"><line x1="52" y1="15" x2="52" y2="39" stroke="currentColor" stroke-width="1.2"/>'
    '<path d="M52 38.5 l-3.6 3.4 3.6 6 3.6-6z" fill="var(--contour)"/></g>'
    '<circle cx="32" cy="9" r="2.4" fill="var(--contour)"/>'
)

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Groma launch film v2</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Overpass:wght@400;600;700&family=Overpass+Mono:wght@400;600&display=block">
<style>
:root { --paper:#0E1412; --sheet:#131A17; --paper2:#18211D; --rule:#26302C; --rule2:#3A4540;
  --ink:#E4E8E1; --ink2:#A9B2AC; --ink3:#7F8883; --contour:#C99662; --hydro:#6BA4D8; --signal:#EE6C35;
  --lz:#1F7A5A; --dep:#D6802E; --scour:#3478C4;
  --d0:#9E9E9E; --d1:#FECC5C; --d2:#FD8D3C; --d3:#F03B20; --d4:#BD0026;
  --display:"Barlow Condensed",sans-serif; --body:"Overpass",sans-serif; --mono:"Overpass Mono",monospace; }
* { box-sizing:border-box; margin:0; padding:0; }
html,body { width:1920px; height:1080px; overflow:hidden; background:var(--paper); color:var(--ink); font-family:var(--body); -webkit-font-smoothing:antialiased; }
.L { position:absolute; inset:0; overflow:hidden; opacity:0; }
.cover { position:absolute; left:50%; top:50%; width:1920px; height:1080px; object-fit:cover; }
.photo { filter: contrast(1.12) saturate(.88) brightness(.92); }
.vig { position:absolute; inset:0; background: radial-gradient(ellipse at 50% 46%, transparent 50%, rgba(5,8,7,.66) 100%); pointer-events:none; }
.scrim { position:absolute; inset:0; background: linear-gradient(to top, rgba(6,9,8,.86), rgba(6,9,8,0) 55%); }
.t { position:absolute; opacity:0; will-change:transform,opacity; }
.disp { font-family:var(--display); font-weight:700; line-height:.92; letter-spacing:-.005em; }
.mono { font-family:var(--mono); font-variant-numeric:tabular-nums; }
.label { font:600 22px var(--mono); letter-spacing:.14em; text-transform:uppercase; color:var(--contour); }
.maplab { font:600 26px var(--display); letter-spacing:.32em; text-transform:uppercase; color:var(--ink); text-shadow:0 0 18px rgba(0,0,0,.7); }
.kin { font-size:170px; }
.word { display:inline-block; opacity:0; }
#gl { position:absolute; inset:0; width:1920px; height:1080px; }
.hud { position:absolute; left:64px; bottom:56px; font:600 22px var(--mono); color:var(--ink); text-shadow:0 0 12px rgba(0,0,0,.8); opacity:0; }
.hud .bar { height:8px; border:2px solid var(--ink); border-top:0; margin-top:10px; }
.hud small { display:block; font-weight:400; color:var(--ink2); font-size:18px; margin-top:6px; }
.crop { position:absolute; overflow:hidden; }
.app { position:absolute; left:0; top:0; width:1920px; height:1080px; transform-origin:0 0; }
canvas.seq { position:absolute; left:0; top:0; transform-origin:0 0; }
.band { position:absolute; left:0; right:0; bottom:0; height:150px; background:rgba(10,14,12,.92); border-top:2px solid var(--contour); display:flex; align-items:center; gap:28px; padding:0 72px; }
.band .disp { font-size:64px; }
.stack { position:absolute; left:1060px; top:470px; width:520px; height:520px; transform-style:preserve-3d; }
.layer { position:absolute; inset:0; transform-style:preserve-3d; border:2px solid rgba(228,232,225,.75); background:var(--sheet); }
.layer img { width:100%; height:100%; object-fit:cover; display:block; }
.layer .lab { display:none; }
.leg { position:absolute; left:72px; top:420px; display:grid; gap:20px; }
.leg div { font:600 30px var(--mono); color:var(--ink); opacity:0; }
.leg b { color:var(--contour); margin-right:18px; }
.leg span { color:var(--ink2); font-weight:400; }
.layer .lab b { color:var(--contour); font-weight:600; margin-right:12px; }
.evid { display:grid; grid-template-columns:1fr; align-content:center; gap:22px; padding:48px; height:100%; font:600 30px var(--mono); }
.evid span { color:var(--ink2); font-weight:400; }
.call { display:flex; flex-direction:column; justify-content:center; padding:48px; height:100%; }
.call .disp { font-size:118px; color:var(--ink); }
.probbar { display:flex; height:28px; margin-top:26px; }
.card { position:absolute; inset:0; }
.big { font-size:300px; line-height:.86; }
.cav { font:400 25px var(--body); color:var(--ink2); max-width:1180px; line-height:1.4; }
.chips { display:flex; flex-wrap:wrap; gap:12px 14px; max-width:1500px; }
.chip { font:600 27px var(--mono); color:var(--ink); border:2px solid var(--rule2); padding:11px 16px; opacity:0; }
.chip.hl { font-size:34px; }
.chip.hl { border-color:var(--contour); color:var(--contour); }
.grain { position:absolute; inset:-20px; pointer-events:none; opacity:.14; mix-blend-mode:overlay; z-index:90;
  background-image: radial-gradient(rgba(255,255,255,.10) 1px, transparent 1.2px), radial-gradient(rgba(0,0,0,.22) 1px, transparent 1.2px);
  background-size:3px 3px,5px 5px; }
#flash { position:absolute; inset:0; background:var(--ink); opacity:0; z-index:95; pointer-events:none; }
#black { position:absolute; inset:0; background:#000; z-index:99; }
.mark { width:240px; height:240px; color:var(--ink); }
</style></head><body>
<svg width="0" height="0" style="position:absolute"><filter id="mb" x="-20%" y="0" width="140%" height="100%"><feGaussianBlur id="mbs" stdDeviation="0 0"/></filter></svg>

<!-- HOOK -->
<div class="L" id="h1"><img class="cover photo" id="h1i" src="%%CAP1%%"><div class="vig"></div>
  <div class="t maplab" id="h1l" style="left:72px;top:64px">Swannanoa, North Carolina · 28 Sep 2024</div></div>
<div class="L" id="h2"><img class="cover photo" id="h2i" src="%%CAP2%%"><div class="vig"></div><div class="scrim"></div>
  <div class="t disp kin" id="h2t" style="left:72px;bottom:96px"><span class="word" id="w1">Every building,</span><br><span class="word" id="w2" style="color:var(--contour)">after the disaster.</span></div></div>

<!-- 3D TERRAIN -->
<div class="L" id="g"><canvas id="gl" width="1920" height="1080"></canvas><div class="vig"></div>
  <div class="t maplab" id="gl1" style="left:72px;top:64px">Swannanoa valley · Buncombe County, NC</div>
  <div class="t mono" id="gl2" style="left:72px;top:110px;font-size:19px;color:var(--ink2)">USGS 3DEP relief ×1.8 · NC OneMap imagery</div>
  <div class="hud" id="hud"><span id="usng">17S LV 0000 0000</span><small id="hudsub">elevation</small><div class="bar" id="scalebar" style="width:120px"></div><small id="scalelab">1 km</small></div>
  <div class="t" id="whats" style="left:0;top:0;width:1500px;height:1080px;background:linear-gradient(to right, rgba(8,11,10,.8), rgba(8,11,10,0))"></div>
  <div class="t" id="what" style="left:72px;top:330px;max-width:1300px">
    <div class="disp" style="font-size:210px">Groma</div>
    <div class="disp" style="font-size:78px;margin-top:10px;font-weight:600">Building-by-building disaster damage assessment</div>
    <div class="mono" style="font-size:26px;margin-top:26px;color:var(--ink2)">Public imagery · lidar · field records · free and open source</div></div>
  <div class="t disp" id="glk1" style="right:72px;top:64px;font-size:64px;text-align:right">Damage density<br><span class="mono" style="font-size:22px;color:var(--ink2);font-weight:400">expected Major or Destroyed, smoothed 70 m</span></div>
  <div class="t disp" id="glk2" style="right:72px;top:64px;font-size:64px;text-align:right"><span id="glk2a">Before · Feb 2023</span></div>
  <div class="t disp" id="glk3" style="right:72px;top:64px;font-size:64px;text-align:right">Relief · 20 m contours</div>
  <div class="t" id="resp" style="right:72px;top:64px;text-align:right">
    <div class="disp" style="font-size:72px">Response plan</div>
    <div class="mono" id="r1" style="font-size:28px;margin-top:20px;opacity:0"><b style="color:var(--signal)">532</b> road segments likely blocked</div>
    <div class="mono" id="r2" style="font-size:28px;margin-top:12px;opacity:0"><b style="color:var(--hydro)">9</b> search sectors · 1 km USNG</div>
    <div class="mono" id="r3" style="font-size:28px;margin-top:12px;opacity:0"><b style="color:#5fd1a5">30</b> landing-zone candidates</div>
    <div class="mono" id="r4" style="font-size:24px;margin-top:20px;opacity:0;color:var(--ink2)">If debris also blocks roads: 74 buildings,<br>about 113 people cut off</div></div></div>

<!-- APP ORBIT (real 3D view) -->
<div class="L" id="orb"><canvas class="seq" id="orbc" width="1920" height="1080"></canvas><div class="vig"></div>
  <div class="band"><span class="label">The app</span><span class="disp">Every building at its inventory height, in 3D.</span></div></div>

<!-- ANATOMY -->
<div class="L" id="an" style="background:var(--paper);perspective:2400px">
  <div class="t" id="anh" style="left:72px;top:96px"><div class="label">Anatomy of a call</div><div class="disp" style="font-size:84px;margin-top:8px">One building, every piece<br>of evidence.</div>
    <div class="mono" style="font-size:22px;color:var(--ink2);margin-top:16px">17S LV 7253 4080 · Swannanoa · manufactured home</div></div>
  <div class="leg" id="leg"><div id="l7"><b>07</b>County search team <span>· Destroyed</span></div><div id="l6"><b>06</b>Groma's call <span>· Destroyed 76%</span></div><div id="l5"><b>05</b>Evidence <span>· four channels</span></div><div id="l4"><b>04</b>Lidar ground <span>· ring max 0.31 m</span></div><div id="l3"><b>03</b>Pixel change <span>· z +2.8</span></div><div id="l2"><b>02</b>After <span>· spring 2025</span></div><div id="l1"><b>01</b>Before <span>· Feb 2023</span></div></div>
  <div class="stack" id="stack">
    <div class="layer" id="a1"><img src="%%PRE%%"><div class="lab"><b>01</b>Before · Feb 2023</div></div>
    <div class="layer" id="a2"><img src="%%POST%%"><div class="lab"><b>02</b>After · spring 2025</div></div>
    <div class="layer" id="a3"><img src="%%CHG%%"><div class="lab"><b>03</b>Change · z +2.8</div></div>
    <div class="layer" id="a4" style="background:#0b100e"><img src="%%GRD%%" style="image-rendering:pixelated"><div class="lab"><b>04</b>Lidar ground · ring max 0.31 m</div></div>
    <div class="layer" id="a5"><div class="evid"><div>Imagery model <span>· Destroyed</span></div><div>Pixel change <span>· z +2.8</span></div><div>Blue tarp <span>· none</span></div><div>Flood depth <span>· no gauge on this reach</span></div></div><div class="lab"><b>05</b>Evidence</div></div>
    <div class="layer" id="a6"><div class="call"><div class="label">Groma's call</div><div class="disp">Destroyed 76%</div>
      <div class="probbar"><i style="flex:.0003;background:var(--d0)"></i><i style="flex:.0002;background:var(--d1)"></i><i style="flex:.0256;background:var(--d2)"></i><i style="flex:.2152;background:var(--d3)"></i><i style="flex:.7588;background:var(--d4)"></i></div>
      <div class="mono" style="font-size:22px;color:var(--ink2);margin-top:14px">Major 22% · Minor 3% · sent to people first</div></div><div class="lab"><b>06</b>Fused call</div></div>
    <div class="layer" id="a7"><div class="call"><div class="label">County search team</div><div class="disp" style="color:var(--contour)">Destroyed</div>
      <div class="mono" style="font-size:22px;color:var(--ink2);margin-top:14px">Buncombe County SARCOP field record</div></div><div class="lab"><b>07</b>On the ground</div></div>
  </div></div>

<!-- APP STILLS -->
<div class="L" id="rsp"><div class="crop" style="inset:0"><img class="app" id="rspi" src="%%RESPOND%%"></div>
  <div class="band"><span class="label">Respond</span><span class="disp">Lifelines, landing zones, a plan for TAK.</span></div></div>
<div class="L" id="ver" style="background:var(--paper)"><div class="crop" style="left:820px;top:0;width:1100px;height:1080px;border-left:2px solid var(--rule2)"><img class="app" id="veri" src="%%VERIFY%%"></div>
  <div class="t" id="vert" style="left:72px;top:300px;max-width:700px"><div class="label">Verify</div><div class="disp" style="font-size:118px;margin-top:10px">People check the hard calls.</div>
    <div class="mono" style="font-size:26px;color:var(--ink2);margin-top:22px">Blind to the model. A Civil Air Patrol photo from two days after the storm beside the imagery.</div></div></div>
<div class="L" id="stp" style="background:var(--paper)"><div class="crop" style="left:660px;top:40px;width:1200px;height:1000px;border:2px solid var(--rule2)"><canvas class="seq" id="stpc" width="840" height="700"></canvas></div>
  <div class="t" id="stpt" style="left:72px;top:300px;max-width:560px"><div class="label">Any FEMA disaster</div><div class="disp" style="font-size:112px;margin-top:10px">Type the number.</div>
    <div class="disp" id="stph" style="font-size:112px;color:var(--signal);opacity:0">It picks the hazard.</div></div></div>
<div class="L" id="wld"><div class="crop" style="inset:0"><img class="app" id="wldi" src="%%OVERVIEW%%"></div><div class="vig"></div>
  <div class="band"><span class="label">Wildfire · area level</span><span class="disp">Eaton fire, Altadena: ~1,417 expected at Major or Destroyed.</span></div></div>
<div class="L" id="off" style="background:var(--paper)"><div class="crop" style="inset:0"><img class="app" id="offi" src="%%OFF3D%%"></div><div class="vig"></div>
  <div class="t" id="offt" style="left:72px;bottom:72px;background:rgba(10,14,12,.92);padding:30px 40px;border-left:6px solid var(--signal)">
    <div class="label" style="color:var(--signal)">Network denied · served from a pack</div><div class="disp" style="font-size:96px;margin-top:8px">Offline packs <span style="color:var(--contour)">(beta)</span></div>
    <div class="mono" style="font-size:24px;color:var(--ink2);margin-top:12px">Imagery, basemap, calls and exports on one laptop. Addresses stay behind.</div></div></div>
<div class="L" id="exp" style="background:var(--paper)"><div style="position:absolute;left:72px;top:110px">
  <div class="label">Out the door</div><div class="disp" style="font-size:118px;margin-top:8px">The FEMA damage survey, filled in.</div>
  <div class="chips" id="cols" style="margin-top:40px">%%COLS%%</div>
  <div class="chips" id="fmts" style="margin-top:46px"><span class="chip hl">KML for TAK</span><span class="chip hl">GeoPackage</span><span class="chip hl">File Geodatabase</span><span class="chip hl">CSV in US National Grid</span><span class="chip hl">Survey123 sheet</span></div></div>
  <div class="crop" id="takc" style="right:72px;bottom:72px;width:860px;height:150px;border:3px solid var(--contour);opacity:0"><img class="app" src="%%RESPOND%%" style="transform:translate(-3020px,-420px) scale(2);"></div></div>

<!-- APPLICATIONS -->
<div class="L" id="ap1"><img class="cover photo" src="%%CAP3%%" id="ap1i"><div class="vig"></div><div class="scrim"></div>
  <div class="t" id="ap1t" style="left:72px;bottom:90px"><div class="label">Emergency management</div><div class="disp" style="font-size:128px;margin-top:8px">A damage count the day imagery arrives.</div></div></div>
<div class="L" id="ap2"><img class="cover" src="%%HOMEPOST%%" id="ap2i" style="filter:contrast(1.1) brightness(.85)"><div class="vig"></div><div class="scrim"></div>
  <div class="t" id="ap2t" style="left:72px;bottom:90px"><div class="label">Insurers and lenders</div><div class="disp" style="font-size:128px;margin-top:8px">Check a building before you pay on it.</div></div></div>
<div class="L" id="ap3"><img class="cover" src="%%ORBLAST%%" id="ap3i" style="filter:contrast(1.08) brightness(.82)"><div class="vig"></div><div class="scrim"></div>
  <div class="t" id="ap3t" style="left:72px;bottom:90px"><div class="label">National Guard</div><div class="disp" style="font-size:128px;margin-top:8px">One damage picture, on one laptop.</div></div></div>

<!-- PROOF -->
<div class="L" id="p1" style="background:var(--paper)"><div style="position:absolute;left:120px;top:190px">
  <div class="label">Measured against the field · Hurricane Helene</div>
  <div class="disp big" id="p1n" style="margin-top:20px">15 <span style="font-size:.4em;color:var(--ink3)">of</span> 19</div>
  <div class="disp" style="font-size:66px;margin-top:22px">severe calls agreed with county search teams</div>
  <div class="cav" style="margin-top:26px">Swannanoa homes. A tuning area compared with search-team field records, not an accuracy figure.</div></div></div>
<div class="L" id="p2" style="background:var(--paper)"><div style="position:absolute;left:120px;top:190px">
  <div class="label">Measured against the field · Eaton fire</div>
  <div class="disp big" id="p2n" style="margin-top:20px"><span id="p2v">0.0</span><span style="font-size:.5em">%</span></div>
  <div class="disp" style="font-size:66px;margin-top:22px">of the wildfire model's Major or Destroyed calls matched CAL FIRE inspections</div>
  <div class="cav" style="margin-top:26px">Altadena, 2,246 buildings, one held-out run of the standalone wildfire model. Not yet fused into the full pipeline.</div></div></div>

<!-- END -->
<div class="L" id="end" style="background:var(--paper)">
  <svg class="mark t" id="mark" viewBox="0 0 64 64" style="left:840px;top:200px">%%MARK%%</svg>
  <div class="t disp" id="ew" style="left:0;right:0;top:470px;text-align:center;font-size:150px;letter-spacing:.06em">Groma</div>
  <div class="t mono" id="e1" style="left:0;right:0;top:640px;text-align:center;font-size:30px;color:var(--contour);letter-spacing:.12em;text-transform:uppercase">Free and open source</div>
  <div class="t mono" id="e2" style="left:0;right:0;top:700px;text-align:center;font-size:34px">github.com/print-EddyMa/nc-recon</div>
  <div class="t" id="e3" style="left:0;right:0;top:790px;text-align:center;font:600 30px var(--body);color:var(--ink2)">Decision support. Verify on the ground.</div>
  <div class="t mono" id="e4" style="left:0;right:0;bottom:40px;text-align:center;font-size:16px;color:var(--ink3)">Imagery: Civil Air Patrol / FEMA, NC OneMap, USGS 3DEP, NOAA · Maps © OpenStreetMap contributors, CARTO, USGS The National Map · Not an official FEMA assessment</div></div>

<div class="grain" id="grain"></div><div id="flash"></div><div id="black"></div>

<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}</script>
<script type="module">
import * as THREE from "three";
const $ = id => document.getElementById(id);
const B = %%BEAT%%, DUR = %%DUR%%;
const cl = (x,a=0,b=1) => Math.max(a, Math.min(b, x));
const lin = (t,a,b) => cl((t-a)/(b-a));
const eo = x => 1 - Math.pow(1-x, 3), eo5 = x => 1 - Math.pow(1-x, 5);
const eio = x => x<.5 ? 4*x*x*x : 1 - Math.pow(-2*x+2,3)/2;
const at = b => b * B;                               // beat -> seconds
const win = (t,a,b,fi=.15,fo=.12) => Math.min(eo(lin(t,a,a+fi)), 1 - eio(lin(t,b-fo,b)));
function show(id, t, a, b, fi=.12, fo=.1) { const o = win(t,a,b,fi,fo); $(id).style.opacity = o; return o; }
function rise(id, t, a, b, fi=.45, dy=26, fo=.15) { const e=$(id); const p=eo5(lin(t,a,a+fi));
  e.style.opacity = Math.min(p, 1 - eio(lin(t,b-fo,b))); e.style.transform = `translateY(${(1-p)*dy}px)`; }
function kb(id, t, a, b, s0, s1, x0=0, y0=0, x1=0, y1=0) { const p=lin(t,a,b);
  $(id).style.transform = `translate(-50%,-50%) translate(${x0+(x1-x0)*p}px,${y0+(y1-y0)*p}px) scale(${s0+(s1-s0)*p})`; }
function cam(img, t, a, b, f, g, ease=eio) { const p=ease(lin(t,a,b)); const v=f.map((x,i)=>x+(g[i]-x)*p);
  img.style.transform = `translate(${-v[0]*v[2]}px,${-v[1]*v[2]}px) scale(${v[2]})`; }
// whip: directional blur + slide at a cut (out layer leaves left, in layer arrives from right)
const WHIPS = [%%WHIPS%%];
function whip(t) { let s = 0; for (const [c, outId, inId] of WHIPS) {
  const d = t - c; if (d > -0.11 && d < 0) { const k = (d+0.11)/0.11; $(outId).style.transform = `translateX(${-k*k*520}px)`; $(outId).style.filter = "url(#mb)"; s = Math.max(s, k*60); }
  else if (d >= 0 && d < 0.14) { const k = 1 - d/0.14; $(inId).style.transform = `translateX(${k*k*520}px)`; $(inId).style.filter = "url(#mb)"; s = Math.max(s, k*60); }
  else { if (d >= 0.14 && d < 0.5) { $(inId).style.transform = ""; $(inId).style.filter = ""; } if (d <= -0.11 && d > -0.5) { $(outId).style.filter = ""; } } }
  $("mbs").setAttribute("stdDeviation", `${s.toFixed(1)} 0`); }
const FLASHES = [%%FLASHES%%];
function flash(t) { let o = 0; for (const c of FLASHES) { const d = t - c; if (d >= 0 && d < 0.18) o = Math.max(o, .55*(1-d/0.18)); } $("flash").style.opacity = o; }
function punch(id, t, beats, s=0.045) { let k = 0; for (const b of beats) { const d = t - at(b); if (d >= 0 && d < 0.35) k = Math.max(k, 1 - d/0.35); } return 1 + s*eo(k); }

// ---------------- three.js terrain from the site's baked assets ----------------
const L = await (await fetch("%%LAYERS%%")).json();
const [X0, Y0, X1, Y1] = L.bbox_utm, W = (X1-X0)/1000, D = (Y1-Y0)/1000, EX = 1.8, dw = L.dem.w, dh = L.dem.h;
const zbuf = new Uint16Array(await (await fetch("%%DEM%%")).arrayBuffer());
const z = new Float32Array(zbuf.length); let zmin = 1e9, zmax = -1e9;
for (let i = 0; i < z.length; i++) { z[i] = zbuf[i] / 10; zmin = Math.min(zmin, z[i]); zmax = Math.max(zmax, z[i]); }
const H = m => (m - zmin) / 1000 * EX;
const zAt = (u, v) => z[Math.round(cl(v)* (dh-1)) * dw + Math.round(cl(u) * (dw-1))];
const img = src => new Promise((r, j) => { const i = new Image(); i.onload = () => r(i); i.onerror = j; i.src = src; });
const [post, pre, heat] = await Promise.all([img("%%TPOST%%"), img("%%TPRE%%"), img("%%THEAT%%")]);
await document.fonts.ready;
const TW = 2048, TH = 1422;
function mk() { const c = document.createElement("canvas"); c.width = TW; c.height = TH; return [c, c.getContext("2d")]; }
// relief: hillshade in topo-sheet tones
const [relief, rx] = mk(); { const sm = document.createElement("canvas"); sm.width = dw; sm.height = dh; const sx = sm.getContext("2d");
  const id = sx.createImageData(dw, dh); const az = Math.PI*1.75, al = Math.PI/4.5;
  for (let r = 0; r < dh; r++) for (let c = 0; c < dw; c++) { const i = r*dw+c;
    const gx = (z[r*dw+Math.min(dw-1,c+1)] - z[r*dw+Math.max(0,c-1)]) / (2*16.7), gy = (z[Math.min(dh-1,r+1)*dw+c] - z[Math.max(0,r-1)*dw+c]) / (2*16.7);
    const sl = Math.PI/2 - Math.atan(Math.hypot(gx, gy)*1.4), asp = Math.atan2(-gx, gy);
    const hs = cl(Math.sin(al)*Math.sin(sl) + Math.cos(al)*Math.cos(sl)*Math.cos(az - asp));
    const e = (z[i]-zmin)/(zmax-zmin); const base = [24+e*40, 30+e*36, 26+e*28];
    id.data[i*4] = base[0] + hs*120; id.data[i*4+1] = base[1] + hs*112; id.data[i*4+2] = base[2] + hs*96; id.data[i*4+3] = 255; }
  sx.putImageData(id, 0, 0); rx.imageSmoothingQuality = "high"; rx.drawImage(sm, 0, 0, TW, TH); }
// contours: marching squares every 20 m, index every 100 m
const [cont, cx2] = mk(); { const sx = TW/(dw-1), sy = TH/(dh-1);
  for (let lev = Math.ceil(zmin/20)*20; lev < zmax; lev += 20) { const idx = lev % 100 === 0;
    cx2.strokeStyle = idx ? "rgba(214,160,104,.95)" : "rgba(201,150,98,.62)"; cx2.lineWidth = idx ? 2.6 : 1.3; cx2.beginPath();
    for (let r = 0; r < dh-1; r++) for (let c = 0; c < dw-1; c++) {
      const a = z[r*dw+c], b = z[r*dw+c+1], d = z[(r+1)*dw+c], e = z[(r+1)*dw+c+1];
      const pts = []; const edge = (p, q, x0, y0, x1, y1) => { if ((p < lev) !== (q < lev)) { const k = (lev-p)/(q-p); pts.push([(x0+(x1-x0)*k)*sx, (y0+(y1-y0)*k)*sy]); } };
      edge(a, b, c, r, c+1, r); edge(b, e, c+1, r, c+1, r+1); edge(d, e, c, r+1, c+1, r+1); edge(a, d, c, r, c, r+1);
      if (pts.length >= 2) { cx2.moveTo(pts[0][0], pts[0][1]); cx2.lineTo(pts[1][0], pts[1][1]); }
      if (pts.length === 4) { cx2.moveTo(pts[2][0], pts[2][1]); cx2.lineTo(pts[3][0], pts[3][1]); } }
    cx2.stroke(); }
  cx2.strokeStyle = "rgba(107,164,216,.9)"; cx2.lineWidth = 3;
  for (const rv of L.rivers) { cx2.beginPath(); rv.p.forEach(([u, v], i) => i ? cx2.lineTo(u*TW, v*TH) : cx2.moveTo(u*TW, v*TH)); cx2.stroke(); } }
// response overlays
const [roads, rdx] = mk(); rdx.lineCap = "round";
for (const r of L.roads) { rdx.strokeStyle = r.s === "blocked" ? "#EE6C35" : r.s === "debris" ? "#FECC5C" : "#6BA4D8"; rdx.lineWidth = r.s === "bridge" ? 6 : 4.5;
  rdx.beginPath(); r.p.forEach(([u, v], i) => i ? rdx.lineTo(u*TW, v*TH) : rdx.moveTo(u*TW, v*TH)); rdx.stroke(); }
const [secs, scx] = mk(); scx.font = "700 46px 'Barlow Condensed'"; scx.textAlign = "center"; scx.textBaseline = "middle";
for (const s of L.sectors) { const p = s.p.map(([u, v]) => [u*TW, v*TH]); scx.strokeStyle = "#6BA4D8"; scx.lineWidth = 5; scx.fillStyle = "rgba(107,164,216,.12)";
  scx.beginPath(); p.forEach(([x, y], i) => i ? scx.lineTo(x, y) : scx.moveTo(x, y)); scx.closePath(); scx.fill(); scx.stroke();
  const mx = p.reduce((a, q) => a + q[0], 0)/p.length, my = p.reduce((a, q) => a + q[1], 0)/p.length;
  scx.fillStyle = "#0E1412"; scx.beginPath(); scx.arc(mx, my, 34, 0, 6.3); scx.fill(); scx.fillStyle = "#E4E8E1"; scx.fillText(String(s.priority), mx, my + 2); }
function drawLZ(ctx, n) { ctx.font = "700 30px 'Overpass'"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (let i = 0; i < Math.min(n, L.lz.length); i++) { const [u, v] = L.lz[i].p; const x = u*TW, y = v*TH;
    ctx.fillStyle = "#1F7A5A"; ctx.beginPath(); ctx.arc(x, y, 22, 0, 6.3); ctx.fill(); ctx.strokeStyle = "#E4E8E1"; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = "#FFFFFF"; ctx.fillText("H", x, y + 2); } }

const tex = document.createElement("canvas"); tex.width = TW; tex.height = TH; const tx = tex.getContext("2d");
const renderer = new THREE.WebGLRenderer({ canvas: $("gl"), antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1); renderer.setSize(1920, 1080, false);
const scene = new THREE.Scene(); const bg = new THREE.Color("#0B100E"); scene.background = bg; scene.fog = new THREE.Fog(bg, 10, 26);
const camera = new THREE.PerspectiveCamera(36, 1920/1080, 0.03, 80);
const geo = new THREE.PlaneGeometry(W, D, dw-1, dh-1); geo.rotateX(-Math.PI/2);
const pos = geo.attributes.position; for (let i = 0; i < pos.count; i++) pos.setY(i, H(z[i])); geo.computeVertexNormals();
const T = new THREE.CanvasTexture(tex); T.colorSpace = THREE.SRGBColorSpace; T.anisotropy = renderer.capabilities.getMaxAnisotropy();
scene.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: T, roughness: 1, metalness: 0 })));
{ // skirt
  const sk = new THREE.MeshLambertMaterial({ color: new THREE.Color("#7A5A3A"), side: THREE.DoubleSide });
  const edges = [[...Array(dw).keys()].map(c => c), [...Array(dw).keys()].map(c => (dh-1)*dw + c), [...Array(dh).keys()].map(r => r*dw), [...Array(dh).keys()].map(r => r*dw + dw-1)];
  for (const e of edges) { const v = []; for (const i of e) { const x = pos.getX(i), y = pos.getY(i), zz = pos.getZ(i); v.push(x, y, zz, x, -0.25, zz); }
    const ix = []; for (let k = 0; k < e.length-1; k++) { const a = k*2; ix.push(a, a+1, a+2, a+1, a+3, a+2); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3)); g.setIndex(ix); g.computeVertexNormals(); scene.add(new THREE.Mesh(g, sk)); } }
scene.add(new THREE.HemisphereLight(0xffffff, 0x2a2420, 1.25));
const sun = new THREE.DirectionalLight(0xfff2dc, 1.6); sun.position.set(-4, 6, -3); scene.add(sun);

const U = (u, v) => new THREE.Vector3((u-0.5)*W, H(zAt(u, v)) + 0.02, (v-0.5)*D);
const AOI = [(L.aoi_uv[0][0]+L.aoi_uv[1][0])/2, (L.aoi_uv[0][1]+L.aoi_uv[1][1])/2], AN = L.anatomy.uv;
let lastKey = "";
function paint(st) { const key = JSON.stringify(st); if (key === lastKey) return; lastKey = key;
  tx.globalAlpha = 1; tx.globalCompositeOperation = "source-over";
  if (st.relief >= 1) tx.drawImage(relief, 0, 0, TW, TH); else {
    tx.drawImage(pre, 0, 0, TW, TH);
    if (st.wipe > 0) { tx.save(); tx.beginPath(); tx.rect(0, 0, TW*st.wipe, TH); tx.clip(); tx.drawImage(post, 0, 0, TW, TH); tx.restore();
      if (st.wipe < 1) { tx.fillStyle = "#E4E8E1"; tx.fillRect(TW*st.wipe - 3, 0, 6, TH); } }
    if (st.relief > 0) { tx.globalAlpha = st.relief; tx.drawImage(relief, 0, 0, TW, TH); tx.globalAlpha = 1; } }
  if (st.heat > 0) { tx.globalAlpha = st.heat; tx.globalCompositeOperation = "screen"; tx.drawImage(heat, 0, 0, TW, TH); tx.drawImage(heat, 0, 0, TW, TH); tx.globalCompositeOperation = "source-over"; tx.globalAlpha = 1; }
  if (st.cont > 0) { tx.globalAlpha = st.cont; tx.drawImage(cont, 0, 0); tx.globalAlpha = 1; }
  if (st.roads > 0) { tx.globalAlpha = st.roads; tx.drawImage(roads, 0, 0); tx.globalAlpha = 1; }
  if (st.secs > 0) { tx.globalAlpha = st.secs; tx.drawImage(secs, 0, 0); tx.globalAlpha = 1; }
  if (st.lz > 0) drawLZ(tx, st.lz);
  T.needsUpdate = true; }
function pad(n, w) { let s = String(Math.max(0, Math.floor(n))); while (s.length < w) s = "0" + s; return s.slice(-w); }
function look(p, tg) { camera.position.copy(p); camera.lookAt(tg); renderer.render(scene, camera);
  const u = tg.x/W + 0.5, v = tg.z/D + 0.5, ux = X0 + u*(X1-X0), uy = Y1 - v*(Y1-Y0);
  $("usng").textContent = "17S LV " + pad((ux-300000)/10, 4) + " " + pad((uy-3900000)/10, 4);
  $("hudsub").textContent = "Elevation " + Math.round(zAt(u, v)) + " m · " + Math.round(zAt(u, v)*3.2808) + " ft";
  const d = p.distanceTo(tg), pxPerKm = 1080 / (2*Math.tan(THREE.MathUtils.degToRad(18))*d);
  const km = pxPerKm > 700 ? 0.25 : pxPerKm > 300 ? 0.5 : pxPerKm > 120 ? 1 : 2;
  $("scalebar").style.width = Math.round(km*pxPerKm) + "px"; $("scalelab").textContent = km < 1 ? (km*1000) + " m" : km + " km"; }
const lerpV = (a, b, k) => a.clone().lerp(b, k);
function orbit(tg, r, h, ang) { const a = THREE.MathUtils.degToRad(ang); return new THREE.Vector3(tg.x + r*Math.sin(a), tg.y + h, tg.z + r*Math.cos(a)); }
function terrain(t) {
  const c = U(AOI[0], AOI[1]), an = U(AN[0], AN[1]);
  if (t < at(16)) { const k = eio(lin(t, at(8), at(16))); paint({ wipe: 1, heat: .35*lin(t, at(10), at(15)), relief: 0, cont: 0 });
    look(lerpV(new THREE.Vector3(c.x, 10.5, c.z + 0.05), new THREE.Vector3(c.x - 0.9, 3.4, c.z + 3.0), k), c); return; }
  if (t < at(20)) { const k = eio(lin(t, at(16), at(20))); paint({ wipe: 1, heat: .95, relief: 0, cont: 0 });
    const tg = lerpV(new THREE.Vector3(c.x - 1.3, c.y, c.z), new THREE.Vector3(c.x + 0.5, c.y, c.z - 0.1), k);
    look(tg.clone().add(lerpV(new THREE.Vector3(-1.4, 1.0, 1.6), new THREE.Vector3(-1.0, 0.75, 1.25), k)), tg); return; }
  if (t < at(26)) { const k = lin(t, at(20), at(26)); const w = eio(lin(t, at(21), at(25)));
    paint({ wipe: Math.round(w*400)/400, heat: 0, relief: 0, cont: 0 }); $("glk2a").textContent = w > .5 ? "After · spring 2025" : "Before · Feb 2023";
    look(orbit(an, 1.7, 1.05, 205 + 50*eio(k)), an); return; }
  const k = eio(lin(t, at(26), at(30))); paint({ wipe: 1, heat: 0, relief: Math.round(eo(lin(t, at(26), at(27.5)))*20)/20, cont: Math.round(eo(lin(t, at(26.5), at(28)))*20)/20 });
  look(lerpV(new THREE.Vector3(c.x + 0.6, 2.0, c.z + 2.6), new THREE.Vector3(c.x - 0.3, 4.1, c.z + 3.6), k), c); }
function response(t) { const c = U(AOI[0], AOI[1]); const k = lin(t, at(48), at(56));
  const nlz = Math.floor(30 * lin(t, at(52), at(54.5)));
  paint({ wipe: 1, heat: 0, relief: .55, cont: .35, roads: Math.round(eo(lin(t, at(49), at(50.5)))*10)/10, secs: Math.round(eo(lin(t, at(50.5), at(52)))*10)/10, lz: nlz });
  look(orbit(c, 3.2, 3.6, 172 + 36*eio(k)), c); }

// ---------------- frame sequences ----------------
const orbitFrames = await Promise.all([...Array(%%ORBN%%).keys()].map(i => img("%%ORB%%/" + String(i).padStart(4, "0") + ".png")));
const stepFrames = await Promise.all(["stepper_0", "stepper_1", "stepper_2", "stepper_3", "stepper_4", "stepper_found"].map(n => img("%%APP2%%/" + n + ".png")));
function drawSeq(cv, im, sx, sy, sw, sh) { const g = cv.getContext("2d"); g.drawImage(im, sx, sy, sw, sh, 0, 0, cv.width, cv.height); }

window.DURATION = DUR;
window.render = function (t) {
  $("black").style.opacity = 1 - eo(lin(t, 0, 0.25)) + eio(lin(t, DUR - 0.9, DUR));
  $("grain").style.transform = `translate(${(Math.floor(t*24)*7)%20-10}px,${(Math.floor(t*24)*13)%20-10}px)`;
  // HOOK 0-8 beats
  show("h1", t, 0, at(4), .05, .02); kb("h1i", t, 0, at(4), 1.34 - .12*eo(lin(t, 0, .5)), 1.18, 0, 30, -40, 0);
  rise("h1l", t, .35, at(4), .4, 14, .05);
  show("h2", t, at(4), at(8), .02, .02); kb("h2i", t, at(4), at(8), 1.22, 1.12, 50, 0, -30, 10);
  { const w1 = eo5(lin(t, at(4.4), at(5.3))), w2 = eo5(lin(t, at(6), at(6.9)));
    $("h2t").style.opacity = 1; $("w1").style.opacity = w1; $("w1").style.transform = `translateY(${(1-w1)*40}px)`;
    $("w2").style.opacity = w2; $("w2").style.transform = `translateY(${(1-w2)*40}px)`; }
  // 3D terrain: beats 8-36
  const gOn = show("g", t, at(8), at(36), .02, .02) + (t >= at(48) && t < at(56.5) ? 1 : 0);
  if (t >= at(48) && t < at(56.5)) $("g").style.opacity = 1;
  if (t >= at(8) && t < at(30)) terrain(t); else if (t >= at(48) && t < at(56.5)) response(t);
  rise("what", t, at(8.6), at(15.6), .5, 30, .25); $("whats").style.opacity = win(t, at(8.4), at(15.8), .4, .3);
  rise("gl1", t, at(16.2), at(29.7), .35, 12, .1); rise("gl2", t, at(16.5), at(29.7), .35, 10, .1);
  $("hud").style.opacity = (t >= at(16) && t < at(30)) || (t >= at(48) && t < at(56.4)) ? 1 : 0;
  rise("glk1", t, at(16.2), at(19.8), .3, 14, .1); rise("glk2", t, at(20.2), at(25.8), .3, 14, .1); rise("glk3", t, at(26.3), at(29.8), .3, 14, .1);
  rise("resp", t, at(48.3), at(56.3), .35, 14, .12);
  rise("r1", t, at(49), at(56.3), .3, 10, .1); rise("r2", t, at(50.5), at(56.3), .3, 10, .1); rise("r3", t, at(52), at(56.3), .3, 10, .1); rise("r4", t, at(54), at(56.3), .3, 10, .1);
  // app orbit beats 30-36
  if (show("orb", t, at(30), at(36), .02, .02) > 0) { const n = orbitFrames.length; const i = Math.min(n - 1, Math.floor(lin(t, at(30), at(36)) * (n - 1)));
    drawSeq($("orbc"), orbitFrames[i], 0, 0, 1920, 1080); $("orbc").style.transform = `scale(${1.16 + .04*lin(t, at(30), at(36))}) translate(-100px,-40px)`; }
  // anatomy beats 36-48
  if (show("an", t, at(36), at(48), .02, .02) > 0) { rise("anh", t, at(36.05), at(47.7), .3, 16, .1);
    const sep = eio(lin(t, at(37), at(44))), rot = -38 + 14*lin(t, at(36), at(48));
    $("stack").style.transform = `rotateX(60deg) rotateZ(${rot}deg) scale(.8)`;
    for (let i = 1; i <= 7; i++) { const e = $("a" + i); const zz = (i - 1) * 84 * sep; const vis = i <= 2 ? 1 : eo(lin(t, at(36) + (i-1)*0.15, at(36) + (i-1)*0.15 + .25));
      e.style.transform = `translateZ(${zz}px)`; e.style.opacity = vis;
      const lg = $("l" + i); const lp = eo(lin(t, at(38) + (i-1)*0.5, at(38) + (i-1)*0.5 + .3)); lg.style.opacity = lp; lg.style.transform = `translateX(${(1-lp)*-18}px)`; } }
  // respond crop beats 56-60
  if (show("rsp", t, at(56), at(60), .02, .02) > 0) cam($("rspi"), t, at(56), at(60), [960, 120, 1.25], [1180, 150, 1.9], eo);
  // verify beats 60-68
  if (show("ver", t, at(60), at(68), .02, .02) > 0) { cam($("veri"), t, at(60.3), at(67.6), [376, 90, 1.5], [376, 428, 1.5]); rise("vert", t, at(60.3), at(67.8), .4, 18, .1); }
  // stepper beats 68-76
  if (show("stp", t, at(68), at(76), .02, .02) > 0) { const fr = t < at(69) ? 0 : t < at(69.5) ? 1 : t < at(70) ? 2 : t < at(70.5) ? 3 : t < at(71.5) ? 4 : 5;
    const zoom = fr === 5 ? eio(lin(t, at(71.5), at(72.5))) : 0;
    drawSeq($("stpc"), stepFrames[fr], 3010 + zoom*20, 120 + zoom*360, 840 - zoom*80, 700 - zoom*67); $("stpc").style.transform = "scale(1.4286)";
    rise("stpt", t, at(68.3), at(75.8), .35, 16, .1); rise("stph", t, at(71.6), at(75.8), .3, 14, .1); }
  // wildfire area level beats 76-80
  if (show("wld", t, at(76), at(80), .02, .02) > 0) cam($("wldi"), t, at(76), at(80), [0, 40, 1.0], [520, 300, 1.7], eo);
  // offline beats 80-88
  if (show("off", t, at(80), at(88), .02, .02) > 0) { const sw = t >= at(84); $("offi").src = sw ? "%%OFFMAP%%" : "%%OFF3D%%";
    cam($("offi"), t, sw ? at(84) : at(80), sw ? at(88) : at(84), sw ? [900, 0, 1.35] : [0, 0, 1.05], sw ? [1390, 0, 1.9] : [200, 60, 1.25], eo); rise("offt", t, at(80.4), at(87.8), .35, 16, .1); }
  // exports beats 88-96
  if (show("exp", t, at(88), at(96), .02, .02) > 0) { const cs = $("cols").children; for (let i = 0; i < cs.length; i++) cs[i].style.opacity = eo(lin(t, at(88.4) + i*0.06, at(88.4) + i*0.06 + .2));
    const fs = $("fmts").children; for (let i = 0; i < fs.length; i++) fs[i].style.opacity = eo(lin(t, at(91) + i*0.25, at(91) + i*0.25 + .2));
    $("takc").style.opacity = eo(lin(t, at(92.5), at(93.2))); }
  // applications beats 96-108
  for (const [id, a, b] of [["ap1", 96, 100], ["ap2", 100, 104], ["ap3", 104, 108]]) {
    if (show(id, t, at(a), at(b), .02, .02) > 0) { kb(id + "i", t, at(a), at(b), 1.18 * punch(id, t, [a]), 1.08, 0, 0, -30, 0); rise(id + "t", t, at(a) + .08, at(b), .35, 22, .05); } }
  // proof beats 108-124
  if (show("p1", t, at(108), at(116), .02, .12) > 0) { const p = eo5(lin(t, at(108.2), at(109.2))); $("p1n").style.opacity = p; $("p1n").style.transform = `translateY(${(1-p)*30}px)`; }
  if (show("p2", t, at(116), at(124), .02, .15) > 0) { const p = eo(lin(t, at(116.2), at(118.5))); $("p2v").textContent = (95.7*p).toFixed(1); $("p2n").style.opacity = eo(lin(t, at(116.2), at(116.8))); }
  // end beats 124-140
  if (show("end", t, at(124), DUR + 1, .02, .02) > 0) { rise("mark", t, at(124.3), DUR + 1, .5, 16, .01);
    const u = Math.max(0, t - at(124.6)); const a = 10*Math.exp(-u*1.3)*Math.cos(u*4.4);
    $("plumbL").setAttribute("transform", `rotate(${a} 12 15)`); $("plumbR").setAttribute("transform", `rotate(${a} 52 15)`);
    rise("ew", t, at(125.5), DUR + 1, .5, 20, .01); rise("e1", t, at(127.5), DUR + 1, .4, 10, .01); rise("e2", t, at(128.5), DUR + 1, .4, 10, .01);
    rise("e3", t, at(130), DUR + 1, .4, 10, .01); rise("e4", t, at(131), DUR + 1, .5, 6, .01); }
  whip(t); flash(t);
};
window.render(0);
window.READY = Promise.resolve(true);
</script>
<script>window.READY = new Promise(r => { const iv = setInterval(() => { if (window.render) { clearInterval(iv); r(true); } }, 50); });</script>
</body></html>"""


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    chips = json.load(open(os.path.join(ROOT, "site", "assets", "chips.json")))["e874056f"]
    ex = json.load(open(os.path.join(A, "export_rows.json")))
    cols = "".join(f'<span class="chip">{c}</span>' for c in ex["columns"])
    orb = os.path.join(A, "app2", "orbit")
    whips = [(4, "h1", "h2"), (36, "orb", "an"), (60, "rsp", "ver"), (76, "stp", "wld"), (88, "off", "exp"),
             (100, "ap1", "ap2"), (104, "ap2", "ap3")]
    flashes = [8, 16, 30, 48, 68, 80, 96, 108, 116, 124]
    sub = {
        "%%CAP1%%": rel(os.path.join(A, "cap_3200", "3e4341f10f55e585.jpg")),
        "%%CAP2%%": rel(os.path.join(A, "cap_3200", "b74798641e3c5744.jpg")),
        "%%CAP3%%": rel(os.path.join(A, "cap_3200", "c12cece8353397b5.jpg")),
        "%%HOMEPOST%%": rel(os.path.join(A, "plates", "swannanoa_home_post.jpg")),
        "%%PRE%%": chips["pre"], "%%POST%%": chips["post"],
        "%%CHG%%": rel(os.path.join(TERR, "anatomy_change.jpg")), "%%GRD%%": rel(os.path.join(TERR, "anatomy_ground.png")),
        "%%RESPOND%%": rel(os.path.join(A, "app2", "respond.png")), "%%VERIFY%%": rel(os.path.join(A, "app2", "verify.png")),
        "%%OVERVIEW%%": rel(os.path.join(A, "app2", "overview.png")), "%%OFF3D%%": rel(os.path.join(A, "app2", "offline_3d.png")),
        "%%OFFMAP%%": rel(os.path.join(A, "app2", "offline_map.png")), "%%APP2%%": rel(os.path.join(A, "app2")),
        "%%ORB%%": rel(orb), "%%ORBLAST%%": rel(os.path.join(orb, sorted(f for f in os.listdir(orb) if f.endswith(".png"))[-1])), "%%ORBN%%": str(len([f for f in os.listdir(orb) if f.endswith(".png")])),
        "%%LAYERS%%": rel(os.path.join(TERR, "layers.json")), "%%DEM%%": rel(os.path.join(TERR, "dem.u16")),
        "%%TPOST%%": rel(os.path.join(TERR, "post.jpg")), "%%TPRE%%": rel(os.path.join(TERR, "pre.jpg")),
        "%%THEAT%%": rel(os.path.join(TERR, "heat.png")),
        "%%COLS%%": cols, "%%MARK%%": MARK, "%%BEAT%%": repr(B), "%%DUR%%": repr(DURATION),
        "%%WHIPS%%": ", ".join(f'[{round(b * B, 4)}, "{o}", "{i}"]' for b, o, i in whips),
        "%%FLASHES%%": ", ".join(repr(round(b * B, 4)) for b in flashes),
    }
    html = HTML
    for k, v in sub.items():
        html = html.replace(k, v)
    assert "%%" not in html, [w for w in html.split() if "%%" in w][:5]
    assert "—" not in html
    with open(os.path.join(BUILD, "composition_v2.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote build/composition_v2.html", DURATION, "s")


if __name__ == "__main__":
    main()
