# Groma security model and review record

*Security review of the integrated build, 2026-10-22. What the service
protects, how, what was found and fixed in this review, and what an operator
must still do. The checks that keep these properties true are in
`pipeline/tests/test_security.py`.*

## What is protected, and from whom

| Data | Who may see it | Why |
|---|---|---|
| Building-level calls (centroids, probabilities, chips, imagery tiles) | responders with the service token | a centroid is nearly an address; a damage call on a home is sensitive |
| Addresses (`<area>.responder.json`) | responders | personal data from FEMA USA Structures |
| Labels, Verify judgments, verifier names | responders | ground truth and the names of the people who made it |
| Response products (cut-off clusters, landing zones, sectors, flagged facilities) | responders | they locate people who cannot leave |
| Civil Air Patrol photos | responders | obliques can show people, vehicles and homes |
| Area summaries, public tract-level GeoJSON, hazard profiles, health | anyone | aggregates with no address or building id |

## Controls

* **Fail-closed access.** Every responder route calls `auth.check`: with
  `TERRATRIAGE_TOKEN` set, a request needs `Authorization: Bearer <token>`
  (constant-time compare); with no token the routes answer 403. There is no
  "localhost is trusted" rule, because behind a reverse proxy every request
  arrives from 127.0.0.1. `NCR_DEV_OPEN=1` is refused on a non-loopback
  bind, and the server refuses to start on a public address without a token.
* **Rate limits per client** (`guard.py`): reads 600/min, writes 30/min,
  feeds 120/min, and an **upstream** bucket of 30/min for routes that make the
  server call outside services on the client's behalf (`/ops/coverage`,
  photo thumbnails). `X-Forwarded-For` is honoured only with
  `NCR_TRUST_PROXY=1`.
* **Browser headers on every response**: a Content Security Policy with
  hashed inline scripts and no `unsafe-eval`, `frame-ancestors 'none'`,
  `object-src 'none'`, `nosniff`, `no-referrer`, `X-Frame-Options: DENY`, and
  `Cache-Control: no-store` on API answers. CORS allows only `CORS_ORIGINS`.
  HSTS comes from the bundled Caddy proxy.
* **Inputs that reach files or queries are constrained**: area ids
  `[a-z0-9_]{1,40}`, photo keys 16 hex characters, event ids
  `[a-z0-9-]{3,40}`, FEMA numbers 1 to 9999. Cache keys are refused if they
  contain a path separator, `..` or NUL. ArcGIS where-clauses are built only
  from config values, fixed constants, ISO dates, integers, a storm keyword
  limited to letters, digits, spaces and hyphens, and a county name limited
  to letters, spaces, dots and hyphens. Overpass queries are built from fixed
  tags and numeric bounding boxes.
* **Outbound fetches stay on fixed hosts.** No route fetches a URL the client
  supplies. Photo thumbnails are fetched by key from the cached Civil Air
  Patrol index, only from the CAP image host, and a redirect off that host is
  refused; downloads are capped at 40 MB and 80 megapixels, two at a time.
* **Files are written atomically** (unique temp file in the same directory,
  then rename): caches, thumbnails, response products, label release state.
  Concurrent writers never share a temp file.
* **CSV output cannot carry spreadsheet formulas.** Free text (label notes,
  verifier names, addresses from third-party layers) passes through
  `guard.csv_cell`, which prefixes `'` to text starting with `= + - @`, tab
  or carriage return and leaves numbers alone (OWASP CSV injection guidance).
* **Model weights load without executing code**: `torch.load(weights_only=True)`
  with only numpy scalar types allowed.
* **Audit trail** (`data/audit.log`, JSON lines): area views, briefs,
  address views, labels, Verify judgments and exports, exports, assessments,
  event creation, deletions, photo views, response product views, builds and
  KML downloads, and reference views.
* **No personal tracking.** Groma observes places and assets. It does not
  track people, read licence plates or recognise faces, and outbound
  requests carry a User-Agent naming the project, never a personal contact
  unless an operator sets `NCR_CONTACT`.

## Findings in this review

| Severity | Finding | Status |
|---|---|---|
| Medium | `/ops/coverage` was unauthenticated and fanned out to several upstream catalogs per call (traffic amplification, upstream blocking) | fixed: responder token + upstream rate bucket |
| Medium | Label CSV formula injection through labeler and notes | fixed: `csv_cell`; labeler also sanitised on input |
| Medium | Cache writes from concurrent API threads shared one temp name | fixed: unique temp files; key validation |
| Medium | Response build "one at a time" check ran outside its lock | fixed |
| Medium | Pillow 12.3.0: 24 published advisories | fixed in `requirements.txt` (13.0.0); suite passes on 13.0.0; shared venv upgraded at integration |
| Medium | Building-level `old_fort.geojson` tracked in git and present on the public repo's `main` | open: owner decision (untrack and replace with a synthetic fixture; history stays public unless rewritten) |
| Low/Medium | Verify verifier names and export addresses in CSV | fixed: `csv_cell` |
| Low | Photo thumbnails: concurrent same-key race, unbounded concurrent downloads, no pixel cap, redirects not checked | fixed |
| Low | Lidar county name reached an ArcGIS where-clause with wildcards intact | fixed: whitelist |
| Low | Area list (and evaluation) treated any `*.geojson` in the output folder as an assessment; a sidecar file returned 400 for the whole list | fixed in `api.py` and `evaluate.py` |
| Low | Situation brief: area name unescaped in HTML (sanitised at entry; CSP blocks inline script) | fixed: escaped |
| Low | Third-party model checkpoints unpickled with `weights_only=False` | fixed |
| Low | KML icons over plain HTTP | fixed |
| Low | New responder reads (photos, response products, references) not audited | fixed: view_photos, view_response, view_response_layers, export_response_kml, build_response, view_references |
| Low | `pipeline/data/truth/` not in `.gitignore` | fixed |
| Low | Vite 8.2.2 (dev server, `launch-editor` command execution advisory); Tailwind 3 dev chain (`braces` denial of service) | Vite: bump to 8.3.5 queued at integration; Tailwind 3 accepted until a Tailwind 4 move (build-time only) |
| Accepted | ShakeMap `grid.xml` parsed with the standard library (USGS source; Python 3.13 expat resists entity expansion; no external entities resolved) | accepted |
| Accepted | Responder token stored in the browser's local storage | accepted: CSP forbids injected script; rotate the token if a device is lost |

## Operator checklist

1. Set a long random `TERRATRIAGE_TOKEN` (for example
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`); never
   run `NCR_DEV_OPEN=1` outside a laptop.
2. Serve only through the bundled Caddy proxy (HTTPS and HSTS) with
   `NCR_TRUST_PROXY=1`; keep `CORS_ORIGINS` to the app's own origin.
3. On a shared host, make the data directory private:
   `chmod 700 pipeline/data` (files are created 644 by default), and keep
   backups (`run.py ops-backup`) encrypted at rest.
4. In `docker-compose.yml`, add `security_opt: ["no-new-privileges:true"]`
   to the services and drop the capabilities each one does not need (the
   image already runs as a non-root user; the Caddy proxy still needs
   `NET_BIND_SERVICE` for ports 80 and 443).
5. Rotate the token after any device loss or staff change; the audit log
   records the client address for every responder action.
6. Run `pip-audit -r requirements.txt` and `npm audit --omit=dev` before each
   release (CI does both).
