# Launch checklist

Groma launches free: every feature, self-hosted or as a pilot. This page says
what is ready and what still needs a person.

## Ready

| Area | State |
|---|---|
| Licence | Apache-2.0 (`LICENSE`, `NOTICE`); data terms in `LICENSES.md` |
| Install | `docker compose up -d --build` is a complete install: web app, API, worker, HTTPS (Caddy), both damage models fetched, checked and built in |
| Models | Wildfire model shipped with its held-out Eaton result; general image model converted at build; what is and is not validated is stated in `docs/model/MODEL_CARD.md` and on every product |
| Products | Assess, Verify, Respond, exports (FEMA survey fields, GeoPackage, File Geodatabase, KML, CSV), the state IDA packet, owner records, the public street check and the Groma Index, offline packs (beta) |
| Security | Fail-closed responder token, signed expiring owner links, banded public answers, rate limits, CSP, audit log, dependency audits and SBOMs in CI; `SECURITY.md` |
| Website | `site/`: who it is for, what it does, a live 3D demo, results with their limits, free plans, contact |
| Tests | Pipeline suite, web type-check, lint and build, Docker build in CI |

## Still needs a person

1. **A legal entity with an adult signatory** before any contract, grant,
   SAM.gov registration or paid plan.
2. **Hosting for a public demo** (a domain and a small server) so the site's
   street check and index can link to a live app. Until then the site links
   to GitHub and email.
3. **`NCR_OWNER_SECRET` and `TERRATRIAGE_TOKEN`** set on every server.
4. **Owner verification partners** (a legal aid group or county call centre)
   before sending owner record links: Groma does not check identity itself.
5. **Before any paid plan:** a flood and wind model trained only on
   commercially usable data (the general image model is non-commercial), and
   a scored run of the full pipeline on a new wildfire.
6. **Altadena** stays a held-out test area: retire it formally before using
   it for owner records.
