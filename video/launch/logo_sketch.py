"""Logo directions for NC Recon. Writes sketch.html (a contact sheet) from plain geometry."""
import math

INK, SIG = "#F4F2EC", "#FF5A1F"
def tile(x, y, s, r=0, fill=INK, rx=0.0):
    t = f' transform="rotate({r} {x+s/2} {y+s/2})"' if r else ""
    return f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="{rx}" fill="{fill}"{t}/>'

def grid3():
    out = []
    for r in range(3):
        for c in range(3):
            hit = (r, c) == (1, 2)
            x, y = 10 + c * 28, 10 + r * 28
            out.append(tile(x + (3 if hit else 0), y - (2 if hit else 0), 24, 24 if hit else 0, SIG if hit else INK))
    return out

def blockN():
    cells = [(0,0),(1,0),(2,0),(3,0),(1,1),(2,2),(0,3),(1,3),(2,3),(3,3)]   # (row, col): an N in a 4x4 block
    out = []
    for r, c in cells:
        hit = (r, c) == (2, 2)
        x, y = 6 + c * 22, 6 + r * 22
        out.append(tile(x + (2 if hit else 0), y + (1 if hit else 0), 18, 22 if hit else 0, SIG if hit else INK))
    return out

def roof():
    # a hip roof from above: what a house looks like from the sky. One facet is gone.
    g = 2.4
    return [f'<polygon points="12,20 88,20 66,50 34,50" fill="{INK}"/>',
            f'<polygon points="12,{20+g+1} {34-g},50 12,{80-g-1}" fill="{INK}"/>',
            f'<polygon points="34,{50+g} 66,{50+g} 88,80 12,80" fill="{INK}"/>',
            f'<polygon points="{88+7},{20+4} {66+12},{50+1} {88+11},{80-3}" fill="{SIG}"/>']

def brackets():
    b = 'fill="none" stroke-width="7" stroke-linecap="butt" stroke="%s"' % INK
    return [f'<path d="M10 30V10H30M70 10H90V30M90 70V90H70M30 90H10V70" {b}/>', tile(35, 35, 30, 14, SIG)]

def ring():
    return [f'<rect x="22" y="22" width="56" height="56" fill="{INK}"/>',
            f'<circle cx="50" cy="50" r="38" fill="none" stroke="#0B0B0B" stroke-width="9"/>',
            f'<circle cx="50" cy="50" r="38" fill="none" stroke="{SIG}" stroke-width="4"/>']

def plumbline():
    # R made of a footprint and a scan cut
    return [f'<path d="M18 12H62A26 26 0 0 1 62 64H52L80 90H58L34 64V90H18Z" fill="{INK}"/>',
            f'<rect x="34" y="28" width="28" height="20" fill="#0B0B0B"/>',
            tile(39, 31, 14, 20, SIG)]

MARKS = [("The odd one out: a block of nine, one knocked off its foundation", grid3()),
         ("The block N: an N made of buildings, one knocked loose", blockN()),
         ("The roof: a house from the sky, one facet torn away", roof()),
         ("The lock-on: detection brackets on one tilted building", brackets()),
         ("The ping: one building, one scan ring", ring()),
         ("The R: a footprint letter with a building off-axis", plumbline())]

cards = []
for name, m in MARKS:
    svg = f'<svg viewBox="0 0 100 100" width="210" height="210">{"".join(m)}</svg>'
    small = f'<svg viewBox="0 0 100 100" width="32" height="32">{"".join(m)}</svg>'
    tiny = f'<svg viewBox="0 0 100 100" width="16" height="16">{"".join(m)}</svg>'
    cards.append(f'<div class="c">{svg}<div class="row">{small}{tiny}<b>NC RECON</b></div><p>{name}</p></div>')
open("sketch.html", "w").write('''<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#0B0B0B;color:#F4F2EC;font:15px "Helvetica Neue",Arial,sans-serif}
.g{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#222}
.c{background:#0B0B0B;padding:26px;text-align:center}.row{display:flex;gap:14px;align-items:center;justify-content:center;margin-top:12px}
b{font:800 24px/1 "Helvetica Neue",Arial,sans-serif;letter-spacing:.02em}p{color:#999;margin:10px 0 0;font-size:13px}</style><div class="g">'''
  + "".join(cards) + "</div>")
