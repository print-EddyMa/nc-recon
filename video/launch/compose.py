"""Write the launch film composition: `python video/launch/compose.py`.

One HTML page, 1920x1080, with a deterministic `window.render(t)` that sets
every layer for time t (seconds). `render.py` steps it frame by frame in
headless Chrome. All picture is real: Civil Air Patrol frames, NC OneMap
before/after plates, the Swannanoa assessment's own footprints and levels,
the 2025 lidar change, the app itself, and the product's own numbers.

Writes build/composition.html (git-ignored with the rest of the media).
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
A = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")
FONTS = os.path.join(ROOT, "web", "node_modules")

DURATION = 72.0
# Shot list (seconds). Every on-screen figure is read from a real output file.
CAP = {"open": "3e4341f10f55e585", "debris": "b74798641e3c5744", "river": "c12cece8353397b5"}
LEVEL_COLOUR = {"no_damage": "#9E9E9E", "affected": "#FECC5C", "minor": "#FD8D3C", "major": "#F03B20",
                "destroyed": "#BD0026", None: "#5d6b70"}
MARK = (
    '<g fill="none" stroke="currentColor" stroke-linecap="round">'
    '<line x1="32" y1="9" x2="32" y2="55" stroke-width="2.6"/>'
    '<line x1="9" y1="15" x2="55" y2="15" stroke-width="2.6"/>'
    '<line x1="6" y1="56" x2="58" y2="56" stroke-width="2.6"/></g>'
    '<g id="plumbL"><line x1="12" y1="15" x2="12" y2="39" stroke="currentColor" stroke-width="1.2"/>'
    '<path d="M12 38.5 l-3.6 3.4 3.6 6 3.6-6z" fill="var(--bronze)"/></g>'
    '<g id="plumbR"><line x1="52" y1="15" x2="52" y2="39" stroke="currentColor" stroke-width="1.2"/>'
    '<path d="M52 38.5 l-3.6 3.4 3.6 6 3.6-6z" fill="var(--bronze)"/></g>'
    '<circle cx="32" cy="9" r="2.4" fill="var(--bronze)"/>'
)


def rel(p: str) -> str:
    return os.path.relpath(p, BUILD)


def polys(name: str) -> str:
    rows = json.load(open(os.path.join(A, "overlays", f"{name}.json")))
    out = []
    for r in rows:
        c = LEVEL_COLOUR.get(r["level"], LEVEL_COLOUR[None])
        pts = " ".join(f"{x},{y}" for x, y in r["pts"])
        cx = sum(x for x, _ in r["pts"]) / len(r["pts"])
        out.append(f'<polygon class="fp" data-x="{cx:.0f}" points="{pts}" style="--c:{c}"/>')
    return "".join(out)


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    ex = json.load(open(os.path.join(A, "export_rows.json")))
    counts = ex["counts"]
    cols = ex["columns"]
    rows = ex["rows"]
    app = {k: os.path.join(A, "app", f"{k}.png") for k in ("overview", "area", "queue", "verify")}
    have_app = all(os.path.exists(p) for p in app.values())
    table_head = "".join(f"<th>{c}</th>" for c in ["incident_id_number", "county", "street_address",
                                                    "level_of_damage_assessed", "ncr_usng_10m", "ncr_probability"])
    table_rows = "".join("<tr>" + "".join(f"<td>{r[c]}</td>" for c in ["incident_id_number", "county", "street_address",
                                                                       "level_of_damage_assessed", "ncr_usng_10m",
                                                                       "ncr_probability"]) + "</tr>" for r in rows)
    col_list = "".join(f'<span class="col">{c}</span>' for c in cols)
    legend = "".join(f'<span><i style="background:{LEVEL_COLOUR[k]}"></i>{lab} <b>{counts.get(k, 0)}</b></span>'
                     for k, lab in [("no_damage", "No damage"), ("affected", "Affected"), ("minor", "Minor"),
                                    ("major", "Major"), ("destroyed", "Destroyed")])

    def app_img(k: str, cls: str = "") -> str:
        if have_app:
            return f'<img class="app {cls}" src="{rel(app[k])}">'
        return f'<div class="app ph {cls}">app capture: {k}</div>'

    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Groma launch film</title>
<style>
@font-face {{ font-family: "Marcellus"; src: url({rel(os.path.join(FONTS, "@fontsource/marcellus/files/marcellus-latin-400-normal.woff2"))}); }}
@font-face {{ font-family: "Public Sans"; font-weight: 100 900; src: url({rel(os.path.join(FONTS, "@fontsource-variable/public-sans/files/public-sans-latin-wght-normal.woff2"))}); }}
@font-face {{ font-family: "Plex Mono"; font-weight: 400; src: url({rel(os.path.join(FONTS, "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2"))}); }}
@font-face {{ font-family: "Plex Mono"; font-weight: 500; src: url({rel(os.path.join(FONTS, "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2"))}); }}
:root {{ --bg:#0F1315; --ink:#ECEAE3; --dim:#A9AEA8; --faint:#737A76; --verdigris:#63B59C; --bronze:#C9954B; --line:#2A3235; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html,body {{ width:1920px; height:1080px; overflow:hidden; background:var(--bg); color:var(--ink); }}
body {{ font-family:"Public Sans",sans-serif; -webkit-font-smoothing:antialiased; }}
.layer {{ position:absolute; inset:0; overflow:hidden; opacity:0; }}
.cover {{ position:absolute; left:50%; top:50%; width:1920px; height:1080px; object-fit:cover; transform-origin:50% 50%; }}
.photo {{ filter: contrast(1.06) saturate(.9) brightness(.94); }}
.vig {{ position:absolute; inset:0; background: radial-gradient(ellipse at 50% 46%, transparent 52%, rgba(6,9,10,.62) 100%); }}
.scrim-b {{ position:absolute; left:0; right:0; bottom:0; height:46%; background: linear-gradient(to top, rgba(8,11,12,.82), rgba(8,11,12,0)); }}
.scrim-l {{ position:absolute; top:0; bottom:0; left:0; width:62%; background: linear-gradient(to right, rgba(8,11,12,.78), rgba(8,11,12,0)); }}
.disp {{ font-family:"Marcellus",serif; font-weight:400; letter-spacing:.005em; line-height:1.06; }}
.mono {{ font-family:"Plex Mono",monospace; font-variant-numeric:tabular-nums; }}
.t {{ position:absolute; opacity:0; will-change:transform,opacity; }}
.place {{ left:120px; bottom:118px; font-size:52px; }}
.placesub {{ left:122px; bottom:78px; font-size:22px; color:var(--dim); letter-spacing:.04em; }}
.big {{ left:120px; top:50%; font-size:84px; max-width:1100px; transform:translateY(-50%); }}
.lab {{ font-size:20px; letter-spacing:.08em; color:var(--ink); background:rgba(10,14,15,.66); padding:9px 14px; border-radius:3px; }}
.plate {{ position:absolute; inset:0; }}
.plate img {{ position:absolute; inset:0; width:1920px; height:1080px; }}
.seam {{ position:absolute; top:0; bottom:0; width:3px; background:var(--ink); box-shadow:0 0 0 1px rgba(0,0,0,.25); }}
svg.fps {{ position:absolute; inset:0; width:1920px; height:1080px; }}
.fp {{ fill: color-mix(in srgb, var(--c) 34%, transparent); stroke: var(--c); stroke-width:2.2; opacity:0; }}
.legend {{ position:absolute; right:96px; bottom:84px; display:flex; gap:26px; font-size:21px; color:var(--ink); background:rgba(10,14,15,.72); padding:16px 22px; border-radius:4px; opacity:0; }}
.legend i {{ display:inline-block; width:14px; height:14px; border-radius:2px; margin-right:9px; vertical-align:-1px; }}
.legend b {{ font-weight:500; margin-left:6px; color:var(--dim); }}
.cap-r {{ position:absolute; left:96px; top:84px; font-size:22px; letter-spacing:.06em; color:var(--ink); opacity:0; }}
.crop {{ position:absolute; overflow:hidden; }}
.app {{ position:absolute; left:0; top:0; width:1920px; height:1200px; transform-origin:0 0; }}
.lower {{ position:absolute; left:0; right:0; bottom:0; height:168px; background:rgba(11,14,15,.9); border-top:1px solid var(--line); display:flex; align-items:center; padding-left:120px; }}
.lower span {{ font-size:50px; color:var(--ink); }}
.app.ph {{ display:grid; place-items:center; background:#151a1c; color:var(--faint); font:500 28px "Plex Mono"; width:1920px; height:1080px; }}
.card {{ position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:1320px; }}
.stat {{ font-size:250px; line-height:.9; white-space:nowrap; }}
.stat small {{ font-size:.38em; color:var(--faint); margin:0 .14em; }}
.proofline {{ font-size:40px; line-height:1.3; color:var(--ink); margin-top:44px; max-width:1180px; }}
.proofline b {{ font-weight:600; }}
.fine {{ font-size:22px; color:var(--faint); margin-top:30px; }}
table.ia {{ border-collapse:collapse; font-size:22px; }}
table.ia th {{ text-align:left; font-weight:500; color:var(--bronze); padding:12px 26px 12px 0; border-bottom:1px solid var(--line); white-space:nowrap; }}
table.ia td {{ padding:13px 26px 13px 0; border-bottom:1px solid var(--line); white-space:nowrap; color:var(--ink); }}
table.ia tr {{ opacity:0; }}
.cols {{ display:flex; flex-wrap:wrap; gap:10px 14px; max-width:1500px; margin-top:34px; }}
.col {{ font:400 19px "Plex Mono"; color:var(--dim); border:1px solid var(--line); padding:7px 11px; border-radius:3px; opacity:0; }}
.formats {{ margin-top:40px; font-size:30px; color:var(--ink); opacity:0; }}
.formats span {{ color:var(--faint); margin:0 .5em; }}
.reg {{ position:absolute; left:160px; right:160px; }}
.reg .row {{ border-top:1px solid var(--line); padding:30px 0 34px; opacity:0; display:grid; grid-template-columns: 640px 1fr; align-items:baseline; gap:40px; }}
.reg .who {{ font:400 30px "Marcellus"; letter-spacing:.16em; text-transform:uppercase; color:var(--bronze); }}
.reg .what {{ font:400 50px "Marcellus"; line-height:1.1; }}
.mark {{ position:absolute; left:50%; top:43%; width:220px; height:220px; transform:translate(-50%,-50%); color:var(--ink); opacity:0; }}
.word {{ position:absolute; left:50%; top:62%; transform:translateX(-50%); font:400 92px "Marcellus"; letter-spacing:.32em; padding-left:.32em; opacity:0; white-space:nowrap; }}
.sub {{ position:absolute; left:50%; top:73%; transform:translateX(-50%); font:500 24px "Plex Mono"; letter-spacing:.3em; text-transform:uppercase; color:var(--dim); opacity:0; white-space:nowrap; }}
.tag {{ position:absolute; left:50%; top:80%; transform:translateX(-50%); font:400 34px "Marcellus"; color:var(--ink); opacity:0; white-space:nowrap; }}
.grain {{ position:absolute; inset:-20px; pointer-events:none; opacity:.16; mix-blend-mode:overlay;
  background-image: radial-gradient(rgba(255,255,255,.10) 1px, transparent 1.2px), radial-gradient(rgba(0,0,0,.22) 1px, transparent 1.2px);
  background-size: 3px 3px, 5px 5px; z-index:50; }}
#black {{ position:absolute; inset:0; background:#000; z-index:60; opacity:1; }}
</style></head><body>

<div class="layer" id="s1"><img class="cover photo" id="s1i" src="{rel(os.path.join(A, 'cap_3200', CAP['open'] + '.jpg'))}"><div class="vig"></div><div class="scrim-b"></div>
  <div class="t disp place" id="s1t">Swannanoa, North Carolina</div>
  <div class="t mono placesub" id="s1s">28 September 2024 · Civil Air Patrol</div></div>

<div class="layer" id="s2"><img class="cover photo" id="s2i" src="{rel(os.path.join(A, 'cap_3200', CAP['debris'] + '.jpg'))}"><div class="vig"></div><div class="scrim-l"></div></div>
<div class="layer" id="s3"><img class="cover photo" id="s3i" src="{rel(os.path.join(A, 'cap_3200', CAP['river'] + '.jpg'))}"><div class="vig"></div><div class="scrim-l"></div></div>
<div class="t disp big" id="s23t" style="z-index:5">Two days after<br>Hurricane Helene.</div>

<div class="layer" id="s4"><div class="plate" id="s4p">
  <img src="{rel(os.path.join(A, 'plates', 'swannanoa_home_pre.jpg'))}">
  <div id="s4post" style="position:absolute;inset:0;clip-path:inset(0 0 0 100%)"><img src="{rel(os.path.join(A, 'plates', 'swannanoa_home_post.jpg'))}">
    <svg class="fps" viewBox="0 0 1920 1080">{polys('swannanoa_home')}</svg></div>
  <div class="seam" id="s4seam"></div></div>
  <div class="vig"></div>
  <div class="t mono lab" id="s4a" style="left:96px;top:84px">Before · February 2023</div>
  <div class="t mono lab" id="s4b" style="right:96px;top:84px">After · spring 2025</div></div>

<div class="layer" id="s5"><div class="plate" id="s5p"><img src="{rel(os.path.join(A, 'plates', 'swannanoa_wide_post.jpg'))}">
  <svg class="fps" id="s5svg" viewBox="0 0 1920 1080">{polys('swannanoa_wide')}</svg></div><div class="vig"></div>
  <div class="mono cap-r" id="s5c">Swannanoa · {ex['n']} structures read, one at a time</div>
  <div class="legend mono" id="s5l">{legend}</div></div>

<div class="layer" id="s6"><div class="plate" id="s6p"><img src="{rel(os.path.join(A, 'lidar', 'relief.png'))}">
  <div id="s6chg" style="position:absolute;inset:0;clip-path:inset(0 100% 0 0)"><img src="{rel(os.path.join(A, 'lidar', 'change.png'))}"></div></div><div class="vig"></div>
  <div class="mono cap-r" id="s6c">Ground change from lidar, 2017 to 2025</div>
  <div class="legend mono" id="s6l"><span><i style="background:#56A8D6"></i>Scoured</span><span><i style="background:#E09640"></i>Deposited</span><span><i style="background:transparent;border:2px solid #F4F1E8"></i>Buildings flagged</span></div></div>

<div class="layer" id="s7a"><div class="crop" style="inset:0">{app_img('overview')}</div><div class="lower"><span class="disp">Start from any FEMA disaster number.</span></div></div>
<div class="layer" id="s7b"><div class="crop" style="inset:0">{app_img('area')}</div><div class="lower"><span class="disp">893 buildings in 88 seconds, on a laptop.</span></div></div>
<div class="layer" id="s7c"><div class="crop" style="inset:0">{app_img('queue')}</div><div class="lower"><span class="disp">Hard calls first. Most severe, most occupied.</span></div></div>

<div class="layer" id="s8" style="background:var(--bg)">
  <div class="crop" style="left:820px;top:0;width:1100px;height:1080px;border-left:1px solid var(--line)">{app_img('verify')}</div>
  <div class="t disp" id="s8t1" style="left:120px;top:330px;font-size:70px;max-width:640px">Checked by people.<br>Blind to the model.</div>
  <div class="t" id="s8t2" style="left:122px;top:560px;font-size:31px;line-height:1.4;max-width:600px;color:var(--dim)">808 of 893 Swannanoa buildings have a Civil Air Patrol photo from two days after the storm.</div></div>

<div class="layer" id="s9" style="background:var(--bg)"><div class="card">
  <div class="disp stat" id="s9n">15<small>of</small>19</div>
  <div class="proofline" id="s9l">In Swannanoa, when the model called a home <b>Major or Destroyed</b>, county search teams agreed <b>15 times out of 19</b>.</div>
  <div class="fine" id="s9f">Not an accuracy figure: a tuning area, held against search-team field records.</div></div></div>

<div class="layer" id="s10" style="background:var(--bg)"><div class="card" style="width:1560px">
  <div class="disp" id="s10t" style="font-size:60px;opacity:0">The FEMA damage survey, filled in.</div>
  <div class="cols" id="s10c">{col_list}</div>
  <table class="ia mono" id="s10tab" style="margin-top:44px"><tr style="opacity:1">{table_head}</tr>{table_rows}</table>
  <div class="formats" id="s10f">GeoPackage<span>·</span>File Geodatabase<span>·</span>KML<span>·</span>CSV in US National Grid</div></div></div>

<div class="layer" id="s11" style="background:var(--bg)"><div class="reg" style="top:250px">
  <div class="row" id="r1"><div class="who">Emergency management</div><div class="what">A building-by-building count the day imagery arrives.</div></div>
  <div class="row" id="r2"><div class="who">Insurance and lending</div><div class="what">Check a building's condition before you pay on it.</div></div>
  <div class="row" id="r3"><div class="who">National Guard</div><div class="what">One damage picture, in US National Grid.</div></div></div></div>

<div class="layer" id="s12" style="background:var(--bg)">
  <svg class="mark" id="mark" viewBox="0 0 64 64">{MARK}</svg>
  <div class="word" id="word">GROMA</div>
  <div class="sub" id="sub">Disaster assessment</div>
  <div class="tag" id="tag">Building by building.</div>
  <div class="mono" id="credit" style="position:absolute;left:0;right:0;bottom:46px;text-align:center;font-size:17px;letter-spacing:.04em;color:var(--faint);opacity:0">Imagery: Civil Air Patrol / FEMA, NC OneMap, USGS 3DEP · Maps © OpenStreetMap contributors © CARTO · Decision support, not an official FEMA assessment</div></div>

<div class="grain" id="grain"></div>
<div id="black"></div>

<script>
const $ = id => document.getElementById(id);
const cl = (x,a=0,b=1) => Math.max(a, Math.min(b, x));
const lin = (t,a,b) => cl((t-a)/(b-a));
const eo = x => 1 - Math.pow(1-x, 3);            // ease out
const eio = x => x<.5 ? 4*x*x*x : 1 - Math.pow(-2*x+2,3)/2;
const win = (t,a,b,fi=.5,fo=.5) => Math.min(eo(lin(t,a,a+fi)), 1 - eio(lin(t,b-fo,b)));
function show(id, t, a, b, fi=.6, fo=.6) {{ const e=$(id); const o=win(t,a,b,fi,fo); e.style.opacity=o; return o; }}
function settle(id, t, a, b, fi=.9, dy=18, fo=.5) {{ // type settles into place: no fly-ins
  const e=$(id); const p=eo(lin(t,a,a+fi)); e.style.opacity = Math.min(p, 1-eio(lin(t,b-fo,b)));
  const base = e.dataset.base || (e.dataset.base = getComputedStyle(e).transform === 'none' ? '' : getComputedStyle(e).transform);
  e.style.transform = (base || '') + ` translateY(${{(1-p)*dy}}px)`; }}
function kb(id, t, a, b, s0, s1, x0=0, y0=0, x1=0, y1=0) {{ // Ken Burns on a centred cover image
  const p = lin(t,a,b); const s = s0+(s1-s0)*p, x = x0+(x1-x0)*p, y = y0+(y1-y0)*p;
  $(id).style.transform = `translate(-50%,-50%) translate(${{x}}px,${{y}}px) scale(${{s}})`; }}
function fps(svg, t, a, b) {{ // footprints appear in a left-to-right sweep
  for (const p of svg.querySelectorAll('.fp')) {{ const x = +p.dataset.x/1920; p.style.opacity = eo(lin(t, a+(b-a)*x*.85, a+(b-a)*x*.85+.5)); }} }}
function cam(id, t, a, b, f, g, smooth) {{ // move a crop's camera over a 1920x1200 capture: [x, y, scale]
  const im = $(id).querySelector('.app'); if (!im) return;
  const p = smooth ? eio(lin(t,a,b)) : lin(t,a,b); const v = f.map((x,i) => x+(g[i]-x)*p);
  im.style.transform = `translate(${{-v[0]*v[2]}}px,${{-v[1]*v[2]}}px) scale(${{v[2]}})`; }}
const MARK_SETTLE = (t, a) => {{ const u = Math.max(0, t-a); return 9*Math.exp(-u*1.25)*Math.cos(u*4.2); }};

window.DURATION = {DURATION};
window.render = function(t) {{
  $('black').style.opacity = 1 - eo(lin(t,0,1.2)) + eio(lin(t,{DURATION}-1.0,{DURATION}));
  $('grain').style.transform = `translate(${{(Math.floor(t*24)*7)%20-10}}px,${{(Math.floor(t*24)*13)%20-10}}px)`;
  // S1 0-5: the morning after
  show('s1', t, 0, 5.15, .1, .35); kb('s1i', t, 0, 5.2, 1.14, 1.24, 0, 20, -60, -10);
  settle('s1t', t, 1.0, 4.7); settle('s1s', t, 1.5, 4.7, .9, 10);
  // S2 5-8.5, S3 8.5-12
  show('s2', t, 4.9, 8.6, .35, .3); kb('s2i', t, 4.9, 8.7, 1.2, 1.1, 40, 0, -40, 10);
  show('s3', t, 8.4, 12.1, .3, .35); kb('s3i', t, 8.4, 12.2, 1.1, 1.2, 0, -20, 30, 10);
  settle('s23t', t, 5.5, 11.6, 1.0, 20, .6);
  // S4 12-20: before / after
  show('s4', t, 11.9, 20.1, .4, .4);
  const sw = eio(lin(t, 13.4, 17.4)); const sx = 1920*(1-sw);
  $('s4post').style.clipPath = `inset(0 0 0 ${{sx}}px)`; $('s4seam').style.left = (sx-1.5)+'px';
  $('s4seam').style.opacity = win(t, 13.2, 17.9, .3, .5);
  $('s4p').style.transform = `scale(${{1+0.06*lin(t,12,20)}})`;
  show('s4a', t, 12.4, 17.6, .5, .5); show('s4b', t, 12.4, 19.7, .5, .5);
  fps($('s4post').querySelector('svg'), t, 17.8, 19.3);
  // S5 20-26: every structure, read
  show('s5', t, 19.9, 26.1, .45, .4); $('s5p').style.transform = `scale(${{1.08-0.08*eo(lin(t,20,26))}})`;
  fps($('s5svg'), t, 20.4, 23.6); show('s5c', t, 20.8, 25.7); show('s5l', t, 22.6, 25.7);
  // S6 26-32: lidar
  show('s6', t, 25.9, 32.1, .4, .4); $('s6p').style.transform = `scale(${{1.0+0.07*lin(t,26,32)}})`;
  $('s6chg').style.clipPath = `inset(0 ${{100-100*eio(lin(t,26.8,29.6))}}% 0 0)`;
  show('s6c', t, 26.6, 31.6); show('s6l', t, 29.0, 31.6);
  // S7 32-38: the product, fast
  show('s7a', t, 31.9, 34.1, .2, .1); show('s7b', t, 34.0, 36.1, .1, .1); show('s7c', t, 36.0, 38.1, .1, .3);
  cam('s7a', t, 32, 34.1, [0,40,1.0], [440,60,1.3]);
  cam('s7b', t, 34, 36.1, [100,40,1.05], [293,80,1.18]);
  cam('s7c', t, 36, 38.1, [700,120,1.55], [853,170,1.8]);
  // S8 38-48: people check
  show('s8', t, 37.9, 48.1, .4, .5);
  cam('s8', t, 38.6, 47.4, [376,90,1.5], [376,428,1.5], true);
  settle('s8t1', t, 38.8, 47.6); settle('s8t2', t, 43.2, 47.6, 1.0, 12);
  // S9 48-55: proof
  show('s9', t, 47.9, 55.1, .5, .5); settle('s9n', t, 48.4, 54.8, 1.1, 14); settle('s9l', t, 49.4, 54.8, 1.0, 10); settle('s9f', t, 51.2, 54.8, 1.0, 8);
  // S10 55-60: export
  show('s10', t, 54.9, 60.1, .35, .4); settle('s10t', t, 55.2, 59.8, .8, 12);
  {{ const cs=$('s10c').children; for (let i=0;i<cs.length;i++) cs[i].style.opacity = eo(lin(t, 55.6+i*.07, 55.9+i*.07)); }}
  {{ const rs=$('s10tab').querySelectorAll('tr'); for (let i=1;i<rs.length;i++) rs[i].style.opacity = eo(lin(t, 56.9+i*.22, 57.3+i*.22)); }}
  show('s10f', t, 58.2, 60.0, .6, .4);
  // S11 60-65.5: who it is for
  show('s11', t, 59.9, 65.6, .35, .45);
  for (const [id,a] of [['r1',60.4],['r2',61.7],['r3',63.0]]) settle(id, t, a, 65.3, .8, 12, .4);
  // S12 65.5-72: the instrument
  show('s12', t, 65.4, 72.5, .4, .1);
  {{ const m=$('mark'); m.style.opacity = eo(lin(t,65.7,66.7)); const a = MARK_SETTLE(t, 65.9);
     $('plumbL').setAttribute('transform', `rotate(${{a}} 12 15)`); $('plumbR').setAttribute('transform', `rotate(${{a}} 52 15)`); }}
  settle('word', t, 66.5, 72.5, 1.0, 10, .1); settle('sub', t, 67.2, 72.5, .9, 8, .1); settle('tag', t, 68.4, 72.5, 1.0, 8, .1); show('credit', t, 69.0, 72.5, .8, .1);
}};
window.render(0);
</script></body></html>"""
    with open(os.path.join(BUILD, "composition.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote", os.path.join(BUILD, "composition.html"), "app captures:", "yes" if have_app else "placeholders")


if __name__ == "__main__":
    main()
