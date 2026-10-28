#!/usr/bin/env python3
"""
materials.py -- Agent 0 (Style Bible + Materials) for the AAA 3x3 km city build.

Builds:
  /city/materials.blend              PBR material library (packed images + 2 node groups)
  /city/materials_index.json         machine readable index
  /city/out/materials_preview.png    1920x1080 day render of the library

Run headless:
  blender -b -P /city/modules/materials.py

DESIGN NOTES (every other agent must know this):
  * Every material samples TEXCOORD 'Object' through a Mapping node whose scale
    is (1 / tile_scale_m).  Object space == metres (transforms are applied per
    the contract) => texel density is AUTOMATIC and identical city-wide and NO
    mesh needs a UV map.
  * Image textures use projection = BOX (blend 0.12), so walls, floors and
    rotated objects all get correct, non-stretched texturing.
  * Height detail comes from a Bump node fed by the source displacement map.
    Bump works screen-space, so unlike the Normal Map node it needs no UVs.
  * Pointiness / Bevel / AO nodes are Cycles-only (EEVEE 5.2 returns a constant
    0.5 for pointiness), so NG_EdgeWear_Dirt mixes a pointiness term (Cycles)
    with noise + up-facing terms (works in both engines).
"""

import bpy
import os
import sys
import json
import math
import time
import urllib.request
import urllib.error
import traceback
from collections import OrderedDict

try:
    import numpy as np
except Exception:
    np = None

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CITY = os.path.dirname(SCRIPT_DIR)
if os.path.basename(CITY) != "city":
    CITY = "/home/abdulhadi/Work/city"

TEX_DIR = os.path.join(CITY, "textures")
META_DIR = os.path.join(TEX_DIR, "_meta")
BLEND_PATH = os.path.join(CITY, "materials.blend")
INDEX_PATH = os.path.join(CITY, "materials_index.json")
PREVIEW_PATH = os.path.join(CITY, "out", "materials_preview.png")

API_FILES = "https://api.polyhaven.com/files/"
UA = {"User-Agent": "Mozilla/5.0 (city-build; agent0)"}

os.makedirs(TEX_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)

FAILURES = []


def log(*a):
    print("[materials]", *a, flush=True)


# ---------------------------------------------------------------------------
# colour helpers
# ---------------------------------------------------------------------------
def hex_to_linear(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def linear_to_hex(rgb):
    out = []
    for c in rgb:
        c = max(0.0, min(1.0, float(c)))
        s = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
        out.append(int(round(max(0.0, min(1.0, s)) * 255)))
    return "#%02X%02X%02X" % tuple(out)


# ---------------------------------------------------------------------------
# PALETTE -- the ONLY colours allowed on facades / signage / awnings / vehicles
# ---------------------------------------------------------------------------
PALETTE = OrderedDict([
    ("bone",       "#E9E3D7"),
    ("sand",       "#D4BD99"),
    ("terracotta", "#B0603C"),
    ("oxblood",    "#8E2F2B"),
    ("mustard",    "#D9A41F"),
    ("sage",       "#7F9070"),
    ("teal",       "#2E7C74"),
    ("navy",       "#263B5C"),
    ("charcoal",   "#34373D"),
    ("stone",      "#9B968D"),
    ("magenta",    "#D9447F"),
    ("violet",     "#7A4FB6"),
])

# ---------------------------------------------------------------------------
# PolyHaven texture sets.  2K only for hero surfaces (asphalt / concrete /
# brick), 1K everywhere else.  value = requested resolution.
# ---------------------------------------------------------------------------
TEXSETS = {
    # --- roads / ground ---
    "clean_asphalt":          "2k",   # road_asphalt_new
    "asphalt_01":             "2k",   # road_asphalt_worn
    "concrete_pavement_02":   "1k",   # sidewalk_paving
    "cobblestone_floor_04":   "1k",   # road_cobble
    # --- facades ---
    "concrete_wall_008":      "2k",   # facade_concrete, road_curb_concrete
    "concrete_wall_003":      "1k",   # facade_concrete_weathered
    "concrete_slab_wall":     "1k",   # facade_concrete_slab
    "white_stucco":           "1k",   # facade_stucco
    "plastered_wall_02":      "1k",   # facade_plaster_<all 12 palette colours>
    "worn_cracked_plaster":   "1k",   # facade_plaster_weathered
    "brick_wall_001":         "2k",   # facade_brick_red, facade_brick_painted
    "painted_metal_shutter":  "1k",   # facade_metal_panel (+ weathered)
    "weathered_brown_planks": "1k",   # facade_timber_cladding
    # --- metal / wood ---
    "metal_plate":            "1k",   # metal_checker_plate
    "rusty_painted_metal":    "1k",   # metal_rust
    "wood_planks":            "1k",   # wood_planks
    "weathered_planks":       "1k",   # wood_planks_weathered
    # --- roofs ---
    "clay_roof_tiles":        "1k",   # roof_clay_tile
    "corrugated_iron":        "1k",   # roof_corrugated_metal
    "bitumen":                "1k",   # roof_bitumen_flat
    # --- nature ---
    "grass_ground":           "1k",   # nature_grass
    "sparse_grass":           "1k",   # nature_wild_grass
    "bark_brown_01":          "1k",   # nature_bark
    "farm_soil":              "1k",   # nature_dirt
    "gravel_floor":           "1k",   # nature_gravel
    # --- interiors ---
    "wood_floor":             "1k",   # int_wood_floor
    "interior_tiles":         "1k",   # int_tile_floor
    "laminate_floor_02":      "1k",   # int_laminate_counter
}

# ---------------------------------------------------------------------------
# PolyHaven resolution (two API schemas exist: modern 'blend' pack layout and
# the older per-map layout {'Diffuse': {'1k': {'jpg': {...}}}})
# ---------------------------------------------------------------------------
MAP_PATTERNS = {
    "diff":  ["diff", "albedo", "color", "diffuse", "basecolor"],
    "rough": ["rough", "roughness"],
    "disp":  ["disp", "displacement", "height"],
}
OLD_KEY_ALIASES = {
    "diff":  ["diffuse", "diff", "color", "albedo", "basecolor"],
    "rough": ["rough", "roughness"],
    "disp":  ["displacement", "disp", "height"],
}
RES_ORDER = ["2k", "4k", "1k", "8k"]
_files_cache = {}
_img_cache = {}
_img_stats = {}


def ph_files(asset):
    if asset in _files_cache:
        return _files_cache[asset]
    path = os.path.join(META_DIR, asset + ".json")
    if not os.path.exists(path):
        url = API_FILES + asset
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "r") as f:
        d = json.load(f)
    _files_cache[asset] = d
    return d


def _res_order(res_pref):
    out = [res_pref] + [r for r in RES_ORDER if r != res_pref]
    return out


def find_map(asset, kind, res_pref):
    """-> (resolution, url) or (None, None)"""
    try:
        f = ph_files(asset)
    except Exception as e:
        log("files API failed", asset, e)
        return None, None
    pats = MAP_PATTERNS[kind]

    # --- modern schema -------------------------------------------------
    blend = f.get("blend")
    if isinstance(blend, dict) and any(r in blend for r in ("1k", "2k", "4k")):
        for res in _res_order(res_pref):
            entry = blend.get(res)
            if not isinstance(entry, dict):
                continue
            texs = entry.get("include", {}).get("textures", {})
            for fname, meta in texs.items():
                base = os.path.basename(fname).lower()
                if not any("_%s_" % p in base for p in pats):
                    continue
                url = meta.get("url") if isinstance(meta, dict) else None
                if url:
                    return res, url
        # fall back to AO/rough packed 'arm' for roughness
        if kind == "rough":
            for res in _res_order(res_pref):
                texs = blend.get(res, {}).get("include", {}).get("textures", {})
                for fname, meta in texs.items():
                    if "_arm_" in os.path.basename(fname).lower():
                        return res, meta["url"]

    # --- legacy schema -------------------------------------------------
    lowered = {}
    for k, v in f.items():
        if isinstance(v, dict):
            lowered[k.lower()] = (k, v)
    for alias in OLD_KEY_ALIASES[kind]:
        hit = lowered.get(alias)
        if not hit:
            continue
        key, v = hit
        if kind == "disp":
            fmts = ["png", "exr", "jpg"]
        else:
            fmts = ["jpg", "png", "exr"]
        for res in _res_order(res_pref):
            rv = v.get(res)
            if not isinstance(rv, dict):
                continue
            for fmt in fmts:
                m = rv.get(fmt)
                if isinstance(m, dict) and m.get("url"):
                    return res, m["url"]
    return None, None


def download(url, dest, tries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 2048:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    f.write(chunk)
            if os.path.getsize(tmp) < 2048:
                raise IOError("file too small")
            os.replace(tmp, dest)
            return dest
        except Exception as e:
            log("  download try %d failed %s :: %s" % (i + 1, url, e))
            time.sleep(1.5)
    if os.path.exists(tmp):
        os.remove(tmp)
    return None


def load_map(asset, kind, res_pref, non_color):
    """download + load one map; shared datablock per (asset,kind,res)."""
    key = (asset, kind, res_pref, non_color)
    if key in _img_cache:
        return _img_cache[key]
    res, url = find_map(asset, kind, res_pref)
    if not url:
        log("MISSING MAP", asset, kind)
        _img_cache[key] = None
        return None
    dest = os.path.join(TEX_DIR, asset, os.path.basename(url.split("?")[0]))
    path = download(url, dest)
    if not path:
        _img_cache[key] = None
        return None
    img = bpy.data.images.load(path, check_existing=True)
    img.name = "%s_%s_%s" % (asset, kind, res)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    _img_cache[key] = img
    log("  loaded %-24s %-5s %s %s" % (asset, res, kind, os.path.basename(path)))
    return img


def img_mean_linear(img):
    """mean linear RGB of an image (float4 pixels)"""
    if img.name in _img_stats:
        return _img_stats[img.name]
    if np is None:
        _img_stats[img.name] = (0.5, 0.5, 0.5)
        return (0.5, 0.5, 0.5)
    n = img.size[0] * img.size[1]
    if n <= 0:
        _img_stats[img.name] = (0.5, 0.5, 0.5)
        return (0.5, 0.5, 0.5)
    buf = np.empty(n * 4, dtype=np.float32)
    try:
        img.pixels.foreach_get(buf)
    except Exception:
        _img_stats[img.name] = (0.5, 0.5, 0.5)
        return (0.5, 0.5, 0.5)
    px = buf.reshape(-1, 4)
    m = [float(px[:, 0].mean()), float(px[:, 1].mean()), float(px[:, 2].mean())]
    _img_stats[img.name] = tuple(m)
    return tuple(m)

# ---------------------------------------------------------------------------
# node helpers
# ---------------------------------------------------------------------------
def new_mat(name):
    if name in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[name])
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    return m, nt, bsdf


def coord_mapping(nt, tile, source="Object"):
    """TexCoord(source) -> Mapping(scale = 1/tile).  tile in metres."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    s = 1.0 / float(tile)
    mp.inputs["Scale"].default_value = (s, s, s)
    nt.links.new(tc.outputs[source], mp.inputs["Vector"])
    return mp.outputs["Vector"]


def img_node(nt, img, tile, blend=0.12, non_color=False, source="Object"):
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    else:
        img.colorspace_settings.name = "sRGB"
    vec = coord_mapping(nt, tile, source)
    it = nt.nodes.new("ShaderNodeTexImage")
    it.image = img
    it.projection = "BOX"
    it.projection_blend = blend
    it.extension = "REPEAT"
    nt.links.new(vec, it.inputs["Vector"])
    return it


def noise_vec(nt, tile, source="Object"):
    return coord_mapping(nt, tile, source)


def add_bump(nt, height_socket, strength=0.4, distance=0.03):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height_socket, b.inputs["Height"])
    return b.outputs["Normal"]


def mix_rgba(nt, a_sock, b_sock, fac_sock=None, blend="MIX", fac=1.0):
    """ShaderNodeMix in RGBA mode, sockets found by enabled+type (version safe)."""
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    n.blend_type = blend
    ins = [s for s in n.inputs if s.enabled]
    cols = [s for s in ins if s.type == "RGBA"]
    vals = [s for s in ins if s.type == "VALUE"]
    outs = [s for s in n.outputs if s.type == "RGBA"]
    if a_sock is not None:
        nt.links.new(a_sock, cols[0])
    if b_sock is not None:
        nt.links.new(b_sock, cols[1])
    if fac_sock is not None:
        nt.links.new(fac_sock, vals[0])
    else:
        vals[0].default_value = fac
    return outs[0]


def const_col(nt, rgba):
    n = nt.nodes.new("ShaderNodeRGB")
    n.outputs[0].default_value = rgba
    return n.outputs[0]


def const_val(nt, v):
    n = nt.nodes.new("ShaderNodeValue")
    n.outputs[0].default_value = v
    return n.outputs[0]


def hue_sat(nt, color_sock, hue=0.5, sat=1.0, val=1.0):
    n = nt.nodes.new("ShaderNodeHueSaturation")
    n.inputs["Hue"].default_value = hue
    n.inputs["Saturation"].default_value = sat
    n.inputs["Value"].default_value = val
    nt.links.new(color_sock, n.inputs["Color"])
    return n.outputs["Color"]


def math_nt(nt, op, a, b=None, clamp=False, b_val=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if isinstance(a, (int, float)):
        n.inputs[0].default_value = a
    else:
        nt.links.new(a, n.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            n.inputs[1].default_value = b
        else:
            nt.links.new(b, n.inputs[1])
    elif b_val is not None:
        n.inputs[1].default_value = b_val
    return n.outputs[0]


def ramp(nt, stops, in_sock):
    """stops = [(pos, (r,g,b,a)), ...] sorted"""
    n = nt.nodes.new("ShaderNodeValToRGB")
    cr = n.color_ramp
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = stops[0][0]
    cr.elements[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = cr.elements.new(pos)
        e.color = col
    nt.links.new(in_sock, n.inputs["Fac"])
    return n.outputs["Color"]


def set_emit(bsdf, hexcol, strength):
    lin = hex_to_linear(hexcol)
    bsdf.inputs["Emission Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
    bsdf.inputs["Emission Strength"].default_value = strength


def set_alpha_mat(mat, alpha):
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Alpha"].default_value = alpha
    try:
        mat.surface_render_method = "BLENDED"
    except Exception:
        pass
    try:
        mat.blend_method = "BLEND"
    except Exception:
        pass
    try:
        mat.use_transparent_shadow = True
    except Exception:
        pass


# ---------------------------------------------------------------------------
# shared node groups
# ---------------------------------------------------------------------------
def build_node_groups():
    # ---------------- NG_ColorVariation ----------------
    ng = bpy.data.node_groups.new("NG_ColorVariation", "ShaderNodeTree")
    ng.use_fake_user = True
    iface = ng.interface
    s = iface.new_socket("Base Color", in_out="INPUT", socket_type="NodeSocketColor")
    s.default_value = (0.5, 0.5, 0.5, 1.0)
    s.description = "Your palette colour (sRGB-linear), before variation."
    s = iface.new_socket("Variation", in_out="INPUT", socket_type="NodeSocketFloat")
    s.min_value = 0.0
    s.max_value = 0.5
    s.default_value = 0.12
    s.description = "0 = none, 0.12 = subtle (default), 0.35 = strong."
    s = iface.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketFloat")
    s.min_value = 0.0
    s.max_value = 10.0
    s.default_value = 0.0
    s.description = "Adds a per-object offset on top of Object Info > Random."
    s = iface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    s.description = "Varied colour, hue-safe (palette stays valid)."

    gin = ng.nodes.new("NodeGroupInput")
    gout = ng.nodes.new("NodeGroupOutput")
    oi = ng.nodes.new("ShaderNodeObjectInfo")

    r1 = math_nt(ng, "MULTIPLY", oi.outputs["Random"], 97.13)
    r2 = math_nt(ng, "ADD", r1, gin.outputs["Seed"])
    r3 = math_nt(ng, "FRACT", r2)                                  # rnd A 0..1
    r4 = math_nt(ng, "MULTIPLY", r3, 137.71)
    r5 = math_nt(ng, "FRACT", r4)                                  # rnd B 0..1

    # value scale = 1 + (rndA - 0.5) * 2 * Variation
    d = math_nt(ng, "SUBTRACT", r3, 0.5)
    v = math_nt(ng, "MULTIPLY", d, gin.outputs["Variation"])
    v2 = math_nt(ng, "MULTIPLY", v, 2.0)
    val = math_nt(ng, "ADD", v2, 1.0)
    # saturation scale = 1 + (rndB - 0.5) * Variation
    d2 = math_nt(ng, "SUBTRACT", r5, 0.5)
    s2 = math_nt(ng, "MULTIPLY", d2, gin.outputs["Variation"])
    sat = math_nt(ng, "ADD", s2, 1.0)
    # hue = 0.5 + (rndB - 0.5) * 0.02  (max +-3.6 deg, palette safe)
    d3 = math_nt(ng, "SUBTRACT", r5, 0.5)
    h = math_nt(ng, "MULTIPLY", d3, 0.02)
    hue = math_nt(ng, "ADD", h, 0.5)

    hs = ng.nodes.new("ShaderNodeHueSaturation")
    ng.links.new(hue, hs.inputs["Hue"])
    ng.links.new(sat, hs.inputs["Saturation"])
    ng.links.new(val, hs.inputs["Value"])
    ng.links.new(gin.outputs["Base Color"], hs.inputs["Color"])
    ng.links.new(hs.outputs["Color"], gout.inputs["Color"])
    log("built NG_ColorVariation")

    # ---------------- NG_EdgeWear_Dirt ----------------
    ng = bpy.data.node_groups.new("NG_EdgeWear_Dirt", "ShaderNodeTree")
    ng.use_fake_user = True
    iface = ng.interface
    s = iface.new_socket("Base Color", in_out="INPUT", socket_type="NodeSocketColor")
    s.default_value = (0.5, 0.5, 0.5, 1.0)
    s.description = "Albedo (image output or palette colour)."
    s = iface.new_socket("Roughness", in_out="INPUT", socket_type="NodeSocketFloat")
    s.min_value = 0.0
    s.max_value = 1.0
    s.default_value = 0.7
    s.description = "Nominal roughness, dirt raises it, wear lowers it."
    s = iface.new_socket("Wear", in_out="INPUT", socket_type="NodeSocketFloat")
    s.min_value = 0.0
    s.max_value = 1.0
    s.default_value = 0.35
    s.description = "Edge wear / sun-bleach amount. Cycles: pointiness driven. EEVEE: noise driven."
    s = iface.new_socket("Dirt", in_out="INPUT", socket_type="NodeSocketFloat")
    s.min_value = 0.0
    s.max_value = 1.0
    s.default_value = 0.4
    s.description = "Grime amount. 0.3 outdoors, 0.5 market, 0.6 industrial."
    s = iface.new_socket("Dirt Color", in_out="INPUT", socket_type="NodeSocketColor")
    s.default_value = (0.045, 0.040, 0.034, 1.0)
    s.description = "Grime colour (warm near-black)."
    s = iface.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat")
    s.min_value = 0.25
    s.max_value = 32.0
    s.default_value = 2.0
    s.description = "Object-space size in metres of one dirt feature."
    s = iface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    s = iface.new_socket("Roughness", in_out="OUTPUT", socket_type="NodeSocketFloat")

    gin = ng.nodes.new("NodeGroupInput")
    gout = ng.nodes.new("NodeGroupOutput")

    tc = ng.nodes.new("ShaderNodeTexCoord")
    inv = math_nt(ng, "DIVIDE", 1.0, gin.outputs["Scale"])
    cx = ng.nodes.new("ShaderNodeCombineXYZ")
    ng.links.new(inv, cx.inputs["X"])
    ng.links.new(inv, cx.inputs["Y"])
    ng.links.new(inv, cx.inputs["Z"])
    mp = ng.nodes.new("ShaderNodeMapping")
    ng.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    ng.links.new(cx.outputs["Vector"], mp.inputs["Scale"])

    # large dirt patches
    n1 = ng.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 4.0
    n1.inputs["Detail"].default_value = 7.0
    n1.inputs["Roughness"].default_value = 0.65
    ng.links.new(mp.outputs["Vector"], n1.inputs["Vector"])
    patch = ramp(ng, [(0.38, (0, 0, 0, 1)), (0.72, (1, 1, 1, 1))], n1.outputs["Fac"])

    # up-facing bias (world normal Z): dust settles on top surfaces
    geo = ng.nodes.new("ShaderNodeNewGeometry")
    sep = ng.nodes.new("ShaderNodeSeparateXYZ")
    ng.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    up = ng.nodes.new("ShaderNodeMapRange")
    up.inputs["From Min"].default_value = -0.4
    up.inputs["From Max"].default_value = 1.0
    up.inputs["To Min"].default_value = 0.35
    up.inputs["To Max"].default_value = 1.0
    ng.links.new(sep.outputs["Z"], up.inputs["Value"])
    d1 = math_nt(ng, "MULTIPLY", patch, up.outputs["Result"])
    dirt_mask = math_nt(ng, "MULTIPLY", d1, gin.outputs["Dirt"], clamp=True)

    # pointiness (Cycles) -- constant 0.5 in EEVEE => contributes 0 there
    pr = ramp(ng, [(0.52, (0, 0, 0, 1)), (0.66, (1, 1, 1, 1))], geo.outputs["Pointiness"])
    # fine noise scuffing (both engines)
    n2 = ng.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 34.0
    n2.inputs["Detail"].default_value = 5.0
    ng.links.new(mp.outputs["Vector"], n2.inputs["Vector"])
    nz = ramp(ng, [(0.56, (0, 0, 0, 1)), (0.74, (1, 1, 1, 1))], n2.outputs["Fac"])
    nz = math_nt(ng, "MULTIPLY", nz, 0.75)
    wmax = math_nt(ng, "MAXIMUM", pr, nz)
    wear_mask = math_nt(ng, "MULTIPLY", wmax, gin.outputs["Wear"], clamp=True)

    # colour: base -> worn (bleached) -> dirty
    bleached = hue_sat(ng, gin.outputs["Base Color"], 0.5, 0.55, 1.45)
    c1 = mix_rgba(ng, gin.outputs["Base Color"], bleached, fac_sock=wear_mask)
    c2 = mix_rgba(ng, c1, gin.outputs["Dirt Color"], fac_sock=dirt_mask)
    ng.links.new(c2, gout.inputs["Color"])

    # roughness: +dirt, -wear
    r_add = math_nt(ng, "MULTIPLY", dirt_mask, 0.20)
    r_sub = math_nt(ng, "MULTIPLY", wear_mask, 0.10)
    r1 = math_nt(ng, "ADD", gin.outputs["Roughness"], r_add)
    r2 = math_nt(ng, "SUBTRACT", r1, r_sub, clamp=True)
    ng.links.new(r2, gout.inputs["Roughness"])
    log("built NG_EdgeWear_Dirt")

# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------
INDEX = OrderedDict()


def register(mat, cat, spec, base_rgb, rough, metal, emissive=False, source="procedural"):
    # library materials are referenced by nothing in this file; without a fake
    # user Blender drops them (zero-user purge) on save.
    mat.use_fake_user = True
    INDEX[mat.name] = OrderedDict([
        ("base_color", linear_to_hex(base_rgb)),
        ("base_color_rgb", [round(float(c), 4) for c in base_rgb]),
        ("roughness", round(float(rough), 3)),
        ("metalness", round(float(metal), 3)),
        ("tile_scale_m", round(float(spec.get("tile", 1.0)), 3)),
        ("category", cat),
        ("emissive", bool(emissive)),
        ("source", source),
        ("description", spec.get("desc", "")),
    ])
    return mat


def _noise_bump(nt, vec, tile, feat, strength, distance, detail=6.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = float(tile) / float(feat)
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = 0.55
    nt.links.new(vec, n.inputs["Vector"])
    return add_bump(nt, n.outputs["Fac"], strength, distance), n


def _weave_bump(nt, vec, tile, pitch, strength, distance):
    """crossed wave textures = woven cloth"""
    outs = []
    for direction in ("X", "Y"):
        w = nt.nodes.new("ShaderNodeTexWave")
        try:
            w.wave_type = "BANDS"
            w.bands_direction = direction
        except Exception:
            pass
        w.inputs["Scale"].default_value = float(tile) / float(pitch)
        w.inputs["Distortion"].default_value = 1.5
        w.inputs["Detail"].default_value = 2.0
        nt.links.new(vec, w.inputs["Vector"])
        outs.append(w.outputs["Fac"])
    comb = math_nt(nt, "MULTIPLY", outs[0], outs[1])
    return add_bump(nt, comb, strength, distance)


def _apply_common(bsdf, mat, spec):
    if spec.get("sheen"):
        try:
            bsdf.inputs["Sheen Weight"].default_value = spec["sheen"]
        except Exception:
            pass
    if spec.get("coat"):
        try:
            bsdf.inputs["Coat Weight"].default_value = spec["coat"]
            bsdf.inputs["Coat Roughness"].default_value = spec.get("coat_rough", 0.05)
        except Exception:
            pass
    if spec.get("alpha") is not None:
        set_alpha_mat(mat, spec["alpha"])
    if spec.get("emit"):
        set_emit(bsdf, spec["emit"], spec.get("emit_strength", 5.0))


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def b_solid(spec):
    """constant colour + optional procedural relief / weave / mottling"""
    cat = spec["cat"]
    lin = hex_to_linear(spec["color"])
    m, nt, bsdf = new_mat(spec["name"])
    vec = coord_mapping(nt, spec.get("tile", 1.0))
    colour = const_col(nt, (lin[0], lin[1], lin[2], 1.0))

    if spec.get("mottle"):
        feat, amt = spec["mottle"]
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = spec.get("tile", 1.0) / feat
        n.inputs["Detail"].default_value = 7.0
        nt.links.new(vec, n.inputs["Vector"])
        r = ramp(nt, [(0.35, (0, 0, 0, 1)), (0.68, (1, 1, 1, 1))], n.outputs["Fac"])
        dark = hue_sat(nt, colour, 0.5, 1.1, 1.0 - amt)
        colour = mix_rgba(nt, colour, dark, fac_sock=r)

    if spec.get("weave"):
        normal = _weave_bump(nt, vec, spec.get("tile", 1.0), spec["weave"],
                             spec.get("bump_strength", 0.35), spec.get("bump_distance", 0.004))
        nt.links.new(normal, bsdf.inputs["Normal"])
    elif spec.get("bump_feat"):
        normal, _ = _noise_bump(nt, vec, spec.get("tile", 1.0), spec["bump_feat"],
                                spec.get("bump_strength", 0.35),
                                spec.get("bump_distance", 0.02),
                                spec.get("bump_detail", 6.0))
        nt.links.new(normal, bsdf.inputs["Normal"])

    if spec.get("voro_feat"):
        v = nt.nodes.new("ShaderNodeTexVoronoi")
        v.inputs["Scale"].default_value = spec.get("tile", 1.0) / spec["voro_feat"]
        v.inputs["Randomness"].default_value = 0.7
        nt.links.new(vec, v.inputs["Vector"])
        normal = add_bump(nt, v.outputs["Distance"], spec.get("bump_strength", 0.4),
                          spec.get("bump_distance", 0.01))
        nt.links.new(normal, bsdf.inputs["Normal"])

    nt.links.new(colour, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.7)
    bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    _apply_common(bsdf, m, spec)
    src = "procedural"
    if spec.get("emit"):
        src = "procedural-emissive"
    return register(m, cat, spec, lin, spec.get("rough", 0.7), spec.get("metal", 0.0),
                    emissive=bool(spec.get("emit")), source=src)


def b_tex(spec):
    """PolyHaven textured material (optionally tinted / rusted / painted)"""
    cat = spec["cat"]
    name = spec["name"]
    asset = spec["asset"]
    res = spec.get("res") or TEXSETS[asset]
    tile = spec.get("tile", 2.0)
    m, nt, bsdf = new_mat(name)

    diff = load_map(asset, "diff", res, False)
    rough_img = load_map(asset, "rough", res, True) if spec.get("rough") == "img" else None
    disp = load_map(asset, "disp", res, True) if spec.get("bump") else None

    if diff is None:                                   # fallback: flat colour
        lin = hex_to_linear(spec.get("color", "#808080"))
        bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
        bsdf.inputs["Roughness"].default_value = spec.get("rough_default", 0.75)
        bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)
        _apply_common(bsdf, m, spec)
        FAILURES.append((name, "no diffuse map for %s" % asset))
        return register(m, cat, spec, lin, spec.get("rough_default", 0.75),
                        spec.get("metal", 0.0), source="fallback-flat")

    it = img_node(nt, diff, tile)
    colour = it.outputs["Color"]
    original = colour

    if spec.get("desat"):
        colour = hue_sat(nt, colour, 0.5, spec["desat"], 1.0)
    if spec.get("tint"):
        mean = img_mean_linear(diff)
        lum = max(0.2126 * mean[0] + 0.7152 * mean[1] + 0.0722 * mean[2], 0.015)
        tl = hex_to_linear(spec["tint"])
        gain = (tl[0] / lum, tl[1] / lum, tl[2] / lum, 1.0)
        colour = mix_rgba(nt, colour, const_col(nt, gain), blend="MULTIPLY", fac=1.0)
        base_rgb = tl
    else:
        base_rgb = img_mean_linear(diff)

    if spec.get("mult"):
        mv = float(spec["mult"])
        colour = mix_rgba(nt, colour, const_col(nt, (mv, mv, mv, 1.0)),
                          blend="MULTIPLY", fac=1.0)
        base_rgb = tuple(c * mv for c in base_rgb)

    if spec.get("paint_mix"):
        colour = mix_rgba(nt, original, colour, fac=spec["paint_mix"])

    if spec.get("rust"):
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = tile / 0.9
        n.inputs["Detail"].default_value = 8.0
        n.inputs["Roughness"].default_value = 0.7
        n.inputs["Distortion"].default_value = 1.2
        vec = coord_mapping(nt, tile)
        nt.links.new(vec, n.inputs["Vector"])
        mask = ramp(nt, [(0.42, (0, 0, 0, 1)), (0.66, (1, 1, 1, 1))], n.outputs["Fac"])
        mask = math_nt(nt, "MULTIPLY", mask, spec["rust"], clamp=True)
        rust_lin = hex_to_linear(spec.get("rust_color", "#7A3B1E"))
        colour = mix_rgba(nt, colour, const_col(nt, (rust_lin[0], rust_lin[1], rust_lin[2], 1.0)),
                          fac_sock=mask)
        base_rgb = tuple(base_rgb[i] * (1 - spec["rust"] * 0.5) + rust_lin[i] * spec["rust"] * 0.5
                         for i in range(3))

    nt.links.new(colour, bsdf.inputs["Base Color"])

    # roughness
    if rough_img is not None:
        ri = img_node(nt, rough_img, tile)
        nt.links.new(ri.outputs["Color"], bsdf.inputs["Roughness"])
        rough = img_mean_linear(rough_img)[0]
    else:
        rough = spec.get("rough", 0.75) if not isinstance(spec.get("rough"), str) else spec.get("rough_default", 0.75)
        bsdf.inputs["Roughness"].default_value = rough

    bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)

    # height
    if disp is not None:
        di = img_node(nt, disp, tile)
        normal = add_bump(nt, di.outputs["Color"], spec.get("bump_strength", 0.5),
                          spec.get("bump_distance", 0.03))
        nt.links.new(normal, bsdf.inputs["Normal"])
    elif spec.get("bump_feat"):
        vec = coord_mapping(nt, tile)
        normal, _ = _noise_bump(nt, vec, tile, spec["bump_feat"],
                                spec.get("bump_strength", 0.35),
                                spec.get("bump_distance", 0.02))
        nt.links.new(normal, bsdf.inputs["Normal"])

    _apply_common(bsdf, m, spec)
    src = "polyhaven:%s@%s" % (asset, res)
    if disp is None:
        src += "|bump=procedural"
    return register(m, cat, spec, base_rgb, rough, spec.get("metal", 0.0),
                    emissive=bool(spec.get("emit")), source=src)


def b_glass(spec):
    lin = hex_to_linear(spec["color"])
    m, nt, bsdf = new_mat(spec["name"])
    vec = coord_mapping(nt, spec.get("tile", 2.0))
    # subtle waviness so glass is not perfectly flat
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = spec.get("tile", 2.0) / 1.6
    n.inputs["Detail"].default_value = 2.0
    nt.links.new(vec, n.inputs["Vector"])
    normal = add_bump(nt, n.outputs["Fac"], spec.get("bump_strength", 0.06), 0.01)
    nt.links.new(normal, bsdf.inputs["Normal"])
    bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.05)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = spec.get("ior", 1.45)
    _apply_common(bsdf, m, spec)
    return register(m, spec["cat"], spec, lin, spec.get("rough", 0.05), 0.0, source="procedural")


def b_marble(spec):
    m, nt, bsdf = new_mat(spec["name"])
    tile = spec.get("tile", 2.0)
    vec = coord_mapping(nt, tile)
    w = nt.nodes.new("ShaderNodeTexWave")
    try:
        w.wave_type = "BANDS"
        w.bands_direction = "X"
    except Exception:
        pass
    w.inputs["Scale"].default_value = tile / 3.2
    w.inputs["Distortion"].default_value = 16.0
    w.inputs["Detail"].default_value = 4.0
    w.inputs["Detail Scale"].default_value = 1.6
    nt.links.new(vec, w.inputs["Vector"])
    base = hex_to_linear(spec["color"])
    vein = hex_to_linear(spec.get("vein", "#6E6A64"))
    cols = ramp(nt, [(0.00, (base[0], base[1], base[2], 1)),
                     (0.42, (base[0], base[1], base[2], 1)),
                     (0.50, (vein[0], vein[1], vein[2], 1)),
                     (0.58, (base[0], base[1], base[2], 1)),
                     (1.00, (base[0], base[1], base[2], 1))], w.outputs["Fac"])
    nt.links.new(cols, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.16)
    bsdf.inputs["Metallic"].default_value = 0.0
    _apply_common(bsdf, m, spec)
    return register(m, spec["cat"], spec, base, spec.get("rough", 0.16), 0.0, source="procedural")


def b_water(spec):
    m, nt, bsdf = new_mat(spec["name"])
    tile = spec.get("tile", 3.0)
    vec = coord_mapping(nt, tile)
    lin = hex_to_linear(spec["color"])
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = tile / 0.9
    n.inputs["Detail"].default_value = 6.0
    n.inputs["Distortion"].default_value = 0.6
    nt.links.new(vec, n.inputs["Vector"])
    normal = add_bump(nt, n.outputs["Fac"], spec.get("bump_strength", 0.28), 0.05)
    nt.links.new(normal, bsdf.inputs["Normal"])
    bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.04)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Specular IOR Level"].default_value = 0.7
    _apply_common(bsdf, m, spec)
    return register(m, spec["cat"], spec, lin, spec.get("rough", 0.04), 0.0, source="procedural")


def b_decal(spec):
    m, nt, bsdf = new_mat(spec["name"])
    tile = spec.get("tile", 2.0)
    vec = coord_mapping(nt, tile)
    lin = hex_to_linear(spec["color"])
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = tile / 1.2
    n.inputs["Detail"].default_value = 5.0
    n.inputs["Roughness"].default_value = 0.6
    nt.links.new(vec, n.inputs["Vector"])
    a = ramp(nt, [(0.44, (0, 0, 0, 1)), (0.58, (1, 1, 1, 1))], n.outputs["Fac"])
    alpha = math_nt(nt, "MULTIPLY", a, spec.get("alpha", 0.75), clamp=True)
    bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.2)
    bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    nt.links.new(alpha, bsdf.inputs["Alpha"])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        pass
    try:
        m.blend_method = "BLEND"
    except Exception:
        pass
    try:
        m.use_transparent_shadow = True
    except Exception:
        pass
    return register(m, spec["cat"], spec, lin, spec.get("rough", 0.2), spec.get("metal", 0.0),
                    source="procedural")


BUILDERS = {
    "solid": b_solid, "tex": b_tex, "glass": b_glass, "marble": b_marble,
    "water": b_water, "decal": b_decal,
}


def build(spec):
    try:
        BUILDERS[spec["kind"]](spec)
        return True
    except Exception as e:
        FAILURES.append((spec["name"], "%s: %s" % (type(e).__name__, e)))
        log("BUILD FAILED", spec["name"])
        traceback.print_exc()
        return False

# ---------------------------------------------------------------------------
# THE MATERIAL LIST (source of truth -- must match style_bible.md)
# ---------------------------------------------------------------------------
SPECS = []


def S(**kw):
    SPECS.append(kw)
    return kw


# --- roads / ground --------------------------------------------------------
S(kind="tex", name="road_asphalt_new", cat="roads", asset="clean_asphalt", res="2k", tile=4.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.50, bump_distance=0.035,
  desc="New asphalt: highway ring, freshly resurfaced arterials, car parks.")
S(kind="tex", name="road_asphalt_worn", cat="roads", asset="asphalt_01", res="2k", tile=4.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.60, bump_distance=0.050,
  desc="Default street asphalt: worn, patchy, tyre-polished. Use for most streets.")
S(kind="tex", name="road_track_asphalt", cat="roads", asset="clean_asphalt", res="2k", tile=4.0,
  rough="img", metal=0.0, mult=0.78, bump=True, bump_strength=0.45, bump_distance=0.030,
  desc="Race circuit surface: darker, gripped (clean_asphalt x0.78).")
S(kind="solid", name="road_lane_paint_white", cat="roads", color="#E9E3D7", rough=0.52, metal=0.0,
  tile=2.0, bump_feat=0.6, bump_strength=0.15, bump_distance=0.006,
  desc="Lane divider, crosswalk stripes, stop lines, arrows. Bone white.")
S(kind="solid", name="road_lane_paint_yellow", cat="roads", color="#D9A41F", rough=0.52, metal=0.0,
  tile=2.0, bump_feat=0.6, bump_strength=0.15, bump_distance=0.006,
  desc="Centre line / edge line yellow (palette mustard).")
S(kind="tex", name="road_curb_concrete", cat="roads", asset="concrete_wall_008", res="2k",
  tile=2.0, rough="img", metal=0.0, bump=True, bump_strength=0.40, bump_distance=0.020,
  desc="Curb faces and gutter lips. Height 0.15 m per contract.")
S(kind="tex", name="sidewalk_paving", cat="roads", asset="concrete_pavement_02", res="1k",
  tile=1.8, rough="img", metal=0.0, bump=True, bump_strength=0.50, bump_distance=0.025,
  desc="Sidewalk slab paving (also plaza and park paths).")
S(kind="tex", name="road_cobble", cat="roads", asset="cobblestone_floor_04", res="1k",
  tile=1.5, rough="img", metal=0.0, bump=True, bump_strength=0.75, bump_distance=0.045,
  desc="Market alleys, pedestrian deep streets, old town lanes.")
S(kind="solid", name="road_manhole_metal", cat="roads", color="#3A3C40", rough=0.50, metal=1.0,
  tile=0.6, voro_feat=0.06, bump_strength=0.35, bump_distance=0.006,
  desc="Manhole covers, drain grates, utility plates.")

# --- facades ---------------------------------------------------------------
FACADE_TEXS = [
    ("facade_concrete", "concrete_wall_008", "2k", 2.71, 0.45, 0.020,
     "Smooth board-formed concrete. Downtown pods, civic, towers."),
    ("facade_concrete_weathered", "concrete_wall_003", "1k", 3.00, 0.50, 0.030,
     "Stained / weathered concrete. Industrial, back walls, service cores."),
    ("facade_concrete_slab", "concrete_slab_wall", "1k", 2.30, 0.40, 0.020,
     "Banded precast slab facade. Downtown podiums, parking, brutalist blocks."),
    ("facade_stucco", "white_stucco", "1k", 2.00, 0.35, 0.015,
     "Clean off-white stucco render. Residential + green belt."),
    ("facade_plaster_weathered", "worn_cracked_plaster", "1k", 1.80, 0.55, 0.030,
     "Cracked, patchy plaster. Market back streets, older blocks."),
    ("facade_brick_red", "brick_wall_001", "2k", 3.00, 0.75, 0.045,
     "Red clay brick, hero resolution. Houses, lofts, warehouse conversions."),
    ("facade_timber_cladding", "weathered_brown_planks", "1k", 1.80, 0.55, 0.030,
     "Horizontal timber cladding. Cottages, park pavilions, cafe annexes."),
]
for nm, asset, res, tile, bs, bd, desc in FACADE_TEXS:
    S(kind="tex", name=nm, cat="facades", asset=asset, res=res, tile=tile, rough="img",
      metal=0.0, bump=True, bump_strength=bs, bump_distance=bd, desc=desc)

# painted plaster in every palette colour (shared plastered_wall_02 albedo, tinted)
for _c, _h in PALETTE.items():
    S(kind="tex", name="facade_plaster_%s" % _c, cat="facades", asset="plastered_wall_02",
      res="1k", tile=2.23, rough="img", metal=0.0, tint=_h, bump=True,
      bump_strength=0.35, bump_distance=0.015,
      desc="Painted plaster facade in palette '%s' (%s). Main district wall colour." % (_c, _h))

S(kind="tex", name="facade_brick_painted", cat="facades", asset="brick_wall_001", res="2k",
  tile=3.0, rough="img", metal=0.0, desat=0.30, tint="#E9E3D7", paint_mix=0.80,
  bump=True, bump_strength=0.70, bump_distance=0.040,
  desc="Whitewashed / painted brick (bone). Re-tint by re-running materials.py.")
S(kind="tex", name="facade_metal_panel", cat="facades", asset="painted_metal_shutter", res="1k",
  tile=2.0, rough=0.38, metal=0.75, bump=True, bump_strength=0.30, bump_distance=0.012,
  desc="Profiled metal cladding, clean. Towers, retail boxes, modern infill.")
S(kind="tex", name="facade_metal_panel_weathered", cat="facades", asset="painted_metal_shutter",
  res="1k", tile=2.0, rough=0.62, metal=0.60, rust=0.50, rust_color="#7A3B1E",
  bump=True, bump_strength=0.45, bump_distance=0.020,
  desc="Rusted profiled metal. Industrial halls, sheds, service elevations.")

# --- glass -----------------------------------------------------------------
S(kind="glass", name="glass_clear", cat="glass", color="#CFDCD6", rough=0.04, alpha=0.30,
  tile=2.0, desc="Window glass for houses/offices. Semi-transparent (alpha blended).")
S(kind="glass", name="glass_tinted_office", cat="glass", color="#20364F", rough=0.08, alpha=0.62,
  tile=2.5, desc="Dark tinted curtain wall for downtown towers. Mostly reflective.")
S(kind="glass", name="glass_shop", cat="glass", color="#DDE9E7", rough=0.03, alpha=0.16,
  tile=2.0, desc="Shopfront glass: very clear so interiors read through.")
S(kind="glass", name="glass_frosted", cat="glass", color="#D5DBDB", rough=0.45, alpha=0.85,
  tile=1.5, desc="Frosted/bathroom/partition glass.")

# --- metal / wood / fabric -------------------------------------------------
S(kind="solid", name="metal_steel", cat="metal_wood_fabric", color="#9B968D", rough=0.34,
  metal=1.0, tile=1.0, bump_feat=1.4, bump_strength=0.10, bump_distance=0.003,
  desc="Bare steel: railings, frames, gantries, street furniture.")
S(kind="tex", name="metal_checker_plate", cat="metal_wood_fabric", asset="metal_plate", res="1k",
  tile=0.5, rough=0.45, metal=0.90, bump=True, bump_strength=0.65, bump_distance=0.020,
  desc="Chequer plate: industrial walkways, stairs, ramp surfaces.")
S(kind="tex", name="metal_rust", cat="metal_wood_fabric", asset="rusty_painted_metal", res="1k",
  tile=2.2, rough=0.85, metal=0.30, bump=True, bump_strength=0.60, bump_distance=0.030,
  desc="Heavy rust. Barriers, old containers, track furniture, scrap.")
for _c in ("charcoal", "bone", "teal", "oxblood", "mustard", "sage", "navy", "sand"):
    S(kind="solid", name="metal_painted_%s" % _c, cat="metal_wood_fabric", color=PALETTE[_c],
      rough=0.42, metal=0.0, tile=1.0, bump_feat=1.2, bump_strength=0.12, bump_distance=0.005,
      desc="Painted/galvanised metal in palette '%s': poles, bollards, rails, doors, shutters." % _c)
S(kind="tex", name="wood_planks", cat="metal_wood_fabric", asset="wood_planks", res="1k",
  tile=1.5, rough="img", metal=0.0, bump=True, bump_strength=0.45, bump_distance=0.020,
  desc="Clean sawn planks: decks, stalls, furniture, gates.")
S(kind="tex", name="wood_planks_weathered", cat="metal_wood_fabric", asset="weathered_planks",
  res="1k", tile=2.0, rough="img", metal=0.0, bump=True, bump_strength=0.55, bump_distance=0.025,
  desc="Grey weathered planks: fences, boardwalks, crates, market trestles.")
for _c in ("bone", "sand", "terracotta", "oxblood", "mustard", "sage", "teal", "navy", "magenta"):
    S(kind="solid", name="fabric_awning_%s" % _c, cat="metal_wood_fabric", color=PALETTE[_c],
      rough=0.78, metal=0.0, tile=1.0, weave=0.014, bump_strength=0.45, bump_distance=0.003,
      sheen=0.30, mottle=(0.55, 0.08),
      desc="Awning / canopy / stall cloth in palette '%s'. Stripe by splitting geometry." % _c)

# --- roofs -----------------------------------------------------------------
S(kind="tex", name="roof_clay_tile", cat="roofs", asset="clay_roof_tiles", res="1k", tile=4.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.85, bump_distance=0.060,
  desc="Terracotta barrel tiles. Houses, teahouses, civic pitched roofs.")
S(kind="tex", name="roof_corrugated_metal", cat="roofs", asset="corrugated_iron", res="1k",
  tile=1.12, rough=0.50, metal=0.65, bump=True, bump_strength=0.70, bump_distance=0.045,
  desc="Corrugated steel roofing. Industrial, sheds, market canopies.")
S(kind="tex", name="roof_bitumen_flat", cat="roofs", asset="bitumen", res="1k", tile=4.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.35, bump_distance=0.020,
  desc="Flat felt/bitumen roof membrane. Apartments, towers, retail boxes.")

# --- nature ----------------------------------------------------------------
S(kind="tex", name="nature_grass", cat="nature", asset="grass_ground", res="1k", tile=2.51,
  rough="img", metal=0.0, bump=True, bump_strength=0.40, bump_distance=0.020,
  desc="Mown lawn: parks, verges, gardens, sports fields.")
S(kind="tex", name="nature_wild_grass", cat="nature", asset="sparse_grass", res="1k", tile=2.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.55, bump_distance=0.030,
  desc="Longer / sparser grass: verges, embankments, river banks, track run-off.")
for _c, _h in (("dark", "#2F4A28"), ("mid", "#4A7A38"), ("light", "#7FA24A")):
    S(kind="solid", name="nature_leaf_%s" % _c, cat="nature", color=_h, rough=0.55, metal=0.0,
      tile=1.0, bump_feat=0.10, bump_strength=0.35, bump_distance=0.006, mottle=(0.6, 0.18),
      sheen=0.15,
      desc="Foliage colour '%s' for leaf cards/clumps (%s). Opaque: model leaf shape." % (_c, _h))
S(kind="tex", name="nature_bark", cat="nature", asset="bark_brown_01", res="1k", tile=1.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.80, bump_distance=0.050,
  desc="Tree bark (vertical mapping reads correctly on trunks).")
S(kind="tex", name="nature_dirt", cat="nature", asset="farm_soil", res="1k", tile=2.0,
  rough="img", metal=0.0, bump=True, bump_strength=0.50, bump_distance=0.030,
  desc="Bare soil: planting beds, construction yards, worn ground.")
S(kind="tex", name="nature_gravel", cat="nature", asset="gravel_floor", res="1k", tile=2.25,
  rough="img", metal=0.0, bump=True, bump_strength=0.70, bump_distance=0.045,
  desc="Gravel: paths, shoulders, track run-off, industrial yards.")
S(kind="water", name="nature_water_lake", cat="nature", color="#10262B", rough=0.035, tile=3.0,
  bump_strength=0.28, desc="Lake / pond / fountain water: glossy, rippled, opaque (EEVEE safe).")

# --- emissive --------------------------------------------------------------
# day-time strengths; the Lighting agent multiplies them for the night pass
# (see style_bible.md -> time of day).
EMISSIVES = [
    ("neon_teal",    "#3FF0E2", 6.0, "Neon/LED in palette teal: bars, tubes, edge strips."),
    ("neon_magenta", "#FF4D94", 6.0, "Neon/LED in palette magenta: clubs, cinema, signage."),
    ("neon_violet",  "#A66BFF", 6.0, "Neon/LED in palette violet: clubs, late-night signage."),
    ("neon_oxblood", "#FF3B30", 6.0, "Neon/LED red (palette oxblood): warnings, bars, signs."),
    ("neon_mustard", "#FFC043", 6.0, "Neon/LED amber (palette mustard): lanterns, signage."),
    ("light_warm",   "#FFD9A8", 8.0, "Warm 2700K interior/lamp emissive: homes, restaurants."),
    ("light_cool",   "#DCEFFF", 8.0, "Cool 5000K office/retail emissive: shops, lobbies."),
    ("sign_white",   "#FFFFFF", 5.0, "Backlit sign face / lightbox / LED billboard white."),
]
for _n, _h, _s, _d in EMISSIVES:
    S(kind="solid", name=_n, cat="emissive", color=_h, rough=0.40, metal=0.0, tile=1.0,
      emit=_h, emit_strength=_s, desc=_d + "  Day strength %.0f (night: see bible)." % _s)

# --- interiors -------------------------------------------------------------
for _c in ("bone", "sand", "teal"):
    S(kind="solid", name="int_wall_paint_%s" % _c, cat="interiors", color=PALETTE[_c],
      rough=0.82, metal=0.0, tile=2.0, bump_feat=0.45, bump_strength=0.12, bump_distance=0.005,
      desc="Interior wall paint, palette '%s'. Eggshell, slight roller texture." % _c)
S(kind="tex", name="int_wood_floor", cat="interiors", asset="wood_floor", res="1k", tile=1.7,
  rough="img", metal=0.0, bump=True, bump_strength=0.40, bump_distance=0.015,
  desc="Laid wood floor: homes, hotels, restaurants, offices.")
S(kind="tex", name="int_tile_floor", cat="interiors", asset="interior_tiles", res="1k", tile=1.9,
  rough="img", metal=0.0, bump=True, bump_strength=0.35, bump_distance=0.012,
  desc="Ceramic tile floor: bathrooms, kitchens, lobbies, canteens.")
S(kind="solid", name="int_carpet", cat="interiors", color="#3A3630", rough=0.95, metal=0.0,
  tile=0.5, bump_feat=0.02, bump_strength=0.70, bump_distance=0.004, mottle=(0.6, 0.12),
  desc="Cut-pile carpet: offices, hotel rooms, clubs, gym studios.")
S(kind="marble", name="int_marble", cat="interiors", color="#EDEAE4", vein="#7E7A73",
  rough=0.15, tile=2.5, coat=0.50, coat_rough=0.03,
  desc="Polished marble slab: bank lobbies, hotel receptions, hero interiors.")
S(kind="solid", name="int_upholstery", cat="interiors", color="#263B5C", rough=0.82, metal=0.0,
  tile=1.0, weave=0.016, bump_strength=0.40, bump_distance=0.003, sheen=0.35,
  mottle=(0.5, 0.10), desc="Woven upholstery (palette navy): booths, sofas, headboards.")
S(kind="tex", name="int_laminate_counter", cat="interiors", asset="laminate_floor_02", res="1k",
  tile=1.7, rough=0.35, metal=0.0, coat=0.35, bump=True, bump_strength=0.30, bump_distance=0.010,
  desc="Sealed laminate counter top: shops, bars, reception desks, kitchens.")
S(kind="solid", name="int_mirror", cat="interiors", color="#EDEDED", rough=0.03, metal=1.0,
  tile=1.0, desc="Mirror: gyms, bathrooms, boutiques, elevator cabins.")

# --- vehicles --------------------------------------------------------------
for _c in ("bone", "charcoal", "navy", "oxblood"):
    S(kind="solid", name="vehicle_paint_%s" % _c, cat="vehicles", color=PALETTE[_c],
      rough=0.28, metal=0.25, tile=1.0, coat=1.0, coat_rough=0.03,
      mottle=(0.6, 0.05), desc="Car body paint, palette '%s' (clearcoated)." % _c)

# --- decals ----------------------------------------------------------------
S(kind="decal", name="decal_puddle_wet", cat="decals", color="#1A1D20", rough=0.06, metal=0.0,
  tile=3.0, alpha=0.85, desc="Puddle / wet patch decal on flat planes (alpha blended).")
S(kind="decal", name="decal_grime", cat="decals", color="#2A241C", rough=0.90, metal=0.0,
  tile=2.5, alpha=0.60, desc="Grime/dirt decal patch for kerbs and wall bases.")

log("spec list:", len(SPECS), "materials;", len(TEXSETS), "texture sets")

# ---------------------------------------------------------------------------
# index file
# ---------------------------------------------------------------------------
def write_index():
    payload = OrderedDict()
    payload["schema"] = "city-materials-index/1"
    payload["blend"] = "/city/materials.blend"
    payload["generated_by"] = "city/modules/materials.py"
    payload["unit"] = "metre"
    payload["node_groups"] = ["NG_EdgeWear_Dirt", "NG_ColorVariation"]
    payload["palette"] = OrderedDict((k, v) for k, v in PALETTE.items())
    payload["conventions"] = OrderedDict([
        ("mapping", "TEXCOORD Object -> Mapping(scale = 1/tile_scale_m); no UVs required"),
        ("image_projection", "BOX, projection_blend 0.12"),
        ("height", "Bump node fed by the PolyHaven displacement map (UV-free)"),
        ("texel_density", "target 512 px / 2 m (256 px/m); floor 256 px/m (tile <= resolution/256)"),
        ("append", "bpy.data.libraries.load('/city/materials.blend') -- append by name, never edit"),
        ("night", "emissive materials store DAY strength; see style_bible.md for night multipliers"),
    ])
    payload["material_names"] = sorted(INDEX.keys())
    payload["materials"] = INDEX
    payload["stats"] = OrderedDict([
        ("material_count", len(INDEX)),
        ("category_counts", _counts(INDEX, "category")),
        ("emissive_count", sum(1 for v in INDEX.values() if v["emissive"])),
        ("polyhaven_materials", sum(1 for v in INDEX.values() if v["source"].startswith("polyhaven"))),
        ("procedural_materials", sum(1 for v in INDEX.values() if v["source"].startswith("procedural"))),
        ("texture_sets", len(TEXSETS)),
        ("failed", [f[0] for f in FAILURES]),
    ])
    with open(INDEX_PATH, "w") as f:
        json.dump(payload, f, indent=1)
    log("wrote", INDEX_PATH, os.path.getsize(INDEX_PATH), "bytes")


def _counts(d, key):
    out = OrderedDict()
    for v in d.values():
        out[v[key]] = out.get(v[key], 0) + 1
    return OrderedDict(sorted(out.items()))


# ---------------------------------------------------------------------------
# preview render (1920x1080, day)
# ---------------------------------------------------------------------------
def render_preview():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1920
    sc.render.resolution_y = 1080
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    try:
        sc.view_settings.view_transform = "Standard"
    except Exception:
        pass
    try:
        sc.eevee.taa_render_samples = 64
    except Exception:
        pass
    try:
        sc.eevee.use_raytracing = True
    except Exception:
        pass

    root = bpy.data.collections.get("materials")
    if root:
        mesh_col = bpy.data.collections.new("PreviewMeshes")
        root.children.link(mesh_col)
        light_col = bpy.data.collections.new("PreviewLights")
        root.children.link(light_col)
    else:
        mesh_col = sc.collection
        light_col = sc.collection

    def M(name):
        return bpy.data.materials.get(name)

    import bmesh
    from mathutils import Matrix, Euler, Vector

    def add_cube(name, loc, size, mat, rot=(0, 0, 0)):
        # geometry baked in world space (no bpy.ops => no context risk headless)
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        xf = Matrix.Translation(Vector(loc)) \
            @ Euler(rot).to_matrix().to_4x4() \
            @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
        bm.transform(xf)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        mesh_col.objects.link(o)
        if mat:
            o.data.materials.append(mat)
        return o

    def add_sphere(name, loc, r, mat):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=24, radius=r)
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        o.location = loc
        mesh_col.objects.link(o)
        if mat:
            o.data.materials.append(mat)
        return o

    def add_text(name, body, loc, size=0.75, mat=None):
        cu = bpy.data.curves.new(name, type="FONT")
        cu.body = body
        cu.size = size
        cu.align_x = "CENTER"
        cu.extrude = 0.01
        o = bpy.data.objects.new(name, cu)
        o.location = loc
        o.rotation_euler = (1.5708, 0, 0)
        mesh_col.objects.link(o)
        if mat:
            o.data.materials.append(mat)
        return o

    # ground: asphalt apron + paving strip
    add_cube("PV_ground", (0, 0, -0.05), (52, 40, 0.1), M("road_asphalt_worn"))
    add_cube("PV_sidewalk", (0, 5.0, 0.06), (40, 5.0, 0.12), M("sidewalk_paving"))
    add_cube("PV_lane", (0, -2.5, 0.011), (40, 0.16, 0.01), M("road_lane_paint_white"))
    add_cube("PV_lane2", (0, -6.5, 0.011), (40, 0.16, 0.01), M("road_lane_paint_yellow"))

    # back wall: facade panels
    panels = ["facade_concrete", "facade_plaster_bone", "facade_plaster_terracotta",
              "facade_brick_red", "facade_metal_panel", "facade_timber_cladding",
              "facade_concrete_slab", "facade_plaster_teal"]
    x0 = -14.0
    for i, p in enumerate(panels):
        add_cube("PV_wall_%s" % p, (x0 + i * 4.0, 9.5, 3.0), (3.8, 0.6, 6.0), M(p))
    add_cube("PV_roofband", (0, 9.4, 6.35), (32.4, 1.4, 0.7), M("roof_clay_tile"))
    add_cube("PV_roofband2", (0, 9.4, 6.95), (32.4, 1.4, 0.5), M("roof_corrugated_metal"))
    add_cube("PV_baseband", (0, 9.1, 0.28), (32.4, 0.6, 0.56), M("road_curb_concrete"))

    # neon + sign strips on the wall
    for i, (n, _h, _s, _d) in enumerate(EMISSIVES[:5]):
        add_cube("PV_neon_%s" % n, (-12.0 + i * 6.0, 9.1, 5.2), (3.2, 0.14, 0.16), M(n))
    add_cube("PV_signbox", (12.0, 9.1, 5.0), (5.0, 0.2, 1.1), M("sign_white"))
    add_cube("PV_signbox2", (-12.0, 9.1, 4.6), (5.0, 0.2, 1.1), M("metal_painted_charcoal"))
    add_cube("PV_lampwarm", (-15.5, 9.1, 3.0), (1.2, 0.2, 1.2), M("light_warm"))
    add_cube("PV_lampcool", (15.5, 9.1, 3.0), (1.2, 0.2, 1.2), M("light_cool"))

    # middle row: hero material spheres
    spheres = ["glass_tinted_office", "metal_steel", "metal_rust", "int_marble",
               "nature_bark", "fabric_awning_magenta", "vehicle_paint_navy",
               "roof_clay_tile", "road_cobble", "int_wood_floor"]
    for i, s in enumerate(spheres):
        add_sphere("PV_ball_%s" % s, (-13.5 + i * 3.0, 2.0, 1.15), 1.15, M(s))

    # ground material cubes
    cubes = ["nature_grass", "nature_gravel", "metal_checker_plate", "wood_planks",
             "int_carpet", "glass_shop", "int_laminate_counter", "nature_water_lake"]
    for i, c in enumerate(cubes):
        add_cube("PV_cube_%s" % c, (-12.0 + i * 3.4, -1.6, 0.6), (1.5, 1.5, 1.2), M(c))

    # palette strip (12 painted plaster swatches)
    names = list(PALETTE.keys())
    for i, c in enumerate(names):
        add_cube("PV_pal_%s" % c, (-10.7 + i * 1.95, -6.2, 0.95), (1.6, 1.6, 1.9),
                 M("facade_plaster_%s" % c))
        add_text("PV_ptxt_%s" % c, "%s\n%s" % (c, PALETTE[c]),
                 (-10.7 + i * 1.95, -7.05, 0.12), size=0.34, mat=M("int_wall_paint_bone"))

    add_text("PV_h1", "CITY MATERIAL LIBRARY  --  %d materials / 12-colour palette" % len(INDEX),
             (0, 9.05, 7.7), size=0.95, mat=M("int_wall_paint_bone"))
    add_text("PV_h2", "TEXTURED SURFACES", (0, 3.0, 3.6), size=0.55, mat=M("int_wall_paint_bone"))
    add_text("PV_h3", "PALETTE (facade_plaster_*)", (0, -6.9, 3.05), size=0.55,
             mat=M("int_wall_paint_bone"))

    # camera
    cam_d = bpy.data.cameras.new("PV_cam")
    cam_d.lens = 34
    cam = bpy.data.objects.new("PV_cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -23.5, 8.0)
    tgt = bpy.data.objects.new("PV_target", None)
    tgt.location = (0.0, 3.0, 2.6)
    sc.collection.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    # lights
    sun_d = bpy.data.lights.new("PV_sun", "SUN")
    sun_d.energy = 4.0
    sun_d.angle = 0.06
    sun = bpy.data.objects.new("PV_sun", sun_d)
    sun.rotation_euler = (0.75, 0.12, 0.75)
    light_col.objects.link(sun)
    area_d = bpy.data.lights.new("PV_fill", "AREA")
    area_d.energy = 2500.0
    area_d.size = 18.0
    area = bpy.data.objects.new("PV_fill", area_d)
    area.location = (-8.0, -18.0, 12.0)
    area.rotation_euler = (0.9, 0.0, -0.3)
    light_col.objects.link(area)

    # world
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        bg.inputs[0].default_value = (0.14, 0.18, 0.26, 1.0)
        bg.inputs[1].default_value = 1.0

    sc.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    log("preview:", PREVIEW_PATH, os.path.exists(PREVIEW_PATH))


# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # module collection (contract: collection named after the module)
    root = bpy.data.collections.new("materials")
    bpy.context.scene.collection.children.link(root)
    for sub in ("Meshes", "Colliders", "Lights"):
        child = bpy.data.collections.new(sub)
        root.children.link(child)

    build_node_groups()

    ok = 0
    for spec in SPECS:
        if build(spec):
            ok += 1
    log("built %d/%d materials in %.1fs" % (ok, len(SPECS), time.time() - t0))

    # pack every image so the blend is portable, then save
    n_img = len([i for i in bpy.data.images if i.source == "FILE"])
    bpy.ops.file.pack_all()
    packed = len([i for i in bpy.data.images if i.source == "FILE" and i.packed_file])
    log("images on disk %d, packed %d" % (n_img, packed))
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    log("saved", BLEND_PATH, "%.1f MB" % (os.path.getsize(BLEND_PATH) / 1e6))

    write_index()

    render_preview()

    log("done in %.1fs" % (time.time() - t0))
    if FAILURES:
        log("FAILURES:")
        for f in FAILURES:
            log("   ", f)
    print("MATERIAL_COUNT=%d" % len(INDEX), flush=True)


if __name__ == "__main__":
    main()
