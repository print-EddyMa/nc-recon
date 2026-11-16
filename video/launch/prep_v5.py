"""Prepare the hype cut's stills: `python3 video/launch/prep_v5.py` (needs numpy, PIL, skimage, scipy).

goes_c/  the Helene satellite frames, cropped to follow the storm
topo/t_* the best tiles from two USGS paper maps (1900 and 1941), which are stored as JPEG tiles in the PDFs
glyph/   map specimens drawn from our own data (site/assets/terrain, buildings.json)
paper.png a seamless paper grain, multiplied over flat colours
"""
import json, math, os, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter, zoom
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets", "v5")
TERR = os.path.join(HERE, "..", "..", "site", "assets", "terrain")
Image.MAX_IMAGE_PIXELS = None
INK = (24, 22, 20, 255)
SIG = (255, 90, 31, 255)


def goes():
    src = sorted(f for f in os.listdir(os.path.join(A, "goes")) if f.endswith(".jpg"))
    out = os.path.join(A, "goes_c"); os.makedirs(out, exist_ok=True)
    cs = []
    for f in src:
        im = Image.open(os.path.join(A, "goes", f)).convert("L")
        a = np.asarray(im.resize((250, 250)), "float32")
        a = gaussian_filter(np.clip(a - 150, 0, None), 22)
        y, x = np.unravel_index(np.argmax(a), a.shape)
        cs.append((x * 8, y * 8))
    c = np.array(cs, "float32")
    for k in range(2):
        c[:, k] = gaussian_filter(np.interp(np.arange(len(c)), np.arange(len(c)), np.median(np.stack([np.roll(c[:, k], i) for i in range(-3, 4)]), axis=0)), 4, mode="nearest")
    R = 800
    for i, f in enumerate(src):
        im = Image.open(os.path.join(A, "goes", f)).convert("RGB")
        x, y = c[i]
        x = min(max(R, x), 2000 - R); y = min(max(R, y), 2000 - R)
        im.crop((int(x - R), int(y - R), int(x + R), int(y + R))).resize((1400, 1400), Image.LANCZOS).save(os.path.join(out, f"{i:04d}.jpg"), quality=88)
    print("goes", len(src), c[0], c[-1])


def topo():
    for n in ("mitchell1900", "black1941"):
        b = open(os.path.join(A, "topo", n + ".pdf"), "rb").read()
        tiles, i = [], 0
        while True:
            s = b.find(b"\xff\xd8\xff", i)
            if s < 0:
                break
            e = b.find(b"endstream", s)
            tiles.append(b[s:e]); i = e
        scored = []
        import io
        for t in tiles:
            try:
                im = Image.open(io.BytesIO(t)).convert("RGB")
            except Exception:
                continue
            if min(im.size) < 700:
                continue
            a = np.asarray(im.resize((200, 200)), "float32")
            scored.append((a.std(), im))
        scored.sort(key=lambda s: -s[0])
        for k, (_s, im) in enumerate(scored[:8]):
            im.save(os.path.join(A, "topo", f"t_{n}_{k}.jpg"), quality=90)
        print("topo", n, len(scored))


def paper():
    rng = np.random.default_rng(5)
    n = rng.standard_normal((1024, 1024))
    a = gaussian_filter(n, 0.7, mode="wrap") * 2.2 + gaussian_filter(n, 6, mode="wrap") * 14 + gaussian_filter(n, 40, mode="wrap") * 50
    a = 255 - np.clip(np.abs(a) * 7, 0, 60)
    Image.fromarray(a.astype("uint8")).save(os.path.join(A, "paper.png"))


def glyphs():
    out = os.path.join(A, "glyph"); os.makedirs(out, exist_ok=True)
    L = json.load(open(os.path.join(TERR, "layers.json")))
    S = 1400
    def canvas():
        im = Image.new("RGBA", (S * 2, S * 2), (0, 0, 0, 0)); return im, ImageDraw.Draw(im)
    def save(im, name):
        im.resize((S, S), Image.LANCZOS).save(os.path.join(out, name + ".png"))
    d = L["dem"]
    dem = np.frombuffer(open(os.path.join(TERR, "dem.u16"), "rb").read(), "uint16").reshape(d["h"], d["w"]).astype("float32") / 10
    sm = gaussian_filter(zoom(dem, 4, order=3), 3)
    sc = S * 2 / max(sm.shape)
    # contour rings around the highest ground
    y0, x0 = np.unravel_index(np.argmax(gaussian_filter(sm, 30)), sm.shape)
    im, dr = canvas()
    win = 300; crop = sm[max(0, y0 - win):y0 + win, max(0, x0 - win):x0 + win]
    for lv, w in zip(np.arange(crop.min(), crop.max(), 20), range(10000)):
        for c in measure.find_contours(crop, lv):
            dr.line([(p[1] / crop.shape[1] * S * 2, p[0] / crop.shape[0] * S * 2) for p in c], fill=INK, width=9 if int(w) % 5 == 0 else 3)
    save(im, "contours")
    # the river
    im, dr = canvas()
    for r in L["rivers"]:
        pts = [(p[0] * S * 2, (p[1] * 0.694 + 0.15) * S * 2) for p in r["p"]]
        dr.line(pts, fill=(30, 80, 170, 255), width=16, joint="curve")
    save(im, "rivers")
    # roads likely cut
    im, dr = canvas()
    for r in L["roads"]:
        pts = [((p[0] - 0.3) / 0.62 * S * 2, (p[1] - 0.23) / 0.62 * S * 2) for p in r["p"]]
        dr.line(pts, fill=SIG if r["s"] == "blocked" else INK, width=20)
    save(im, "roads")
    # one 1 km search sector
    im, dr = canvas()
    dr.rectangle((S * 0.5, S * 0.5, S * 1.5, S * 1.5), outline=INK, width=22)
    dr.rectangle((S * 0.5 - 6, S * 0.5 - 6, S * 0.72, S * 0.72), fill=SIG)
    save(im, "sector")
    # a landing zone candidate
    im, dr = canvas()
    c = S
    for r, w in ((420, 26), (250, 12)):
        dr.ellipse((c - r, c - r, c + r, c + r), outline=INK, width=w)
    dr.ellipse((c - 40, c - 40, c + 40, c + 40), fill=SIG)
    save(im, "lz")
    # neutral building outlines, no damage: town seen from above, in ink
    fp = json.load(open(os.path.join(HERE, "assets", "v4", "buildings.json")))
    im, dr = canvas()
    for u, v, l, s, a in fp:
        x = (u - 0.40) / 0.28 * S * 2; y = (v - 0.27) / 0.28 * S * 2
        l2, s2 = max(l, 8) * 0.7, max(s, 7) * 0.7
        t = math.radians(a); ct, st = math.cos(t), math.sin(t)
        pts = [(x + i * l2 * ct - j * s2 * st, y + i * l2 * st + j * s2 * ct) for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        dr.polygon(pts, fill=INK)
    save(im, "town")
    print("glyphs")


# Civil Air Patrol obliques (crop windows as fractions of the frame), then DVIDS ground frames, wide to close
CAP = [("3e4341f10f55e585", .02, .05), ("b74798641e3c5744", .25, .2), ("c12cece8353397b5", .1, .3), ("0d55dc25ac623808", .3, .1)]
DV = [24, 25, 26, 29, 33, 34, 36, 38, 39, 41, 42, 44, 45, 3, 4, 5, 6, 7, 9, 10, 11, 15, 16, 17, 18, 19, 21, 22, 23, 28, 30, 31, 35, 12, 14, 20]


def photos():
    """The flash: one print per damage assessment. Black and white, equal brightness, so fast cuts do not strobe."""
    out = os.path.join(A, "photos"); os.makedirs(out, exist_ok=True)
    src = []
    caps = sorted(f for f in os.listdir(os.path.join(HERE, "assets", "cap_3200")) if f.endswith(".jpg"))
    for f in caps:
        im = Image.open(os.path.join(HERE, "assets", "cap_3200", f)).convert("L")
        W, H = im.size
        for fx, fy in ((.05, .1), (.42, .3)):
            w = int(W * .56); h = int(w * 2 / 3)
            src.append(im.crop((int(W * fx), int(H * fy), int(W * fx) + w, min(H, int(H * fy) + h))))
    for n in DV:
        p = os.path.join(A, "dv", f"DOD_110675946_{n:03d}.jpg")
        if os.path.exists(p):
            im = Image.open(p).convert("L"); W, H = im.size
            w = min(W, int(H * 1.5)); x = (W - w) // 2
            src.append(im.crop((x, 0, x + w, H)))
    for i, im in enumerate(src):
        a = np.asarray(im.resize((1200, 800), Image.LANCZOS), "float32") / 255
        a = (a - a.mean()) / (a.std() + 1e-6) * 0.2 + 0.44
        a = np.clip(a, 0, 1)
        Image.fromarray((a * 255).astype("uint8")).save(os.path.join(out, f"{i:02d}.jpg"), quality=88)
    print("photos", len(src))


if __name__ == "__main__":
    import sys
    for f in (sys.argv[1:] or ["goes", "topo", "paper", "glyphs", "photos"]):
        globals()[f]()
