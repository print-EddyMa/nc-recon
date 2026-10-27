# Security

Groma handles building-level damage calls and street addresses after a
disaster, which can be misused (for example, to find empty homes). Please
report anything that could expose them.

## Reporting a vulnerability

Email **ma.eddy.work@gmail.com** with "Groma security" in the subject. Do not
open a public issue. Include what you found, how to reproduce it and what it
exposes. You will get a reply within 7 days, and a fix or a plan within 30.

## What protects the data today

* Building-level data and addresses are behind a responder token that fails
  closed (`TERRATRIAGE_TOKEN`); the server refuses to listen beyond
  localhost without one.
* Owner records are private links, signed (`NCR_OWNER_SECRET`), expiring and
  revocable; the token travels in a URL fragment and a POST body, never a
  query string.
* Public pages show only banded, area-level answers; counts below 5 are
  withheld; TEST areas never answer building-level questions.
* Per-client rate limits, a strict Content Security Policy, an append-only
  audit log of responder actions, and dependency audits and SBOMs in CI.

Details: [`docs/ops/SECURITY.md`](docs/ops/SECURITY.md) and
[`docs/ops/DEPLOYMENT.md`](docs/ops/DEPLOYMENT.md).
