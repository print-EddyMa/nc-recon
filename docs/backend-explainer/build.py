"""Assemble docs/backend.html (the "NC Recon Backend" artifact page) from
template.html + script.js + data.json. Run build_data.py first."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(HERE, "..", "backend.html")
t = open(os.path.join(HERE, "template.html")).read()
d = open(os.path.join(HERE, "data.json")).read().replace("</", "<\\/")
js = open(os.path.join(HERE, "script.js")).read()
html = t.replace("__DATA__", d).replace("__SCRIPT__", js)
open(out, "w").write(html)
print(len(html), "bytes ->", os.path.normpath(out), "| em dashes:", html.count("\u2014"))
