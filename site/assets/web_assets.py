"""Write the website's external files: `python3 site/assets/web_assets.py`.

The page loads these by relative path (assets/web/...) instead of carrying
them inline, so it paints after a small HTML file and the hero photograph; the
3D map's imagery and elevation grid load only when the map nears the viewport.
"""
import base64
import json
import os
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "web")
TERR = os.path.join(HERE, "terrain")


def webp(src: str, dst: str, width: int | None = None, quality: int = 72) -> None:
    im = Image.open(src)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, dst), "WEBP", quality=quality, method=6)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    webp(os.path.join(HERE, "hero.jpg"), "hero.webp", 1920, 70)
    webp(os.path.join(HERE, "hero.jpg"), "hero-960.webp", 960, 70)
    webp(os.path.join(TERR, "poster.jpg"), "poster.webp", None, 74)
    webp(os.path.join(TERR, "post.jpg"), "post.webp", None, 60)
    webp(os.path.join(TERR, "pre.jpg"), "pre.webp", None, 60)
    webp(os.path.join(TERR, "anatomy_change.jpg"), "anatomy_change.webp", None, 78)
    for f in ("heat.png", "ground.png", "anatomy_ground.png"):
        shutil.copy(os.path.join(TERR, f), os.path.join(OUT, f))
    # the elevation grid (uint16 decimetres) as a JSON string: static hosts and the
    # artifact host both serve .json, not raw binary
    with open(os.path.join(TERR, "dem.u16"), "rb") as fh:
        dem = base64.b64encode(fh.read()).decode()
    with open(os.path.join(OUT, "dem.json"), "w", encoding="utf-8") as fh:
        json.dump(dem, fh)
    rec = json.load(open(os.path.join(HERE, "chips.json"), encoding="utf-8"))["e874056f"]
    for k in ("pre", "post"):
        head, b = rec[k].split(",", 1)
        with open(os.path.join(OUT, f"chip_{k}.{'jpg' if 'jpeg' in head else 'png'}"), "wb") as fh:
            fh.write(base64.b64decode(b))
    for f in sorted(os.listdir(OUT)):
        print(f"{f:22s} {os.path.getsize(os.path.join(OUT, f)) // 1024:5d} KB")


if __name__ == "__main__":
    main()
