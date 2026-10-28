#!/usr/bin/env python3
"""Fill the <!--MATERIAL_TABLE:<category>--> markers in style_bible.md from
materials_index.json.  The bible tables are GENERATED so names can never drift
from the blend.  Run after materials.py; edit materials.py, not the tables."""
import json
import os
import re

CITY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIBLE = os.path.join(CITY, "style_bible.md")
INDEX = os.path.join(CITY, "materials_index.json")

with open(INDEX) as f:
    data = json.load(f)
mats = data["materials"]


def row(name, m):
    src = m.get("source", "")
    short = src.replace("polyhaven:", "PH ").replace("procedural", "proc.")
    return "| `%s` | %s | %.2f | %.2f | %s | %s | %s |" % (
        name,
        m["base_color"],
        m["roughness"],
        m["metalness"],
        ("%.2f m" % m["tile_scale_m"]) if m["tile_scale_m"] else "—",
        "yes" if m["emissive"] else "",
        short or "—",
    )


HEADER = ("| material | base colour | rough | metal | tile | emit | source |\n"
          "|---|---|---|---|---|---|---|")

with open(BIBLE) as f:
    text = f.read()


def fill(match):
    cat = match.group(1)
    names = [n for n, m in mats.items() if m["category"] == cat]
    if not names:
        raise SystemExit("no materials in category %r" % cat)
    body = "\n".join([HEADER] + [row(n, mats[n]) for n in names])
    return "<!--MATERIAL_TABLE:%s-->\n\n%s\n" % (cat, body)


# match the marker plus any table(s) already generated under it (possibly
# duplicated by older runs), so re-runs are idempotent, never stacking tables
pat = (r"<!--MATERIAL_TABLE:([a-z_]+)-->[ \t]*\n"
       r"(?:(?:[ \t]*\n)?(?:\|.*\n)+)+")
text, n = re.subn(pat, fill, text)
# keep the count line in sync on every run ("**93 materials + 2 node groups.**")
text, n2 = re.subn(r"\d+ materials \+ 2 node groups",
                   "%d materials + 2 node groups" % len(mats), text)
if n2 != 1:
    print("WARNING: material-count line matched %d times" % n2)
with open(BIBLE, "w") as f:
    f.write(text)
print("filled %d tables; %d materials total" % (n, len(mats)))
