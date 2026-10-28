"""CITY MATERIAL LIBRARY BUILDER
================================
Builds:
  /home/abdulhadi/Work/city/materials.blend   (all city materials + 2 shared node groups, images packed)
  /home/abdulhadi/Work/city/materials.json    (index for downstream agents)

Run headless:
  cd /home/abdulhadi/Work/city && blender -b -P modules/materials_lib.py

Rules (see style_bible.md):
  * PBR via Principled BSDF only.
  * Hero surfaces use CC0 PolyHaven 1k texture sets (downloaded to /tmp/opencode/ph).
  * Every base colour passes through  City_Variation -> City_EdgeWear  -> Principled.
  * Texel density target: a 1024px texture covers 4 m (256 px/m); roads 8 m.
"""
import bpy
import json
import os
import sys
import traceback

ROOT = "/home/abdulhadi/Work/city"
TEX = "/tmp/opencode/ph"
OUT_BLEND = os.path.join(ROOT, "materials.blend")
OUT_JSON = os.path.join(ROOT, "materials.json")

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def hexc(h, a=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, a)


def clear_nodes(nt):
    for n in list(nt.nodes):
        nt.nodes.remove(n)


def sock(node, ident, out=False):
    pool = node.outputs if out else node.inputs
    for s in pool:
        if s.identifier == ident:
            return s
    ids = [s.identifier for s in pool]
    raise RuntimeError("%s has no socket %r (have %s)" % (node.bl_idname, ident, ids))


def math_node(nt, op, v0=None, v1=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if v0 is not None:
        n.inputs[0].default_value = v0
    if v1 is not None:
        n.inputs[1].default_value = v1
    return n


def mix_node(nt, blend="MIX", fac=None):
    n = nt.nodes.new("ShaderNodeMixRGB")
    n.blend_type = blend
    if fac is not None:
        n.inputs["Fac"].default_value = fac
    return n


def val_node(nt, v):
    n = nt.nodes.new("ShaderNodeValue")
    n.outputs[0].default_value = v
    return n


def rgb_node(nt, col):
    n = nt.nodes.new("ShaderNodeRGB")
    n.outputs[0].default_value = col
    return n


def noise_node(nt, scale=6.0, detail=5.0, rough=0.55):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    return n


def ramp_node(nt, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    el = r.color_ramp.elements
    while len(el) > 1:
        el.remove(el[-1])
    el[0].position = stops[0][0]
    el[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = el.new(pos)
        e.color = col
    return r


def texcoord_map(nt, tile):
    """Object coordinates scaled so one texture tile = `tile` metres."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0 / tile, 1.0 / tile, 1.0 / tile)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    return mp


def load_image(aid, kind):
    p = os.path.join(TEX, aid, kind + ".jpg")
    if not os.path.exists(p):
        return None
    img = bpy.data.images.load(p, check_existing=True)
    if kind != "Diffuse":
        img.colorspace_settings.name = "Non-Color"
    return img


def tex_chain(nt, aid, tile, rough_mul=1.0, rough_add=0.0, normal_strength=0.4, ao_fac=0.55):
    """Return dict with 'col' / 'rough' / 'nor' sockets built from a CC0 set."""
    out = {}
    mp = texcoord_map(nt, tile)

    d = load_image(aid, "Diffuse")
    if d is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = d
        n.label = aid + " Diffuse"
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        out["col"] = n.outputs["Color"]

        ao = load_image(aid, "AO")
        if ao is not None:
            na = nt.nodes.new("ShaderNodeTexImage")
            na.image = ao
            na.label = aid + " AO"
            nt.links.new(mp.outputs["Vector"], na.inputs["Vector"])
            mx = mix_node(nt, "MULTIPLY", fac=ao_fac)
            nt.links.new(out["col"], mx.inputs["Color1"])
            nt.links.new(na.outputs["Color"], mx.inputs["Color2"])
            out["col"] = mx.outputs["Color"]

    r = load_image(aid, "Rough")
    if r is not None:
        nr = nt.nodes.new("ShaderNodeTexImage")
        nr.image = r
        nr.label = aid + " Rough"
        nt.links.new(mp.outputs["Vector"], nr.inputs["Vector"])
        if rough_mul != 1.0 or rough_add != 0.0:
            m = math_node(nt, "MULTIPLY_ADD")
            nt.links.new(nr.outputs["Color"], m.inputs[0])
            m.inputs[1].default_value = rough_mul
            m.inputs[2].default_value = rough_add
            out["rough"] = m.outputs[0]
        else:
            out["rough"] = nr.outputs["Color"]

    g = load_image(aid, "nor_gl")
    if g is not None:
        ng = nt.nodes.new("ShaderNodeTexImage")
        ng.image = g
        ng.label = aid + " Normal"
        nt.links.new(mp.outputs["Vector"], ng.inputs["Vector"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(ng.outputs["Color"], nm.inputs["Color"])
        out["nor"] = nm.outputs["Normal"]
    return out


def finish_colour(nt, col_sock, amount, wear, dirt=None):
    """City_Variation -> City_EdgeWear, returns the socket to feed Base Color."""
    gv = nt.nodes.new("ShaderNodeGroup")
    gv.node_tree = NG["City_Variation"]
    gv.label = "City_Variation"
    nt.links.new(col_sock, gv.inputs["Base"])
    gv.inputs["Amount"].default_value = amount

    ge = nt.nodes.new("ShaderNodeGroup")
    ge.node_tree = NG["City_EdgeWear"]
    ge.label = "City_EdgeWear"
    nt.links.new(gv.outputs["Result"], ge.inputs["Base"])
    ge.inputs["Wear"].default_value = wear
    if dirt is not None:
        ge.inputs["Dirt"].default_value = dirt
    return ge.outputs["Result"]


def make_bump(nt, src_socket, strength=0.15, distance=0.06):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(src_socket, b.inputs["Height"])
    return b


# --------------------------------------------------------------------------
# shared node groups
# --------------------------------------------------------------------------
NG = {}


def build_groups():
    # ---------------- City_Variation : Base + Amount ----------------------
    ng = bpy.data.node_groups.new("City_Variation", "ShaderNodeTree")
    sb = ng.interface.new_socket("Base", in_out="INPUT", socket_type="NodeSocketColor")
    sa = ng.interface.new_socket("Amount", in_out="INPUT", socket_type="NodeSocketFloat")
    ng.interface.new_socket("Result", in_out="OUTPUT", socket_type="NodeSocketColor")
    sb.default_value = (0.5, 0.5, 0.5, 1.0)
    sa.default_value = 0.15
    ni = ng.nodes.new("NodeGroupInput")
    no = ng.nodes.new("NodeGroupOutput")

    oi = ng.nodes.new("ShaderNodeObjectInfo")
    # t = random - 0.5
    sub = math_node(ng, "SUBTRACT")
    ng.links.new(oi.outputs["Random"], sub.inputs[0])
    sub.inputs[1].default_value = 0.5

    # hue shift = t * 0.12 * Amount
    h1 = math_node(ng, "MULTIPLY")
    ng.links.new(sub.outputs[0], h1.inputs[0])
    h1.inputs[1].default_value = 0.12
    h2 = math_node(ng, "MULTIPLY")
    ng.links.new(h1.outputs[0], h2.inputs[0])
    ng.links.new(ni.outputs["Amount"], h2.inputs[1])
    h3 = math_node(ng, "ADD")
    ng.links.new(h2.outputs[0], h3.inputs[0])
    h3.inputs[1].default_value = 0.5

    # value = 1 + t * Amount * 0.8
    v1 = math_node(ng, "MULTIPLY")
    ng.links.new(sub.outputs[0], v1.inputs[0])
    ng.links.new(ni.outputs["Amount"], v1.inputs[1])
    v2 = math_node(ng, "MULTIPLY")
    ng.links.new(v1.outputs[0], v2.inputs[0])
    v2.inputs[1].default_value = 0.8
    v3 = math_node(ng, "ADD")
    ng.links.new(v2.outputs[0], v3.inputs[0])
    v3.inputs[1].default_value = 1.0

    # saturation = 1 + t * Amount * 0.5
    s1 = math_node(ng, "MULTIPLY")
    ng.links.new(sub.outputs[0], s1.inputs[0])
    ng.links.new(ni.outputs["Amount"], s1.inputs[1])
    s2 = math_node(ng, "MULTIPLY")
    ng.links.new(s1.outputs[0], s2.inputs[0])
    s2.inputs[1].default_value = 0.5
    s3 = math_node(ng, "ADD")
    ng.links.new(s2.outputs[0], s3.inputs[0])
    s3.inputs[1].default_value = 1.0

    hs = ng.nodes.new("ShaderNodeHueSaturation")
    ng.links.new(ni.outputs["Base"], hs.inputs["Color"])
    ng.links.new(h3.outputs[0], hs.inputs["Hue"])
    ng.links.new(s3.outputs[0], hs.inputs["Saturation"])
    ng.links.new(v3.outputs[0], hs.inputs["Value"])
    hs.inputs["Fac"].default_value = 1.0
    ng.links.new(hs.outputs["Color"], no.inputs["Result"])
    NG["City_Variation"] = ng

    # ---------------- City_EdgeWear : Base + Wear + Dirt -------------------
    eg = bpy.data.node_groups.new("City_EdgeWear", "ShaderNodeTree")
    eb = eg.interface.new_socket("Base", in_out="INPUT", socket_type="NodeSocketColor")
    ew = eg.interface.new_socket("Wear", in_out="INPUT", socket_type="NodeSocketFloat")
    ed = eg.interface.new_socket("Dirt", in_out="INPUT", socket_type="NodeSocketColor")
    eg.interface.new_socket("Result", in_out="OUTPUT", socket_type="NodeSocketColor")
    eb.default_value = (0.5, 0.5, 0.5, 1.0)
    ew.default_value = 0.35
    ed.default_value = (0.055, 0.05, 0.045, 1.0)
    ei = eg.nodes.new("NodeGroupInput")
    eo = eg.nodes.new("NodeGroupOutput")

    tc = eg.nodes.new("ShaderNodeTexCoord")
    nz = noise_node(eg, scale=3.2, detail=6.0, rough=0.62)
    eg.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    rp = ramp_node(eg, [(0.34, (0, 0, 0, 1)), (0.72, (1, 1, 1, 1))])
    eg.links.new(nz.outputs["Fac"], rp.inputs["Fac"])

    # grime in cavities (AO inverted)
    ao = eg.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.6
    inv = math_node(eg, "SUBTRACT")
    inv.inputs[0].default_value = 1.0
    eg.links.new(ao.outputs["AO"], inv.inputs[1])
    cav = math_node(eg, "MULTIPLY")
    eg.links.new(inv.outputs[0], cav.inputs[0])
    cav.inputs[1].default_value = 0.55

    m1 = math_node(eg, "MULTIPLY")
    eg.links.new(rp.outputs["Color"], m1.inputs[0])
    eg.links.new(ei.outputs["Wear"], m1.inputs[1])
    m2 = math_node(eg, "MULTIPLY")
    eg.links.new(cav.outputs[0], m2.inputs[0])
    eg.links.new(ei.outputs["Wear"], m2.inputs[1])
    add = math_node(eg, "ADD", clamp=True)
    eg.links.new(m1.outputs[0], add.inputs[0])
    eg.links.new(m2.outputs[0], add.inputs[1])

    mx = mix_node(eg, "MIX")
    eg.links.new(add.outputs[0], mx.inputs["Fac"])
    eg.links.new(ei.outputs["Base"], mx.inputs["Color1"])
    eg.links.new(ei.outputs["Dirt"], mx.inputs["Color2"])
    eg.links.new(mx.outputs["Color"], eo.inputs["Result"])
    NG["City_EdgeWear"] = eg


# --------------------------------------------------------------------------
# procedural recipes  ->  (colour_socket, rough_socket, normal_socket|None)
# --------------------------------------------------------------------------
def p_flat(nt, s):
    col = rgb_node(nt, s["color"]).outputs[0]
    grain = s.get("grain", 0.10)
    n = noise_node(nt, scale=s.get("grain_scale", 7.0), detail=4.0)
    mr = math_node(nt, "MULTIPLY_ADD")
    nt.links.new(n.outputs["Fac"], mr.inputs[0])
    mr.inputs[1].default_value = grain
    mr.inputs[2].default_value = 1.0 - grain * 0.5
    mx = mix_node(nt, "MULTIPLY", fac=1.0)
    nt.links.new(col, mx.inputs["Color1"])
    nt.links.new(mr.outputs[0], mx.inputs["Color2"])
    col = mx.outputs["Color"]
    rough = s.get("rough", 0.6)
    nor = None
    if s.get("bump"):
        b = make_bump(nt, n.outputs["Fac"], strength=s["bump"])
        nor = b.outputs["Normal"]
    return col, val_node(nt, rough).outputs[0], nor


def p_stripe(nt, s):
    mp = texcoord_map(nt, s.get("tile", 1.4))
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.inputs["Scale"].default_value = s.get("stripes", 4.0)
    w.inputs["Distortion"].default_value = 0.0
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    rp = ramp_node(nt, [(0.48, s["c1"]), (0.52, s["c2"])])
    rp.color_ramp.interpolation = "CONSTANT"
    nt.links.new(w.outputs["Fac"], rp.inputs["Fac"])
    # fabric weave grain
    n = noise_node(nt, scale=45.0, detail=3.0)
    m = mix_node(nt, "MULTIPLY", fac=0.18)
    nt.links.new(rp.outputs["Color"], m.inputs["Color1"])
    nt.links.new(n.outputs["Color"], m.inputs["Color2"])
    b = make_bump(nt, w.outputs["Fac"], strength=0.25, distance=0.03)
    return m.outputs["Color"], val_node(nt, 0.75).outputs[0], b.outputs["Normal"]


def p_shingle(nt, s):
    mp = texcoord_map(nt, s.get("tile", 2.0))
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Color1"].default_value = s["c1"]
    br.inputs["Color2"].default_value = s["c2"]
    br.inputs["Mortar"].default_value = s.get("mortar", (0.03, 0.028, 0.026, 1))
    br.inputs["Mortar Size"].default_value = 0.02
    br.inputs["Row Height"].default_value = 0.16
    br.inputs["Brick Width"].default_value = 0.28
    nt.links.new(mp.outputs["Vector"], br.inputs["Vector"])
    n = noise_node(nt, scale=9.0, detail=5.0)
    m = mix_node(nt, "MULTIPLY", fac=0.35)
    nt.links.new(br.outputs["Color"], m.inputs["Color1"])
    nt.links.new(n.outputs["Color"], m.inputs["Color2"])
    b = make_bump(nt, br.outputs["Fac"], strength=0.45, distance=0.05)
    return m.outputs["Color"], val_node(nt, s.get("rough", 0.75)).outputs[0], b.outputs["Normal"]


def p_speckle(nt, s):
    """dark membrane with lighter aggregate speckles (bitumen / tarmac)."""
    col = rgb_node(nt, s["color"]).outputs[0]
    v = nt.nodes.new("ShaderNodeTexVoronoi")
    v.inputs["Scale"].default_value = s.get("scale", 60.0)
    rp = ramp_node(nt, [(0.10, (1, 1, 1, 1)), (0.16, (0, 0, 0, 1))])
    nt.links.new(v.outputs["Distance"], rp.inputs["Fac"])
    m = mix_node(nt, "SCREEN", fac=s.get("speckle", 0.28))
    nt.links.new(col, m.inputs["Color1"])
    nt.links.new(rp.outputs["Color"], m.inputs["Color2"])
    b = make_bump(nt, v.outputs["Distance"], strength=0.3, distance=0.02)
    return m.outputs["Color"], val_node(nt, s.get("rough", 0.85)).outputs[0], b.outputs["Normal"]


def p_brushed(nt, s):
    col = rgb_node(nt, s["color"]).outputs[0]
    mp = texcoord_map(nt, 0.5)
    mp.inputs["Scale"].default_value = (0.15, 40.0, 0.15)  # long streaks
    w = nt.nodes.new("ShaderNodeTexWave")
    w.inputs["Scale"].default_value = 6.0
    w.inputs["Distortion"].default_value = 6.0
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    mr = math_node(nt, "MULTIPLY_ADD")
    nt.links.new(w.outputs["Fac"], mr.inputs[0])
    mr.inputs[1].default_value = s.get("rough_var", 0.25)
    mr.inputs[2].default_value = s.get("rough", 0.3)
    return col, mr.outputs[0], None


def p_leaves(nt, s):
    n = noise_node(nt, scale=2.2, detail=6.0, rough=0.7)
    rp = ramp_node(nt, [(0.30, s["c1"]), (0.55, s["c2"]), (0.80, s["c3"])])
    nt.links.new(n.outputs["Fac"], rp.inputs["Fac"])
    fine = noise_node(nt, scale=26.0, detail=3.0)
    b = make_bump(nt, fine.outputs["Fac"], strength=0.35, distance=0.02)
    return rp.outputs["Color"], val_node(nt, 0.68).outputs[0], b.outputs["Normal"]


def p_bark(nt, s):
    mp = texcoord_map(nt, 1.0)
    mp.inputs["Scale"].default_value = (3.0, 3.0, 0.35)  # stretched vertically
    n = noise_node(nt, scale=6.0, detail=8.0, rough=0.75)
    nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
    rp = ramp_node(nt, [(0.30, s["c1"]), (0.55, s["c2"]), (0.78, s["c3"])])
    nt.links.new(n.outputs["Fac"], rp.inputs["Fac"])
    b = make_bump(nt, n.outputs["Fac"], strength=0.7, distance=0.08)
    return rp.outputs["Color"], val_node(nt, 0.9).outputs[0], b.outputs["Normal"]


def p_water(nt, s):
    mp = texcoord_map(nt, 6.0)
    n = noise_node(nt, scale=3.0, detail=6.0, rough=0.55)
    nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
    b = make_bump(nt, n.outputs["Fac"], strength=0.18, distance=0.10)
    return rgb_node(nt, s["color"]).outputs[0], val_node(nt, 0.03).outputs[0], b.outputs["Normal"]


def p_glass(nt, s):
    n = noise_node(nt, scale=2.0, detail=3.0)
    m = mix_node(nt, "MULTIPLY", fac=0.12)
    nt.links.new(rgb_node(nt, s["color"]).outputs[0], m.inputs["Color1"])
    nt.links.new(n.outputs["Color"], m.inputs["Color2"])
    return m.outputs["Color"], val_node(nt, s.get("rough", 0.05)).outputs[0], None


RECIPE = {
    "flat": p_flat, "stripe": p_stripe, "shingle": p_shingle, "speckle": p_speckle,
    "brushed": p_brushed, "leaves": p_leaves, "bark": p_bark, "water": p_water,
    "glass": p_glass,
}

# --------------------------------------------------------------------------
# material specifications
#   tex   : PolyHaven texture set id (Diffuse/nor_gl/Rough/AO)
#   tile  : metres covered by one texture tile (target 4 m = 256 px/m)
#   rough : roughness when procedural   /  rough_mul, rough_add when textured
#   var   : City_Variation Amount       /  wear : City_EdgeWear Wear factor
#   emis  : (colour, strength)  -> flagged "emissive": true in materials.json
# --------------------------------------------------------------------------
GROUND, VEGG, FACADE, METAL, ROOF, TIMBER, INTER, SIGN, VEG, UTIL = (
    "ground/road", "vegetation ground", "facade", "glass/metal", "roof",
    "timber", "interior", "signage/emissive", "vegetation", "utility")

SPEC = {
    # ---- ground / road -------------------------------------------------
    "asphalt":            dict(cat=GROUND, tex="asphalt_01", tile=8, rough=0.92, rough_mul=0.5, rough_add=0.6, wear=0.6, var=0.08, nor=0.35),
    "asphalt_worn":       dict(cat=GROUND, tex="worn_asphalt", tile=8, rough=0.95, rough_mul=0.5, rough_add=0.6, wear=0.75, var=0.10, nor=0.45),
    "asphalt_highway":    dict(cat=GROUND, tex="asphalt_02", tile=8, rough=0.88, rough_mul=0.5, rough_add=0.55, wear=0.5, var=0.06, nor=0.3),
    "track_asphalt":      dict(cat=GROUND, tex="asphalt_track", tile=6, rough=0.8, rough_mul=0.5, rough_add=0.5, wear=0.4, var=0.05, nor=0.3),
    "marking_white":      dict(cat=GROUND, color=hexc("#EDEDE6"), rough=0.5, grain=0.05, wear=0.55, var=0.05),
    "marking_yellow":     dict(cat=GROUND, color=hexc("#E8B33A"), rough=0.5, grain=0.05, wear=0.55, var=0.05),
    "curb_concrete":      dict(cat=GROUND, tex="concrete_floor_01", tile=3, tint=hexc("#C9CBC6"), rough=0.85, rough_mul=0.4, rough_add=0.6, wear=0.55, var=0.10, nor=0.3),
    "kerb_red":           dict(cat=GROUND, tex="concrete_floor_01", tile=3, tint=hexc("#B8402F"), rough=0.7, rough_mul=0.4, rough_add=0.5, wear=0.6, var=0.10, nor=0.25),
    "kerb_white":         dict(cat=GROUND, tex="concrete_floor_01", tile=3, tint=hexc("#E4E4DE"), rough=0.7, rough_mul=0.4, rough_add=0.5, wear=0.6, var=0.10, nor=0.25),
    "kerb_yellow":        dict(cat=GROUND, tex="concrete_floor_01", tile=3, tint=hexc("#DDB13A"), rough=0.7, rough_mul=0.4, rough_add=0.5, wear=0.6, var=0.10, nor=0.25),
    "sidewalk_concrete":  dict(cat=GROUND, tex="concrete_floor_01", tile=4, tint=hexc("#CFD1CC"), rough=0.88, rough_mul=0.4, rough_add=0.62, wear=0.5, var=0.12, nor=0.3),
    "paving_slab":        dict(cat=GROUND, tex="concrete_tiles", tile=4, tint=hexc("#C6C7C2"), rough=0.85, rough_mul=0.4, rough_add=0.6, wear=0.5, var=0.12, nor=0.35),
    "cobble_stone":       dict(cat=GROUND, tex="cobblestone_floor_05", tile=3, tint=hexc("#B9B2A6"), rough=0.8, rough_mul=0.5, rough_add=0.5, wear=0.6, var=0.14, nor=0.55),
    "gravel":             dict(cat=GROUND, tex="bicolour_gravel", tile=4, rough=0.95, rough_mul=0.5, rough_add=0.6, wear=0.7, var=0.12, nor=0.6),
    "dirt":               dict(cat=GROUND, tex="dirt_floor", tile=4, tint=hexc("#C0AE96"), rough=0.95, rough_mul=0.5, rough_add=0.6, wear=0.7, var=0.12, nor=0.5),
    "sand":               dict(cat=GROUND, recipe="flat", color=hexc("#D9C79C"), rough=0.95, grain=0.12, grain_scale=14, bump=0.35, wear=0.6, var=0.10),

    # ---- vegetation ground --------------------------------------------
    "grass":              dict(cat=VEGG, tex="grass_ground", tile=4, tint=hexc("#9FBF72"), rough=0.9, rough_mul=0.4, rough_add=0.6, wear=0.4, var=0.16, nor=0.5),
    "grass_dry":          dict(cat=VEGG, tex="grass_ground", tile=4, tint=hexc("#D6C183"), rough=0.92, rough_mul=0.4, rough_add=0.6, wear=0.5, var=0.16, nor=0.5),

    # ---- facade --------------------------------------------------------
    "brick_red":          dict(cat=FACADE, tex="brick_wall_001", tile=2, rough=0.9, rough_mul=0.5, rough_add=0.55, wear=0.35, var=0.14, nor=0.6),
    "brick_brown":        dict(cat=FACADE, tex="brown_brick_02", tile=2, rough=0.9, rough_mul=0.5, rough_add=0.55, wear=0.4, var=0.14, nor=0.6),
    "brick_whitewash":    dict(cat=FACADE, tex="castle_brick_02_white", tile=2, tint=hexc("#EFEAE0"), rough=0.85, rough_mul=0.5, rough_add=0.5, wear=0.4, var=0.12, nor=0.55),
    "plaster_white":      dict(cat=FACADE, tex="painted_plaster_wall", tile=4, tint=hexc("#EDEAE2"), rough=0.8, rough_mul=0.4, rough_add=0.55, wear=0.3, var=0.10, nor=0.3),
    "plaster_cream":      dict(cat=FACADE, tex="painted_plaster_wall", tile=4, tint=hexc("#E6D6B4"), rough=0.8, rough_mul=0.4, rough_add=0.55, wear=0.3, var=0.12, nor=0.3),
    "plaster_ochre":      dict(cat=FACADE, tex="painted_plaster_wall", tile=4, tint=hexc("#D8A85E"), rough=0.8, rough_mul=0.4, rough_add=0.55, wear=0.35, var=0.12, nor=0.3),
    "stucco_grey":        dict(cat=FACADE, tex="grey_plaster_02", tile=4, tint=hexc("#BFBFB8"), rough=0.85, rough_mul=0.4, rough_add=0.6, wear=0.3, var=0.10, nor=0.35),
    "stone_grey":         dict(cat=FACADE, tex="stone_wall", tile=4, tint=hexc("#B4B4AE"), rough=0.85, rough_mul=0.4, rough_add=0.6, wear=0.4, var=0.12, nor=0.6),
    "marble_white":       dict(cat=FACADE, tex="marble_01", tile=4, tint=hexc("#F2F1EC"), rough=0.18, rough_mul=0.25, rough_add=0.1, wear=0.2, var=0.06, nor=0.25),
    "concrete":           dict(cat=FACADE, tex="concrete_floor_01", tile=4, tint=hexc("#C2C3BE"), rough=0.85, rough_mul=0.4, rough_add=0.6, wear=0.35, var=0.10, nor=0.3),
    "concrete_poured":    dict(cat=FACADE, recipe="flat", color=hexc("#B7B8B4"), rough=0.8, grain=0.10, grain_scale=11, bump=0.12, wear=0.3, var=0.10),
    "wall_paint":         dict(cat=FACADE, recipe="flat", color=hexc("#E8E2D6"), rough=0.62, grain=0.05, grain_scale=16, bump=0.05, wear=0.15, var=0.10),
    "ceiling_paint":      dict(cat=FACADE, recipe="flat", color=hexc("#F2F1EC"), rough=0.9, grain=0.03, grain_scale=16, bump=0.0, wear=0.1, var=0.05),

    # ---- glass / metal --------------------------------------------------
    "glass_office":       dict(cat=METAL, recipe="glass", color=hexc("#4E6E8C"), rough=0.06, alpha=0.45, wear=0.1, var=0.05),
    "glass_shop":         dict(cat=METAL, recipe="glass", color=hexc("#DCE6EA"), rough=0.03, alpha=0.30, wear=0.1, var=0.05),
    "glass_dark":         dict(cat=METAL, recipe="glass", color=hexc("#1B2026"), rough=0.05, alpha=0.72, wear=0.1, var=0.05),
    "metal_steel":        dict(cat=METAL, recipe="brushed", color=hexc("#9AA0A6"), rough=0.34, rough_var=0.22, metal=1.0, wear=0.3, var=0.08),
    "metal_chrome":       dict(cat=METAL, recipe="brushed", color=hexc("#D8DCE0"), rough=0.09, rough_var=0.06, metal=1.0, wear=0.15, var=0.05),
    "metal_painted_dark": dict(cat=METAL, recipe="flat", color=hexc("#14161A"), rough=0.45, grain=0.06, grain_scale=20, bump=0.05, metal=0.35, wear=0.3, var=0.10),
    "metal_rusty":        dict(cat=METAL, tex="rusty_metal", tile=3, rough=0.85, rough_mul=0.5, rough_add=0.5, metal=0.35, wear=0.7, var=0.14, nor=0.55),
    "rust":               dict(cat=METAL, tex="rusty_metal", tile=2, tint=hexc("#C4703A"), rough=0.9, rough_mul=0.4, rough_add=0.55, metal=0.1, wear=0.8, var=0.16, nor=0.6),

    # ---- roof -----------------------------------------------------------
    "roof_tile_red":      dict(cat=ROOF, tex="clay_roof_tiles", tile=2, tint=hexc("#D9A184"), rough=0.8, rough_mul=0.4, rough_add=0.55, wear=0.4, var=0.14, nor=0.7),
    "roof_metal":         dict(cat=ROOF, tex="corrugated_iron", tile=3, tint=hexc("#B7BAB6"), rough=0.55, rough_mul=0.4, rough_add=0.4, metal=0.7, wear=0.5, var=0.12, nor=0.7),
    "roof_bitumen":       dict(cat=ROOF, recipe="speckle", color=hexc("#3A3C3E"), scale=70, speckle=0.30, rough=0.85, wear=0.5, var=0.10),
    "roof_shingle":       dict(cat=ROOF, recipe="shingle", c1=hexc("#4C433C"), c2=hexc("#3B332E"), tile=2, rough=0.8, wear=0.4, var=0.14),

    # ---- timber ---------------------------------------------------------
    "wood_old":           dict(cat=TIMBER, tex="wood_planks", tile=2, tint=hexc("#C8B79C"), rough=0.75, rough_mul=0.5, rough_add=0.4, wear=0.5, var=0.14, nor=0.5),
    "wood_painted":       dict(cat=TIMBER, tex="wood_planks", tile=2, tint=hexc("#EFEAE0"), rough=0.45, rough_mul=0.3, rough_add=0.35, wear=0.35, var=0.10, nor=0.35),
    "bark":               dict(cat=TIMBER, recipe="bark", c1=hexc("#2E2318"), c2=hexc("#4A3826"), c3=hexc("#6A5640"), rough=0.9, wear=0.3, var=0.16),

    # ---- interior -------------------------------------------------------
    "floor_wood":         dict(cat=INTER, tex="wooden_floor_01", tile=3, rough=0.4, rough_mul=0.3, rough_add=0.25, wear=0.2, var=0.12, nor=0.4),
    "floor_tile":         dict(cat=INTER, tex="floor_tiles_02", tile=3, rough=0.3, rough_mul=0.3, rough_add=0.2, wear=0.2, var=0.10, nor=0.35),
    "floor_carpet":       dict(cat=INTER, tex="dirty_carpet", tile=3, tint=hexc("#B9B0A4"), rough=0.95, rough_mul=0.3, rough_add=0.68, wear=0.2, var=0.14, nor=0.4),

    # ---- signage / fabric / emissive -----------------------------------
    "sign_metal":         dict(cat=SIGN, recipe="brushed", color=hexc("#C7CBCF"), rough=0.3, rough_var=0.15, metal=0.9, wear=0.3, var=0.10),
    "awning_fabric_red":  dict(cat=SIGN, recipe="flat", color=hexc("#B93B2C"), rough=0.8, grain=0.10, grain_scale=55, bump=0.3, wear=0.4, var=0.14),
    "awning_fabric_green": dict(cat=SIGN, recipe="flat", color=hexc("#2F4A3C"), rough=0.8, grain=0.10, grain_scale=55, bump=0.3, wear=0.4, var=0.14),
    "awning_fabric_stripe": dict(cat=SIGN, recipe="stripe", c1=hexc("#D9D6CE"), c2=hexc("#B93B2C"), tile=1.6, stripes=4.0, rough=0.8, wear=0.4, var=0.10),
    "canvas_tarp":        dict(cat=SIGN, recipe="flat", color=hexc("#8E948C"), rough=0.85, grain=0.12, grain_scale=40, bump=0.35, wear=0.6, var=0.14),
    "neon_red":           dict(cat=SIGN, recipe="flat", color=hexc("#FF2A1A"), rough=0.3, grain=0.02, emis=(hexc("#FF3B22"), 2.0), wear=0.1, var=0.04),
    "neon_blue":          dict(cat=SIGN, recipe="flat", color=hexc("#29B6F6"), rough=0.3, grain=0.02, emis=(hexc("#2FC2FF"), 2.0), wear=0.1, var=0.04),
    "neon_green":         dict(cat=SIGN, recipe="flat", color=hexc("#3BDB6E"), rough=0.3, grain=0.02, emis=(hexc("#3BE877"), 2.0), wear=0.1, var=0.04),
    "neon_pink":          dict(cat=SIGN, recipe="flat", color=hexc("#FF4FC3"), rough=0.3, grain=0.02, emis=(hexc("#FF57C8"), 2.0), wear=0.1, var=0.04),
    "emissive_warm":      dict(cat=SIGN, recipe="flat", color=hexc("#FFE7B8"), rough=0.5, grain=0.04, emis=(hexc("#FFD79A"), 1.5), wear=0.1, var=0.06),
    "emissive_cool":      dict(cat=SIGN, recipe="flat", color=hexc("#EAF3FF"), rough=0.5, grain=0.04, emis=(hexc("#DCEBFF"), 1.5), wear=0.1, var=0.06),
    "water":              dict(cat=SIGN, recipe="water", color=hexc("#16323A"), rough=0.03, wear=0.1, var=0.06),

    # ---- vegetation -----------------------------------------------------
    "leaves_green":       dict(cat=VEG, recipe="leaves", c1=hexc("#2E5A2A"), c2=hexc("#4C7C33"), c3=hexc("#6E9A3E"), rough=0.7, wear=0.2, var=0.22),
    "leaves_dark":        dict(cat=VEG, recipe="leaves", c1=hexc("#16301D"), c2=hexc("#25462A"), c3=hexc("#33583A"), rough=0.72, wear=0.2, var=0.20),

    # ---- utility --------------------------------------------------------
    "col_placeholder":    dict(cat=UTIL, recipe="flat", color=hexc("#FF00FF"), rough=0.6, grain=0.02, wear=0.0, var=0.0),
}

GROUPING = [GROUND, VEGG, FACADE, METAL, ROOF, TIMBER, INTER, SIGN, VEG, UTIL]
GROUP_HEADERS = {
    GROUND: "GROUND / ROAD", VEGG: "VEGETATION GROUND", FACADE: "FACADE / WALL",
    METAL: "GLASS / METAL", ROOF: "ROOF", TIMBER: "TIMBER", INTER: "INTERIOR",
    SIGN: "SIGNAGE / EMISSIVE", VEG: "VEGETATION", UTIL: "UTILITY",
}


# --------------------------------------------------------------------------
# builder
# --------------------------------------------------------------------------
def build_material(name, s):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    clear_nodes(nt)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.label = name
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    recipe = s.get("recipe")
    col = rough = nor = None

    if s.get("tex"):
        tc = tex_chain(nt, s["tex"], s.get("tile", 4.0),
                       rough_mul=s.get("rough_mul", 1.0),
                       rough_add=s.get("rough_add", 0.0),
                       normal_strength=s.get("nor", 0.4))
        col = tc.get("col")
        if col is None:
            col = rgb_node(nt, hexc("#808080")).outputs[0]
        if s.get("tint"):
            mx = mix_node(nt, "MULTIPLY", fac=1.0)
            nt.links.new(col, mx.inputs["Color1"])
            nt.links.new(rgb_node(nt, s["tint"]).outputs[0], mx.inputs["Color2"])
            col = mx.outputs["Color"]
        rough = tc.get("rough")
        nor = tc.get("nor")
    elif recipe:
        col, rough, nor = RECIPE[recipe](nt, s)
    else:
        col, rough, nor = p_flat(nt, s)

    base = finish_colour(nt, col, s.get("var", 0.12), s.get("wear", 0.3))
    nt.links.new(base, bsdf.inputs["Base Color"])

    if rough is None:
        rough = val_node(nt, s.get("rough", 0.6)).outputs[0]
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bsdf.inputs["Metallic"].default_value = s.get("metal", 0.0)
    bsdf.inputs["IOR"].default_value = s.get("ior", 1.45)

    if nor is not None:
        nt.links.new(nor, bsdf.inputs["Normal"])

    if s.get("emis"):
        ecol, estr = s["emis"]
        bsdf.inputs["Emission Color"].default_value = ecol
        bsdf.inputs["Emission Strength"].default_value = estr

    if s.get("alpha") is not None:
        bsdf.inputs["Alpha"].default_value = s["alpha"]
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
        try:
            mat.blend_method = "BLEND"
        except Exception:
            pass
    return mat


def build_partner_groups():
    """Recreate the two shared node groups documented in style_bible.md §4
    (NG_ColorVariation / NG_EdgeWear_Dirt) so both name sets stay usable from
    materials.blend. Already-present groups are left untouched."""
    # ---------------- NG_ColorVariation : Base Color + Variation + Seed -----
    if "NG_ColorVariation" not in bpy.data.node_groups:
        g = bpy.data.node_groups.new("NG_ColorVariation", "ShaderNodeTree")
        for nm, typ, dv, lo, hi in (
                ("Base Color", "NodeSocketColor", (0.5, 0.5, 0.5, 1.0), None, None),
                ("Variation", "NodeSocketFloat", 0.12, 0.0, 0.5),
                ("Seed", "NodeSocketFloat", 0.0, 0.0, 10.0)):
            s = g.interface.new_socket(nm, in_out="INPUT", socket_type=typ)
            s.default_value = dv
            if lo is not None:
                s.min_value, s.max_value = lo, hi
        g.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
        gi = g.nodes.new("NodeGroupInput")
        go = g.nodes.new("NodeGroupOutput")
        oi = g.nodes.new("ShaderNodeObjectInfo")
        # t = fract(random * 7.13 + seed * 0.37) - 0.5   (Seed lets neighbours differ)
        m1 = math_node(g, "MULTIPLY"); g.links.new(oi.outputs["Random"], m1.inputs[0])
        m1.inputs[1].default_value = 7.13
        m2 = math_node(g, "MULTIPLY"); g.links.new(gi.outputs["Seed"], m2.inputs[0])
        m2.inputs[1].default_value = 0.37
        ad = math_node(g, "ADD"); g.links.new(m1.outputs[0], ad.inputs[0])
        g.links.new(m2.outputs[0], ad.inputs[1])
        fr = math_node(g, "FRACT"); g.links.new(ad.outputs[0], fr.inputs[0])
        sb = math_node(g, "SUBTRACT"); g.links.new(fr.outputs[0], sb.inputs[0])
        sb.inputs[1].default_value = 0.5
        # hue = 0.5 + t * Variation * 0.02  (±3.6 deg at Variation = 1)
        h1 = math_node(g, "MULTIPLY"); g.links.new(sb.outputs[0], h1.inputs[0])
        g.links.new(gi.outputs["Variation"], h1.inputs[1])
        h2 = math_node(g, "MULTIPLY"); g.links.new(h1.outputs[0], h2.inputs[0])
        h2.inputs[1].default_value = 0.02
        h3 = math_node(g, "ADD"); g.links.new(h2.outputs[0], h3.inputs[0])
        h3.inputs[1].default_value = 0.5
        # value = 1 + t * Variation * 0.6
        v1 = math_node(g, "MULTIPLY"); g.links.new(sb.outputs[0], v1.inputs[0])
        g.links.new(gi.outputs["Variation"], v1.inputs[1])
        v2 = math_node(g, "MULTIPLY"); g.links.new(v1.outputs[0], v2.inputs[0])
        v2.inputs[1].default_value = 0.6
        v3 = math_node(g, "ADD"); g.links.new(v2.outputs[0], v3.inputs[0])
        v3.inputs[1].default_value = 1.0
        hs = g.nodes.new("ShaderNodeHueSaturation")
        g.links.new(gi.outputs["Base Color"], hs.inputs["Color"])
        g.links.new(h3.outputs[0], hs.inputs["Hue"])
        g.links.new(v3.outputs[0], hs.inputs["Value"])
        hs.inputs["Fac"].default_value = 1.0
        hs.inputs["Saturation"].default_value = 1.0
        g.links.new(hs.outputs["Color"], go.inputs["Color"])
        print("  built NG_ColorVariation")

    # ---------------- NG_EdgeWear_Dirt : colour + roughness ------------------
    if "NG_EdgeWear_Dirt" not in bpy.data.node_groups:
        g = bpy.data.node_groups.new("NG_EdgeWear_Dirt", "ShaderNodeTree")
        for nm, typ, dv, lo, hi in (
                ("Base Color", "NodeSocketColor", (0.5, 0.5, 0.5, 1.0), None, None),
                ("Roughness", "NodeSocketFloat", 0.7, 0.0, 1.0),
                ("Wear", "NodeSocketFloat", 0.35, 0.0, 1.0),
                ("Dirt", "NodeSocketFloat", 0.4, 0.0, 1.0),
                ("Dirt Color", "NodeSocketColor", (0.06, 0.055, 0.05, 1.0), None, None),
                ("Scale", "NodeSocketFloat", 2.0, 0.25, 32.0)):
            s = g.interface.new_socket(nm, in_out="INPUT", socket_type=typ)
            s.default_value = dv
            if lo is not None:
                s.min_value, s.max_value = lo, hi
        g.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
        g.interface.new_socket("Roughness", in_out="OUTPUT", socket_type="NodeSocketFloat")
        gi = g.nodes.new("NodeGroupInput")
        go = g.nodes.new("NodeGroupOutput")

        tc = g.nodes.new("ShaderNodeTexCoord")
        inv = math_node(g, "DIVIDE"); inv.inputs[0].default_value = 1.0
        g.links.new(gi.outputs["Scale"], inv.inputs[1])
        mp = g.nodes.new("ShaderNodeMapping")
        g.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        g.links.new(inv.outputs[0], mp.inputs["Scale"])

        # dirt: big patches, biased to up-facing surfaces
        nd = noise_node(g, scale=3.0, detail=6.0, rough=0.62)
        g.links.new(mp.outputs["Vector"], nd.inputs["Vector"])
        rd = ramp_node(g, [(0.35, (0, 0, 0, 1)), (0.75, (1, 1, 1, 1))])
        g.links.new(nd.outputs["Fac"], rd.inputs["Fac"])
        geo = g.nodes.new("ShaderNodeNewGeometry")
        sep = g.nodes.new("ShaderNodeSeparateXYZ")
        g.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
        up = math_node(g, "MAXIMUM"); g.links.new(sep.outputs["Z"], up.inputs[0])
        up.inputs[1].default_value = 0.0
        dm1 = math_node(g, "MULTIPLY"); g.links.new(rd.outputs["Color"], dm1.inputs[0])
        g.links.new(up.outputs[0], dm1.inputs[1])
        dm2 = math_node(g, "MULTIPLY"); g.links.new(dm1.outputs[0], dm2.inputs[0])
        g.links.new(gi.outputs["Dirt"], dm2.inputs[1])

        # wear: fine noise, sun-bleach
        nw = noise_node(g, scale=14.0, detail=4.0, rough=0.7)
        g.links.new(mp.outputs["Vector"], nw.inputs["Vector"])
        rw = ramp_node(g, [(0.55, (0, 0, 0, 1)), (0.85, (1, 1, 1, 1))])
        g.links.new(nw.outputs["Fac"], rw.inputs["Fac"])
        wm = math_node(g, "MULTIPLY"); g.links.new(rw.outputs["Color"], wm.inputs[0])
        g.links.new(gi.outputs["Wear"], wm.inputs[1])

        bleach = g.nodes.new("ShaderNodeHueSaturation")
        g.links.new(gi.outputs["Base Color"], bleach.inputs["Color"])
        bleach.inputs["Hue"].default_value = 0.5
        bleach.inputs["Saturation"].default_value = 0.9
        bleach.inputs["Value"].default_value = 1.25
        g.links.new(wm.outputs[0], bleach.inputs["Fac"])

        dirt_mix = mix_node(g, "MIX")
        g.links.new(bleach.outputs["Color"], dirt_mix.inputs["Color1"])
        g.links.new(gi.outputs["Dirt Color"], dirt_mix.inputs["Color2"])
        g.links.new(dm2.outputs[0], dirt_mix.inputs["Fac"])
        g.links.new(dirt_mix.outputs["Color"], go.inputs["Color"])

        # roughness: dirt +0.2, wear -0.1
        r1 = math_node(g, "MULTIPLY_ADD"); g.links.new(dm2.outputs[0], r1.inputs[0])
        r1.inputs[1].default_value = 0.2
        g.links.new(gi.outputs["Roughness"], r1.inputs[2])
        r2 = math_node(g, "MULTIPLY_ADD"); g.links.new(wm.outputs[0], r2.inputs[0])
        r2.inputs[1].default_value = -0.1
        g.links.new(r1.outputs[0], r2.inputs[2])
        r3 = math_node(g, "MULTIPLY_ADD", clamp=True); g.links.new(r2.outputs[0], r3.inputs[0])
        r3.inputs[1].default_value = 1.0
        r3.inputs[2].default_value = 0.0
        g.links.new(r3.outputs[0], go.inputs["Roughness"])
        print("  built NG_EdgeWear_Dirt")


def absorb_existing():
    """Append every material / node group already present in the on-disk library.

    Two authoring passes write to materials.blend; absorbing whatever is currently on
    disk means neither pass erases the other's names. Returns the list of absorbed
    material names.
    """
    if not os.path.isfile(OUT_BLEND):
        return []
    size = os.path.getsize(OUT_BLEND)
    if size > 700 * 1024 * 1024:
        print("  ! on-disk library is %.0f MB — skipping absorb to stay in RAM" % (size / 1e6))
        return []
    mine_groups = ("City_EdgeWear", "City_Variation")
    try:
        with bpy.data.libraries.load(OUT_BLEND, link=False) as (src, dst):
            have = set(bpy.data.materials.keys())
            own = set(SPEC.keys())
            # never pull this pass's own names back in (they are rebuilt below, and
            # their dependencies would arrive as .001 duplicate node groups)
            dst.materials = [n for n in src.materials
                             if n and n not in have and n != "Material" and n not in own]
            dst.node_groups = [n for n in src.node_groups if n and n not in mine_groups]
    except Exception as e:
        print("  ! could not absorb on-disk library (%s)" % e)
        return []
    got = [m.name for m in bpy.data.materials]
    if got:
        print("  absorbed %d foreign materials: %s..." % (len(got), ", ".join(sorted(got)[:6])))
    return sorted(got)


def main():
    global NG
    print("== materials_lib: building library ==")
    # start from a completely empty file
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for _ in range(3):
        try:
            bpy.data.orphans_purge(do_recursive=True)
        except Exception:
            break

    build_groups()
    build_partner_groups()
    absorbed = absorb_existing()

    names = []
    for cat in GROUPING:
        for n, s in SPEC.items():
            if s["cat"] != cat:
                continue
            if n in bpy.data.materials:      # name collision with the other pass
                print("  (replacing absorbed copy of %s)" % n)
                bpy.data.materials.remove(bpy.data.materials[n])
            build_material(n, s)
            names.append(n)

    # ---- cleanup: no default "Material", no strays -----------------------
    for m in list(bpy.data.materials):
        if m.name not in names and m.name == "Material":
            print("  removing stray material:", m.name)
            bpy.data.materials.remove(m)
    for ng in list(bpy.data.node_groups):
        # keep the shared groups of this pass AND any absorbed from the other pass;
        # drop only anonymous leftovers and stale .001 duplicates
        if ng.name in ("NodeGroup", "") or (ng.name.endswith(".001") and ng.users == 0):
            print("  removing stray node group:", ng.name)
            bpy.data.node_groups.remove(ng)
    # zero-user datablocks: give them a fake user so they survive save/load
    for m in bpy.data.materials:
        m.use_fake_user = True
    for ng in bpy.data.node_groups:
        ng.use_fake_user = True
    for img in bpy.data.images:
        if img.source == "FILE":
            img.use_fake_user = True

    # ---- pack images so materials.blend is self contained ----------------
    packed = 0
    for img in bpy.data.images:
        if img.source == "FILE" and not img.packed_file:
            try:
                img.pack()
                packed += 1
            except Exception as e:
                print("  pack failed", img.name, e)

    # ---- write index ------------------------------------------------------
    emissive = [n for n in names if SPEC[n].get("emis")]
    absorbed_final = sorted(n for n in bpy.data.materials.keys() if n not in names)
    detail = {}
    for n in names:
        s = SPEC[n]
        detail[n] = {
            "category": s["cat"],
            "emissive": bool(s.get("emis")),
            "emission_strength": s["emis"][1] if s.get("emis") else 0.0,
            "alpha": s.get("alpha"),
            "metallic": s.get("metal", 0.0),
            "texture_set": s.get("tex"),
            "wear": s.get("wear", 0.3),
            "variation": s.get("var", 0.12),
            "tile_m": s.get("tile", 4.0),
        }
    index = {
        "version": 1,
        "materials": names,
        "node_groups": sorted(g.name for g in bpy.data.node_groups),
        "emissive": emissive,
        "absorbed": absorbed_final,
        "absorbed_node_groups": sorted(n for n in bpy.data.node_groups.keys()
                                       if n not in ("City_EdgeWear", "City_Variation")),
        "groups": {GROUP_HEADERS[c]: [n for n in names if SPEC[n]["cat"] == c] for c in GROUPING},
        "detail": detail,
        "texel_density": "1024px per 4m (256 px/m); roads 8m per tile",
    }
    index["all_materials"] = sorted(set(names) | set(absorbed))
    with open(OUT_JSON, "w") as f:
        json.dump(index, f, indent=1)

    # ---- save -------------------------------------------------------------
    # Absorbing another authoring pass registers its file as a library in this
    # session, which makes Blender refuse to overwrite the same path — so save
    # beside it and atomically swap the file in.
    tmp_path = OUT_BLEND + ".new"
    try:
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
    except Exception as e:
        print("  direct save refused (%s) — saving to temp and swapping" % e)
        print("  libraries in session:", [l.filepath for l in bpy.data.libraries])
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        bpy.ops.wm.save_as_mainfile(filepath=tmp_path, compress=True)
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 1024:
            raise RuntimeError("temp save failed: %s" % tmp_path)
        os.replace(tmp_path, OUT_BLEND)
        print("  swapped %s in" % OUT_BLEND)

    print("== DONE ==")
    print("  materials :", len(names), "(index len", len(index["materials"]), ")")
    print("  absorbed  :", len(absorbed_final), "extra names from the parallel pass")
    print("  total     :", len(bpy.data.materials), "materials in the blend")
    print("  emissive  :", len(emissive), emissive)
    print("  groups    :", index["node_groups"])
    print("  images    :", len(bpy.data.images), "packed:", packed)
    print("  wrote     :", OUT_BLEND, "(%.1f MB)" % (os.path.getsize(OUT_BLEND) / 1e6))
    print("  wrote     :", OUT_JSON)
    # verify every contract name exists
    required = """asphalt asphalt_worn asphalt_highway marking_white marking_yellow curb_concrete
        sidewalk_concrete paving_slab cobble_stone gravel dirt grass grass_dry track_asphalt kerb_red
        kerb_white brick_red brick_brown brick_whitewash plaster_white plaster_cream plaster_ochre
        stucco_grey stone_grey marble_white concrete concrete_poured glass_office glass_shop glass_dark
        metal_steel metal_painted_dark metal_rusty wood_old wood_painted roof_tile_red roof_metal
        roof_bitumen roof_shingle floor_wood floor_tile floor_carpet wall_paint ceiling_paint sign_metal
        awning_fabric_red awning_fabric_green awning_fabric_stripe canvas_tarp neon_red neon_blue
        neon_green neon_pink emissive_warm emissive_cool leaves_green leaves_dark bark rust
        col_placeholder""".split()
    missing = [r for r in required if r not in names]
    extra = [n for n in names if n not in required]
    print("  required  :", len(required), "missing:", missing)
    print("  extra     :", len(extra), extra)
    if missing:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
