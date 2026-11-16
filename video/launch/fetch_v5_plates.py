"""Public-domain natural history plates of Southern Appalachian species, from Wikimedia Commons.

Keeps only files whose Commons licence says public domain. Writes assets/v5/plates_pd/ and meta.json.
"""
import json, os, re, time, urllib.error, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets", "v5", "plates_pd")
UA = {"User-Agent": "NCReconFilm/1.0 (open source film credits)"}
QUERIES = {
    "bear": "Audubon black bear plate",
    "trout": "Salvelinus fontinalis brook trout illustration",
    "luna": "Actias luna moth plate illustration 18th century",
    "rhododendron": "Rhododendron botanical magazine plate",
    "hellbender": "Hellbender Cryptobranchus illustration",
    "swallowtail": "Papilio turnus plate butterfly illustration",
    "turtle": "Box turtle Holbrook plate",
    "fox": "Audubon red fox Quadrupeds",
    "trillium": "Trillium Botanical Magazine plate",
    "owl": "Audubon Barred Owl",
    "woodpecker": "Audubon Pileated Woodpecker",
    "turkey": "Audubon Wild Turkey plate 1",
}
def get(params):
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    for wait in (0, 20, 60, 120):
        time.sleep(wait)
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    return {}
M = os.path.join(OUT, "meta.json")
meta = json.load(open(M)) if os.path.exists(M) else {}
for name, q in QUERIES.items():
    if name in meta:
        continue
    r = get({"action": "query", "format": "json", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 8,
             "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1400})
    pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    got = False
    for p in pages:
        ii = p["imageinfo"][0]; md = ii.get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        if "public domain" not in lic.lower() and not lic.lower().startswith("pd"):
            continue
        if ii.get("width", 0) < 700 or ii.get("height", 0) < 700:
            continue
        url = ii.get("thumburl") or ii["url"]
        path = os.path.join(OUT, name + ".jpg")
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e:
            print(name, "failed", e); time.sleep(20); continue
        open(path, "wb").write(data)
        meta[name] = {"title": p["title"], "licence": lic, "page": ii.get("descriptionurl"), "artist": re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", ""))[:100]}
        print(name, "->", p["title"][:70], "|", lic); got = True
        break
    if not got:
        print(name, "NONE")
    json.dump(meta, open(M, "w"), indent=1)
    time.sleep(6)
