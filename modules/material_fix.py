"""Repath unresolvable image datablocks so no material renders magenta.

Resolution order per broken image:
  1. project textures/<set>/<set>_<map>_<res>.jpg       (canonical local copy)
  2. the original bytes still packed inside the .blend   (extract + repath, no network)
  3. download 2k jpg from textures/_meta/<set>.json
  4. download 2k jpg via api.polyhaven.com/files/<set>
Then the image is packed, so the .blend stays self-contained.

Broken paths look like
  //../../../../../tmp/opencode/ph/<set>/<Diffuse|AO|Rough|nor_gl|Displacement|arm>.jpg

Usage: blender -b out/foo.blend -P modules/material_fix.py -- [--save]
"""
import bpy, os, sys, json, re, urllib.request

ROOT = "/home/abdulhadi/Work/city"
TEX = os.path.join(ROOT, "textures")
META = os.path.join(TEX, "_meta")
DL = "/tmp/opencode/ph"
API = "https://api.polyhaven.com/files/"

# map stem (normalised) -> filename tokens to look for in textures/<set>/
TOKENS = {
    "diffuse": ("diff", "diffuse", "albedo", "basecolor", "col"),
    "diff": ("diff", "diffuse", "albedo", "basecolor", "col"),
    "col": ("col", "diff", "diffuse"),
    "ao": ("ao",),
    "rough": ("rough",),
    "roughness": ("rough",),
    "norgl": ("nor_gl", "nor", "normal", "nrm"),
    "norm": ("nor_gl", "nor", "normal", "nrm"),
    "nordx": ("nor_dx", "nor", "normal", "nrm"),
    "displacement": ("disp", "displacement", "height"),
    "disp": ("disp", "displacement", "height"),
    "arm": ("arm",),
    "metal": ("metal", "metallic"),
    "metallic": ("metal", "metallic"),
    "spec": ("spec", "rough"),
    "opacity": ("opacity", "alpha"),
}

# normalised stem -> PolyHaven metadata key
META_KEY = {
    "diffuse": "Diffuse", "diff": "Diffuse",
    "ao": "AO",
    "rough": "Rough", "roughness": "Rough",
    "norgl": "nor_gl", "nordx": "nor_dx", "normal": "nor_gl", "norm": "nor_gl",
    "displacement": "Displacement", "disp": "Displacement",
    "arm": "arm", "metal": "Metal", "metallic": "Metal",
    "opacity": "Opacity", "spec": "Specular",
}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def textures_index():
    idx = {}
    if not os.path.isdir(TEX):
        return idx
    for d in sorted(os.listdir(TEX)):
        p = os.path.join(TEX, d)
        if not os.path.isdir(p) or d.startswith("_"):
            continue
        files = [f for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))]
        idx[norm(d)] = (d, files)
    return idx


def pick_local(setname, stem, idx):
    key = norm(setname)
    if key not in idx:
        hits = [k for k in idx if k.startswith(key) or key.startswith(k)]
        if not hits:
            return None
        key = min(hits, key=len)
    d, files = idx[key]
    toks = TOKENS.get(norm(stem), (norm(stem),))
    cands = []
    for f in files:
        fl = f.lower()
        for rank, t in enumerate(toks):
            # texture files are <set>_<map>_<res>.<ext>; "_<t>_" keeps 'nor' from
            # matching 'nor_gl' wrongly and 'ao' from matching 'albedo'
            if ("_%s_" % t) in fl or ("_%s." % t) in fl:
                score = (("2k" in fl) * 4, ("jpg" in fl) * 2, -rank)
                cands.append((score, os.path.join(TEX, d, f)))
                break
    if cands:
        cands.sort()
        return cands[-1][1]
    return None


def extract_packed(img, setname, stem):
    """Write the bytes packed in the .blend back out to a real file."""
    pf = img.packed_file
    if not pf:
        return None
    try:
        data = bytes(pf.data)
    except Exception:
        return None
    if len(data) < 1024:
        return None
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
    d = os.path.join(DL, setname)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "packed_%s%s" % (stem, ext))
    if not os.path.exists(out):
        with open(out, "wb") as f:
            f.write(data)
    return out


def _file_data(setname, stem, data):
    k = META_KEY.get(norm(stem))
    if not k or k not in data:
        return None
    try:
        url = data[k]["2k"]["jpg"]["url"]
    except Exception:
        return None
    os.makedirs(os.path.join(DL, setname), exist_ok=True)
    out = os.path.join(DL, setname, os.path.basename(url))
    if os.path.exists(out) and os.path.getsize(out) > 1024:
        return out
    req = urllib.request.Request(url, headers={"User-Agent": "citykit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r, open(out, "wb") as f:
        f.write(r.read())
    return out


def download_map(setname, stem):
    """Fetch 2k jpg: local metadata first, then the PolyHaven API."""
    data = None
    mp = os.path.join(META, setname + ".json")
    if os.path.exists(mp):
        try:
            data = json.load(open(mp))
        except Exception:
            data = None
    if data:
        try:
            got = _file_data(setname, stem, data)
            if got:
                return got
        except Exception:
            pass
    if setname:
        try:
            req = urllib.request.Request(API + setname, headers={"User-Agent": "citykit/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            return _file_data(setname, stem, data)
        except Exception:
            pass
    return None


def main():
    save = "--save" in sys.argv
    idx = textures_index()
    total = missing = fixed_local = fixed_dl = fixed_packed = 0
    still = []
    for img in list(bpy.data.images):
        if img.source != 'FILE':
            continue
        total += 1
        fp = (img.filepath or "").strip()
        p = bpy.path.abspath(fp) if fp else ""
        if p and os.path.exists(p):
            if not img.packed_file:
                img.pack()
            continue
        missing += 1
        parts = fp.replace("\\", "/").split("/")
        stem = os.path.splitext(parts[-1])[0] if parts[-1] else "unknown"
        setname = parts[-2] if len(parts) >= 2 else "unknown"
        try:
            found = pick_local(setname, stem, idx)
            if found:
                fixed_local += 1
            else:
                found = extract_packed(img, setname, stem)
                if found:
                    fixed_packed += 1
                else:
                    found = download_map(setname, stem)
                    if found:
                        fixed_dl += 1
        except Exception as e:
            print("###ERR", setname, stem, e)
            found = None
        if found:
            img.filepath = found
            try:
                img.reload()
            except Exception:
                pass
            if not img.packed_file:
                try:
                    img.pack()
                except Exception:
                    pass
        else:
            still.append("%s/%s" % (setname, stem))
    print("###RESULT", json.dumps({
        "file": bpy.data.filepath, "images": total, "missing_before": missing,
        "fixed_local": fixed_local, "fixed_packed": fixed_packed,
        "fixed_download": fixed_dl, "still_missing": len(still),
        "unresolved": still,
    }))
    if save:
        bpy.ops.wm.save_mainfile()
        print("###SAVED", bpy.data.filepath)


main()
