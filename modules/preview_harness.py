"""Preview harness for city preview repair.

Opens a blend READ-ONLY (never saves), adds temp camera + temp ground + temp sun/world,
renders EEVEE 1920x1080, computes pixel stddev (+ magenta fraction), retries blank shots,
cleans up temps.  Never modifies or saves the source blend.

Usage: blender -b --factory-startup -P run_<tag>.py   (sys.path includes /city so
       you can `from modules import preview_harness as H`).
"""
import bpy, math, os, json, shutil
import numpy as np
from mathutils import Vector

ROOT = "/home/abdulhadi/Work/city"
OUT = os.path.join(ROOT, "out")
METRICS = "/tmp/opencode/prevfix/metrics"
GEOM = {"MESH", "CURVE", "SURFACE", "META", "FONT", "POINTCLOUD", "VOLUME", "HAIR"}
os.makedirs(METRICS, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

_created = []      # temp object names we added
_orig_hide = []    # (obj, hide_render) toggled for colliders

BLANK_STDDEV = 0.02

# ---------------------------------------------------------------- basics
def open_blend(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    _created.clear(); _orig_hide.clear()
    for coll in bpy.data.collections:
        if coll.name == "Colliders":
            stack = [coll]
            while stack:
                c = stack.pop()
                for o in c.objects:
                    _orig_hide.append((o, o.hide_render))
                    o.hide_render = True
                stack.extend(c.children)
    return bpy.data.objects, bpy.data.collections

def union_bbox(objs):
    mn = Vector((1e18,)*3); mx = Vector((-1e18,)*3); n = 0
    for o in objs:
        if o.type not in GEOM:
            continue
        for c4 in o.bound_box:
            w = o.matrix_world @ Vector(c4)
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
        n += 1
    return mn, mx, n

def center(mn, mx):
    return (Vector(mn) + Vector(mx)) * 0.5

# ---------------------------------------------------------------- env
def load_lib_materials(names):
    got = {n: bpy.data.materials.get(n) for n in names}
    missing = [n for n, m in got.items() if not m]
    if missing:
        try:
            with bpy.data.libraries.load(os.path.join(ROOT, "materials.blend"), link=True) as (src, dst):
                src.materials = missing
        except Exception as e:
            print("HARNESS lib material load failed:", e)
    res = {}
    for n in names:
        m = bpy.data.materials.get(n)
        if not m:
            m = bpy.data.materials.new("HARNESS_fallback")
            m.use_nodes = True
            pb = next((x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED"), None)
            if pb:
                pb.inputs["Base Color"].default_value = (0.35, 0.35, 0.35, 1.0)
        res[n] = m
    return res

def add_ground(center_xy, size=2000.0, mat_name="road_asphalt_new", z=-0.01):
    c = Vector(center_xy)
    s = size / 2.0
    me = bpy.data.meshes.new("HARNESS_GROUND")
    verts = [(c.x - s, c.y - s, z), (c.x + s, c.y - s, z),
             (c.x + s, c.y + s, z), (c.x - s, c.y + s, z)]
    me.from_pydata(verts, [], [(0, 1, 2, 3)])
    me.update()
    ob = bpy.data.objects.new("HARNESS_GROUND", me)
    ob.data.materials.append(load_lib_materials([mat_name])[mat_name])
    bpy.context.scene.collection.objects.link(ob)
    _created.append(ob.name)
    return ob

def add_sun(energy=3.0, elevation_deg=25.0, azimuth_deg=60.0, color=(1.0, 0.96, 0.9)):
    ld = bpy.data.lights.new("HARNESS_SUN", 'SUN')
    ld.energy = energy
    ld.angle = math.radians(2)
    ld.color = color
    ob = bpy.data.objects.new("HARNESS_SUN", ld)
    d = Vector((math.cos(math.radians(elevation_deg)) * math.cos(math.radians(azimuth_deg)),
                math.cos(math.radians(elevation_deg)) * math.sin(math.radians(azimuth_deg)),
                -math.sin(math.radians(elevation_deg))))
    ob.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(ob)
    _created.append(ob.name)
    return ob

def set_world(kind="day", strength=None):
    w = bpy.data.worlds.get("HARNESS_World") or bpy.data.worlds.new("HARNESS_World")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    if kind == "day":
        bg.inputs[0].default_value = (0.58, 0.63, 0.70, 1)   # grey-blue
        bg.inputs[1].default_value = 1.0 if strength is None else strength
    elif kind == "indoor":
        bg.inputs[0].default_value = (0.58, 0.60, 0.65, 1)
        bg.inputs[1].default_value = 0.25 if strength is None else strength
    elif kind == "night":
        bg.inputs[0].default_value = (0.012, 0.015, 0.03, 1)
        bg.inputs[1].default_value = 1.0 if strength is None else strength
    bpy.context.scene.world = w
    return w

# ---------------------------------------------------------------- render
def setup_render(samples=32, w=1920, h=1080, exposure=None):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    if exposure is not None:
        try:
            sc.view_settings.exposure = exposure
        except Exception:
            pass

# ---------------------------------------------------------------- camera
def new_cam(name):
    cd = bpy.data.cameras.new(name)
    cd.clip_start = 0.1
    cd.clip_end = 5000.0
    ob = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(ob)
    _created.append(ob.name)
    return ob

def place_camera(ob, loc, target, lens=35.0, clip_start=0.1, clip_end=5000.0):
    ob.location = Vector(loc)
    d = (Vector(target) - ob.location)
    d = d.normalized() if d.length > 1e-6 else Vector((0, 0, -1))
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    ob.data.lens = lens
    ob.data.clip_start = clip_start
    ob.data.clip_end = clip_end
    return ob

def _cast_hit(origin, direction, distance):
    res, loc, nrm, idx, obj, mat = bpy.context.scene.ray_cast(
        bpy.context.evaluated_depsgraph_get(),
        Vector(origin), Vector(direction).normalized(), distance=distance)
    return res, obj

def clear_view(pos, min_clear=0.6):
    for a in range(0, 360, 45):
        d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), -0.2))
        res, _ = _cast_hit(pos, d, min_clear)
        if res:
            return False
    return True

def nudge_along(ob, target, min_clear=0.7, step=2.0, max_iter=12):
    d = (Vector(target) - Vector(ob.location)).normalized()
    for i in range(max_iter):
        pos = Vector(ob.location) + d * (step * i)
        pos.z = max(pos.z, 1.6)
        if clear_view(pos, min_clear):
            ob.location = pos
            ob.rotation_euler = (Vector(target) - pos).normalized().to_track_quat('-Z', 'Y').to_euler()
            return i
    return -1

def frame_pos(mn, mx, lens=35.0, elev_deg=55.0, azim_deg=0.0, distance_mult=1.0):
    mn, mx = Vector(mn), Vector(mx)
    c = (mn + mx) * 0.5
    r = math.hypot(mx.x - mn.x, mx.y - mn.y) / 2.0 + (mx.z - mn.z) * 0.5
    hfov = 2 * math.atan(18.0 / lens)
    vfov = 2 * math.atan((1080.0 / 1920.0) * math.tan(hfov / 2))
    lim = min(hfov / 2, vfov / 2)
    d = (r / math.tan(lim)) * 1.15 * distance_mult
    pos = Vector((c.x + math.cos(math.radians(elev_deg)) * math.cos(math.radians(azim_deg)) * d,
                  c.y + math.cos(math.radians(elev_deg)) * math.sin(math.radians(azim_deg)) * d,
                  c.z + math.sin(math.radians(elev_deg)) * d))
    if pos.z < mn.z + 2.0:
        pos.z = mn.z + 2.0
    return pos, c, d

# ---------------------------------------------------------------- image qc
def render_to(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path, check_existing=False)
    try:
        px = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
        sd = float(px.std())
        mean = px.mean(axis=0)
        # magenta fraction: R high, G low, B high, R~B
        r, g, b = px[:, 0], px[:, 1], px[:, 2]
        mag = ((r > 0.6) & (g < 0.45) & (b > 0.5) & (np.abs(r - b) < 0.3))
        magfrac = float(mag.mean())
    finally:
        bpy.data.images.remove(img)
    return sd, mean, magfrac

def qc(name, sd, mean, magfrac, attempts, extras=None):
    rec = {"name": name, "png": os.path.join(OUT, name + ".png"),
           "stddev": round(sd, 4), "mean_rgb": [round(float(v), 4) for v in mean],
           "magenta_frac": round(magfrac, 4), "attempts": attempts}
    if extras:
        rec.update(extras)
    with open(os.path.join(METRICS, name + ".json"), "w") as f:
        json.dump(rec, f, indent=1, default=str)
    print("METRIC %s stddev=%.4f mag=%.4f mean=(%.2f,%.2f,%.2f) attempts=%d" % (
        name, sd, magfrac, mean[0], mean[1], mean[2], len(attempts)))
    return rec

# ---------------------------------------------------------------- shot_aerial
def shot_aerial(name, mn, mx, lens=35.0, elev=55.0, azim=0.0, distance_mult=1.0,
                ground=True, sun=True, world="day", ground_mat="road_asphalt_new",
                sun_energy=3.0, ground_size=None, world_strength=None):
    variants = [("base elev=%d az=%d" % (elev, azim)),
                "topdown", "45deg", "2x"]
    params = [(elev, azim, distance_mult),
              (88, 45, 1.1),
              (45, azim + 65, 1.0),
              (elev, azim, distance_mult * 2.0)]
    if ground:
        c = center(mn, mx)
        size = ground_size or max(400.0, max(mx.x - mn.x, mx.y - mn.y) * 1.6)
        add_ground((c.x, c.y), size=size, mat_name=ground_mat)
    if sun:
        add_sun(energy=sun_energy, elevation_deg=25.0)
    set_world(world, strength=world_strength)
    setup_render()
    cam = new_cam("HARNESS_CAM")
    attempts = []
    best_sd, best_src = -1.0, None
    best_mag, best_mean = 0.0, None
    for i, (label, (el, az, dm)) in enumerate(zip(variants, params)):
        pos, tgt, d = frame_pos(mn, mx, lens=lens, elev_deg=el, azim_deg=az, distance_mult=dm)
        clip_end = max(1500.0, d * 1.7 + (mx.z - mn.z) * 2.0)
        place_camera(cam, pos, tgt, lens=lens, clip_start=0.1, clip_end=clip_end)
        bpy.context.scene.camera = cam
        tmp = os.path.join(OUT, "_tmp_" + name + "_v%d.png" % i)
        sd, mean, mag = render_to(tmp)
        tag = label if i == 0 else label
        attempts.append({"variant": tag, "stddev": round(sd, 4), "magenta": round(mag, 4)})
        if sd >= BLANK_STDDEV:
            best_sd, best_src = sd, tmp
            best_mag, best_mean = mag, mean
            break
        if sd > best_sd:
            best_sd, best_src = sd, tmp
            best_mag, best_mean = mag, mean
    final = os.path.join(OUT, name + ".png")
    if best_src:
        shutil.move(best_src, final)
    for i in range(len(variants)):
        p = os.path.join(OUT, "_tmp_" + name + "_v%d.png" % i)
        if os.path.exists(p):
            os.remove(p)
    if best_sd < BLANK_STDDEV:
        print("WARN: %s below stddev threshold (best %.4f)" % (name, best_sd))
    qc(name, best_sd, best_mean, best_mag, attempts)
    return final, best_sd

# ---------------------------------------------------------------- shot_eye
def shot_eye(name, pos, target, lens=24.0, ground_center=None, ground_size=None,
             ground_mat="road_asphalt_new", ground=True, sun=True, world="day",
             sun_energy=3.0, min_clear=0.7, clip_end=2000.0, exposure=None,
             world_strength=None):
    pos = Vector(pos); pos.z = max(pos.z, 1.6)
    if ground:
        gc = ground_center or (pos.x, pos.y)
        add_ground(gc, size=ground_size or 2000.0, mat_name=ground_mat)
    if sun:
        add_sun(energy=sun_energy, elevation_deg=25.0)
    set_world("night" if world == "night" else "day", strength=world_strength)
    setup_render(exposure=exposure)
    cam = new_cam("HARNESS_CAM")
    tgt = Vector(target)
    ce = max(clip_end, (tgt - pos).length * 3.0)

    variants = []
    # variant 0: default at pos
    variants.append(("eye_default", pos, tgt, lens, ce))
    # variant 1: wider lens
    variants.append(("wide18", pos, tgt, 18.0, ce))
    # variant 2: pull back 1.5x along view axis
    view = (tgt - pos).normalized()
    pos2 = pos - view * ((tgt - pos).length * 0.5)
    pos2.z = max(pos2.z, 1.6)
    variants.append(("pulled_back", pos2, tgt, lens, ce))

    attempts = []
    best_sd, best_src = -1.0, None
    best_mag, best_mean = 0.0, None
    nudged = -1
    for i, (label, p, t, l, ce_) in enumerate(variants):
        cam.location = p
        cam.rotation_euler = (t - p).normalized().to_track_quat('-Z', 'Y').to_euler()
        if i == 0 and min_clear > 0:
            nudged = nudge_along(cam, t, min_clear=min_clear)
        place_camera(cam, cam.location, t, lens=l, clip_start=0.05, clip_end=ce_)
        bpy.context.scene.camera = cam
        tmp = os.path.join(OUT, "_tmp_" + name + "_v%d.png" % i)
        sd, mean, mag = render_to(tmp)
        attempts.append({"variant": label + " nudge=%d" % nudged, "stddev": round(sd, 4), "magenta": round(mag, 4)})
        if sd >= BLANK_STDDEV:
            best_sd, best_src = sd, tmp
            best_mag, best_mean = mag, mean
            break
        if sd > best_sd:
            best_sd, best_src = sd, tmp
            best_mag, best_mean = mag, mean
    final = os.path.join(OUT, name + ".png")
    if best_src:
        shutil.move(best_src, final)
    for i in range(len(variants)):
        p = os.path.join(OUT, "_tmp_" + name + "_v%d.png" % i)
        if os.path.exists(p):
            os.remove(p)
    if best_sd < BLANK_STDDEV:
        print("WARN: %s below stddev threshold (best %.4f)" % (name, best_sd))
    qc(name, best_sd, best_mean, best_mag, attempts)
    return final, best_sd

# ---------------------------------------------------------------- cleanup
def cleanup():
    for nm in list(set(_created)):
        ob = bpy.data.objects.get(nm)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
    for ob, v in _orig_hide:
        try:
            ob.hide_render = v
        except ReferenceError:
            pass
    w = bpy.data.worlds.get("HARNESS_World")
    if w:
        bpy.data.worlds.remove(w)
    _created.clear(); _orig_hide.clear()
