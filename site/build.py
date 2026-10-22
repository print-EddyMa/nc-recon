"""Build the Groma website: `python3 site/build.py`.

Writes two copies from template.html, assets/chips.json and assets/terrain/
(baked from real public data by assets/prep_terrain.py):
  site/index.html     a complete static page (drop the folder on any static host)
  site/artifact.html  the same page without the document wrapper, for publishing

Set CONTACT before launch (an email or URL shown in the pilot section).
"""
import base64
import json
import os
import re
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CONTACT = ""          # e.g. "pilots@your-domain.org"; when set, "Request a briefing" buttons appear
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


def main() -> None:
    t = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    rec = json.load(open(os.path.join(HERE, "assets", "chips.json"), encoding="utf-8"))[EXAMPLE]
    p = rec["probs"]
    levels = ["no_damage", "affected", "minor", "major", "destroyed"]
    colours = ["var(--d0)", "var(--d1)", "var(--d2)", "var(--d3)", "var(--d4)"]
    bars = "".join(f'<i style="height:{max(2, round(100 * p[k]))}%;background:{c}"></i>' for k, c in zip(levels, colours))
    ring = lambda r: " ".join(f"{x},{y}" for x, y in r)  # noqa: E731
    favicon = open(os.path.join(HERE, "logo.svg"), encoding="utf-8").read()
    brief = f'<a class="btn" href="mailto:{CONTACT}?subject=Groma%20briefing">Request a briefing</a>' if CONTACT else ""
    ins = json.load(open(os.path.join(HERE, "assets", "instrument.json"), encoding="utf-8"))
    instrument = (f'<figure class="instrument" aria-hidden="true" style="aspect-ratio:{ins["w"]}/{ins["h"]}">'
                  f'<i class="br" style="--m:url({ins["bronze"]})"></i><i class="ln" style="--m:url({ins["lines"]})"></i></figure>')
    terr = os.path.join(HERE, "assets", "terrain")

    def uri(name: str, mime: str) -> str:
        with open(os.path.join(terr, name), "rb") as fh:
            return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()

    layers = json.load(open(os.path.join(terr, "layers.json"), encoding="utf-8"))
    with open(os.path.join(terr, "dem.u16"), "rb") as fh:
        dem = base64.b64encode(fh.read()).decode()
    assets = {"post": uri("post.jpg", "image/jpeg"), "pre": uri("pre.jpg", "image/jpeg"),
              "heat": uri("heat.png", "image/png"), "ground": uri("ground.png", "image/png"), "dem": dem}
    as_json = lambda o: json.dumps(o, separators=(",", ":")).replace("</", "<\\/")  # noqa: E731
    subs = {
        "__LAYERS__": as_json(layers), "__ASSETS__": as_json(assets),
        "__POSTER__": uri("poster.jpg", "image/jpeg"), "__ANAT_CHANGE__": uri("anatomy_change.jpg", "image/jpeg"),
        "__ANAT_GROUND__": uri("anatomy_ground.png", "image/png"),
        "__N_STRUCT__": f"{layers['structures']:,}", "__USNG__": layers["anatomy"]["usng"],
        "__MARK_INNER__": MARK_INNER, "__MARK__": MARK,
        "__FAVICON__": urllib.parse.quote(favicon.split("<title>")[0] + favicon.split("</title>")[1]),
        "__PRE__": rec["pre"], "__POST__": rec["post"],
        "__RING_PRE__": ring(rec["pre_ring"]), "__RING_POST__": ring(rec["post_ring"]),
        "__PROB_BARS__": bars, "__NCR_SHORT__": rec["ncr_id"][:8],
        "__P_DESTROYED__": str(round(100 * p["destroyed"])), "__P_MAJOR__": str(round(100 * p["major"])),
        "__P_MINOR__": str(round(100 * p["minor"])),
        "__J_ND__": str(p["no_damage"]), "__J_AF__": str(p["affected"]), "__J_MI__": str(p["minor"]),
        "__J_MA__": str(p["major"]), "__J_DE__": str(p["destroyed"]),
        "__BRIEF__": brief, "__REPO__": REPO, "__INSTRUMENT__": instrument,
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
