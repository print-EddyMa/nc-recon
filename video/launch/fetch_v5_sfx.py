"""CC0 sound effects for the hype cut, found through Openverse (Freesound previews).

Only CC0 results are kept. Writes assets/v5/sfx/<slot>_<n>.mp3 and sfx.json for the credits.
"""
import json, os, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets", "v5", "sfx")
UA = {"User-Agent": "NCReconFilm/1.0"}
SLOTS = {
    "impact": ("cinematic impact boom", 3), "sub": ("sub drop bass", 3), "braam": ("trailer braam horn", 3),
    "whoosh": ("whoosh transition fast", 5), "riser": ("riser tension build cinematic", 3), "reverse": ("reverse cymbal", 2),
    "tapestop": ("tape stop", 2), "wind": ("hurricane wind storm", 2), "rain": ("heavy rain storm", 2), "river": ("flood river rushing water", 2),
    "thunder": ("thunder crack close", 2), "helicopter": ("helicopter flyby", 2), "chainsaw": ("chainsaw cutting", 1), "debris": ("wood debris crash", 2),
    "radio": ("radio static squelch", 2), "shutter": ("camera shutter click", 2), "paper": ("paper flip page", 3), "stamp": ("rubber stamp", 2),
    "click": ("ui click mechanical", 2), "typewriter": ("typewriter key", 2), "scan": ("scanner beep sweep", 2), "glitch": ("digital glitch", 2),
    "kick": ("808 kick one shot", 3), "snare": ("trap snare one shot", 3), "clap": ("clap one shot", 2), "hat": ("closed hi hat one shot", 3), "bass808": ("808 bass one shot", 3),
    "heartbeat": ("heartbeat", 1), "bell": ("church bell single", 1),
}
meta = {}
for slot, (q, n) in SLOTS.items():
    u = "https://api.openverse.org/v1/audio/?" + urllib.parse.urlencode({"q": q, "license": "cc0", "page_size": 20, "source": "freesound"})
    try:
        rs = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30)).get("results", [])
    except Exception as e:
        print(slot, "failed", e); time.sleep(10); continue
    rs = [r for r in rs if r.get("license") == "cc0" and (r.get("duration") or 0) < 30000]
    got = 0
    for r in rs:
        if got == n:
            break
        path = os.path.join(OUT, f"{slot}_{got}.mp3")
        try:
            open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(r["url"], headers=UA), timeout=30).read())
        except Exception as e:
            continue
        meta[f"{slot}_{got}"] = {"title": r.get("title"), "creator": r.get("creator"), "license": r.get("license"), "page": r.get("foreign_landing_url"), "ms": r.get("duration")}
        got += 1
    print(slot, got, [meta.get(f"{slot}_{i}", {}).get("title") for i in range(got)])
    time.sleep(1.5)
json.dump(meta, open(os.path.join(OUT, "sfx.json"), "w"), indent=1)
