"""Build the NC Recon website: `python3 site/build.py`.

Writes two copies from template.html, assets/chips.json and assets/terrain/
(baked from real public data by assets/prep_terrain.py):
  site/index.html     a complete static page (serve the folder from any static host)
  site/artifact.html  the same page without the document wrapper, for publishing

Images and the elevation grid are separate files in assets/web/ (written by
assets/web_assets.py) so the page itself stays small; the fonts live there too,
in assets/web/fonts/. Publish that folder with the page, at the same relative
paths.

Set CONTACT before launch (an email or URL shown in the pilot section).
"""
import json
import os
import re
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CONTACT = "ma.eddy.work@gmail.com"  # shown on the site: pilot requests, questions, the hosted-plan list
REPO = "https://github.com/print-EddyMa/nc-recon"
EXAMPLE = "e874056f"  # Swannanoa manufactured home: search team and model both say Destroyed


def mark() -> str:
    """The NC Recon mark, "the odd one out": eight tiles in ink, one orange tile knocked out of line.
    Same geometry as docs/brand/mark-on-dark.svg; the ink follows the band it sits on."""
    tiles = "".join(f'<rect x="{x}" y="{y}" width="24" height="24"/>' for y in (7, 36, 65) for x in (7, 36, 65) if (x, y) != (65, 65))
    return (f'<svg viewBox="0 0 100 100" aria-hidden="true"><g fill="currentColor">{tiles}</g>'
            '<rect x="69.2" y="68.4" width="24" height="24" fill="var(--signal)" transform="rotate(19 81.2 80.4)"/></svg>')


WEB_FILES = ("hero.webp", "hero-960.webp", "poster.webp", "post.webp", "pre.webp", "heat.png", "ground.png",
             "dem.json", "anatomy_change.webp", "anatomy_ground.png", "chip_pre.jpg", "chip_post.jpg",
             "fonts/archivo-latin-standard-normal.woff2", "fonts/ibm-plex-mono-latin-500-normal.woff2")


def main() -> None:
    t = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    rec = json.load(open(os.path.join(HERE, "assets", "chips.json"), encoding="utf-8"))[EXAMPLE]
    p = rec["probs"]
    levels = ["no_damage", "affected", "minor", "major", "destroyed"]
    colours = ["var(--d0)", "var(--d1)", "var(--d2)", "var(--d3)", "var(--d4)"]
    bars = "".join(f'<i style="height:{max(2, round(100 * p[k]))}%;background:{c}"></i>' for k, c in zip(levels, colours))
    ring = lambda r: " ".join(f"{x},{y}" for x, y in r)  # noqa: E731
    favicon = open(os.path.join(HERE, "logo.svg"), encoding="utf-8").read()
    assert CONTACT, "set CONTACT: the site's pilot and pricing buttons mail it"
    brief = (f'<a href="mailto:{CONTACT}?subject=NC%20Recon%20pilot%20request"><span class="arr" aria-hidden="true"></span>'
             '<div><b>Request a free pilot</b><span>For an emergency management office, an insurer, a Guard unit or an aid group.</span></div></a>'
             if CONTACT else
             '<a href="#explore"><span class="arr up" aria-hidden="true"></span><div><b>See it work</b>'
             '<span>Turn the Swannanoa valley in 3D, with the damage, roads cut and search sectors.</span></div></a>')
    terr = os.path.join(HERE, "assets", "terrain")
    missing = [f for f in WEB_FILES if not os.path.exists(os.path.join(HERE, "assets", "web", f))]
    fonts = [f for f in missing if f.startswith("fonts/")]
    assert not fonts, f"copy the fonts into site/assets/web/fonts/ (see site/README.md): {fonts}"
    assert not missing, f"run python3 site/assets/web_assets.py first: {missing}"
    layers = json.load(open(os.path.join(terr, "layers.json"), encoding="utf-8"))
    # heavy files stay outside the page (assets/web, written by assets/web_assets.py) and load
    # only when the 3D map comes into view
    web = "assets/web/"
    assets = {"post": web + "post.webp", "pre": web + "pre.webp", "heat": web + "heat.png",
              "ground": web + "ground.png", "dem": web + "dem.json"}
    as_json = lambda o: json.dumps(o, separators=(",", ":")).replace("</", "<\\/")  # noqa: E731
    subs = {
        "__LAYERS__": as_json(layers), "__ASSETS__": as_json(assets),
        "__ANAT_CHANGE__": web + "anatomy_change.webp", "__ANAT_GROUND__": web + "anatomy_ground.png",
        "__N_STRUCT__": f"{layers['structures']:,}", "__USNG__": layers["anatomy"]["usng"],
        "__FAVICON__": urllib.parse.quote(favicon.split("<title>")[0] + favicon.split("</title>")[1]),
        "__PRE__": web + "chip_pre.jpg", "__POST__": web + "chip_post.jpg",
        "__RING_PRE__": ring(rec["pre_ring"]), "__RING_POST__": ring(rec["post_ring"]),
        "__PROB_BARS__": bars, "__NCR_SHORT__": rec["ncr_id"][:8],
        "__P_DESTROYED__": str(round(100 * p["destroyed"])), "__P_MAJOR__": str(round(100 * p["major"])),
        "__P_MINOR__": str(round(100 * p["minor"])),
        "__J_ND__": str(p["no_damage"]), "__J_AF__": str(p["affected"]), "__J_MI__": str(p["minor"]),
        "__J_MA__": str(p["major"]), "__J_DE__": str(p["destroyed"]),
        "__BRIEF__": brief, "__REPO__": REPO, "__CONTACT__": CONTACT,
    }
    for k, v in subs.items():
        t = t.replace(k, v)
    t = t.replace("__MARK__", mark())
    left = re.findall(r"__[A-Z][A-Z_]+__", t)
    assert not left, left[:5]
    assert "—" not in t, "no em dashes"
    with open(os.path.join(HERE, "artifact.html"), "w", encoding="utf-8") as fh:
        fh.write(t)
    head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
    body_at = t.index("<header")
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(head + t[:body_at] + "</head>\n<body>\n" + t[body_at:] + "\n</body>\n</html>\n")
    print(f"site/index.html {os.path.getsize(os.path.join(HERE, 'index.html')) // 1024} KB")


if __name__ == "__main__":
    main()
