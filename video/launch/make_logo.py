"""The NC Recon mark, "the odd one out": nine buildings from above, one knocked off
its foundation. `python3 video/launch/make_logo.py` writes docs/brand/.
Geometry lives here; the film's Blender reveal imports these numbers."""
import json, os

S, P, O = 24.0, 29.0, 7.0          # tile size, pitch, origin (viewBox 0 0 100 100)
HIT = (2, 2)                       # row, col of the knocked tile
DX, DY, ROT = 4.2, 3.4, 19.0       # how far it was knocked
INK_DARK, INK_LIGHT, SIG = "#F5F3EE", "#111111", "#FF5A1F"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "docs", "brand")


def tiles(ink: str, sig: str = SIG) -> str:
    out = []
    for r in range(3):
        for c in range(3):
            x, y = O + c * P, O + r * P
            if (r, c) == HIT:
                cx, cy = x + S / 2 + DX, y + S / 2 + DY
                out.append(f'<rect x="{cx - S / 2:g}" y="{cy - S / 2:g}" width="{S:g}" height="{S:g}" fill="{sig}" '
                           f'transform="rotate({ROT:g} {cx:g} {cy:g})"/>')
            else:
                out.append(f'<rect x="{x:g}" y="{y:g}" width="{S:g}" height="{S:g}" fill="{ink}"/>')
    return "".join(out)


def svg(body: str, view: str = "0 0 100 100") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="NC Recon"><title>NC Recon</title>{body}</svg>\n'


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    w = lambda n, s: open(os.path.join(OUT, n), "w", encoding="utf-8").write(s)  # noqa: E731
    w("mark-on-dark.svg", svg(tiles(INK_DARK)))
    w("mark-on-light.svg", svg(tiles(INK_LIGHT)))
    w("app-icon.svg", svg('<rect x="-16" y="-16" width="132" height="132" rx="28" fill="#0B0B0B"/>' + tiles(INK_DARK), "-16 -16 132 132"))
    print("wrote", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
