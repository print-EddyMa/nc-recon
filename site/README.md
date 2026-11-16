# NC Recon website

Static, self-contained site for NC Recon.

* Edit `template.html`, then run `python3 site/build.py`.
* `index.html` is the complete page: drag the `site/` folder onto Netlify (or
  any static host). `artifact.html` is the same page for Claude artifacts.
* Set `CONTACT` in `build.py` before launch; empty, the contact line is left out.
* `logo.svg` is the favicon: `docs/brand/app-icon.svg`, the mark "the odd one
  out" (3x3 tiles, one orange tile knocked out of line). `mark()` in `build.py`
  writes the same tiles inline for the header and footer.
* Fonts are self-hosted in `assets/web/fonts/` with their OFL licences: Archivo
  (from `video/launch/assets/fonts/`) and IBM Plex Mono 500. three.js from
  jsDelivr is the only third-party script.
* The look follows the launch film; the rules are in `DESIGN.md`, under The site.
* The hero record is real (Swannanoa, NC OneMap public imagery, Buncombe's
  search-team waypoint). Check trademarks before using the name commercially:
  a Czech geodetic package and a Bitsight product are also called NC Recon.
