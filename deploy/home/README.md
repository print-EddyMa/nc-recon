# NC Recon from this computer

The public site, https://ncrecon.netlify.app, is the NC Recon app. Netlify
serves the front end. Every data request (`/ops`, `/areas`, `/assess`,
`/catalog`, `/events`, `/feed`, `/tiles`, `/health`) passes through to the NC
Recon server on this computer by a Cloudflare tunnel. The launch page is at
https://ncrecon.netlify.app/about/.

```
visitor -> ncrecon.netlify.app -> Cloudflare tunnel -> server on this computer (127.0.0.1:8100)
           (front end, CSP)        (adds X-Ncr-Proxy)    (token, rate limits, audit)
```

The site works only while this computer is on, awake and online. When it is
off, the front end still loads, and the app says the assessment service is
unreachable.

## Commands

```sh
deploy/home/live.sh setup    # once: ~/ncrecon-live with a copy of the assessments and new secrets
deploy/home/live.sh start    # server + tunnel + front end
deploy/home/live.sh status
deploy/home/live.sh stop
```

`~/ncrecon-live/.env` holds the secrets. Never commit it or share it:

- `TERRATRIAGE_TOKEN`: the responder token. Paste it into the app under
  Responder access to see building-level data. Anyone with it sees
  building-level data.
- `NCR_OWNER_SECRET`: signs owner-record links.
- `NCR_PROXY_SECRET`: Netlify adds it to every request it passes through. The
  server refuses any request without it, so nobody can use the tunnel address to
  get around the site.

The start script refuses to run without the token and the proxy secret, or with
`NCR_DEV_OPEN=1`.

## Data

This server uses its own copy of the assessments in `~/ncrecon-live/data`. It
never shares a data folder with a development server. It reads raw imagery from
`pipeline/data/raw`. To publish a newer assessment, copy its files from
`pipeline/data/output/ops` into `~/ncrecon-live/data/output/ops`, or run the
assessment through the live site.

## Publishing the front end

A quick tunnel gets a new address each time it starts, so after every `start`
Netlify has to be told the new address:

- With a Netlify personal access token in `NETLIFY_AUTH_TOKEN` (in
  `~/ncrecon-live/.env`), `start` redeploys by itself.
- Without one, deploy `~/ncrecon-live/site` to the Netlify site `ncrecon` by
  hand (`npx netlify-cli deploy --prod --dir dist` from that folder, after
  `netlify login`).

`build_front.py` builds the app the way the Dockerfile does. It leaves out the
same local-only files (imagery tiles, building-level GeoJSON, the pitch demo
and the intro). It writes `netlify.toml` beside the published folder, so the
secret and the tunnel address are never served.

## A fixed address

A free Cloudflare account and a domain give a named tunnel with an address that
never changes. Netlify then needs deploying only when the app changes. For an
always-on host, see `docs/ops/DEPLOYMENT.md`.
