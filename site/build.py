"""Build the Groma website: `python3 site/build.py`.

Writes two copies from template.html, assets/chips.json and assets/terrain/
(baked from real public data by assets/prep_terrain.py):
  site/index.html     a complete static page (serve the folder from any static host)
  site/artifact.html  the same page without the document wrapper, for publishing

Images and the elevation grid are separate files in assets/web/ (written by
assets/web_assets.py) so the page itself stays small; publish that folder with
the page, at the same relative paths.

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

MARK_INNER = (
    '<g fill="none" stroke="currentColor" stroke-linecap="round">'
    '<line x1="32" y1="9" x2="32" y2="55" stroke-width="3.2"/>'
    '<line x1="9" y1="15" x2="55" y2="15" stroke-width="3.2"/>'
    '<line x1="6" y1="56" x2="58" y2="56" stroke-width="3.2"/></g>'
    '<g class="plumb" style="--px:12px"><line x1="12" y1="15" x2="12" y2="39" stroke="currentColor" stroke-width="1.4"/>'
    '<path d="M12 38.5 l-3.6 3.4 3.6 6 3.6-6z" fill="var(--bronze)"/></g>'
    '<g class="plumb" style="--px:52px"><line x1="52" y1="15" x2="52" y2="39" stroke="currentColor" stroke-width="1.4"/>'
    '<path d="M52 38.5 l-3.6 3.4 3.6 6 3.6-6z" fill="var(--bronze)"/></g>'
    '<circle cx="32" cy="9" r="2.6" fill="var(--bronze)"/>'
)
MARK = f'<svg viewBox="0 0 64 64" aria-hidden="true">{MARK_INNER}</svg>'


WEB_FILES = ("hero.webp", "hero-960.webp", "poster.webp", "post.webp", "pre.webp", "heat.png", "ground.png",
             "dem.json", "anatomy_change.webp", "anatomy_ground.png", "chip_pre.jpg", "chip_post.jpg")


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
    brief = (f'<a href="mailto:{CONTACT}?subject=Groma%20pilot%20request"><span class="arr" aria-hidden="true">→</span>'
             '<b>Request a free pilot</b><span>For an emergency management office, an insurer, a Guard unit or an aid group.</span></a>'
             if CONTACT else
             '<a href="#explore"><span class="arr" aria-hidden="true">↑</span><b>See it work</b>'
             '<span>Turn the Swannanoa valley in 3D, with the damage, roads cut and search sectors.</span></a>')
    terr = os.path.join(HERE, "assets", "terrain")
    missing = [f for f in WEB_FILES if not os.path.exists(os.path.join(HERE, "assets", "web", f))]
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
        "__MARK_INNER__": MARK_INNER, "__MARK__": MARK,
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
