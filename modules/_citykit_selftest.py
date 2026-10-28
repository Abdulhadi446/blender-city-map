"""citykit self-test — proves the shared helper library works end to end.

Run:  cd /home/abdulhadi/Work/city && blender -b -P modules/_citykit_selftest.py
All artefacts are written to /tmp/opencode (nothing is left in out/ or reports/).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy
from mathutils import Matrix

import citykit as ck

PASS = []


def ok(label, detail=""):
    PASS.append(label)
    print("[PASS] %s %s" % (label, detail))


# --- 1. constants ---------------------------------------------------------
assert ck.CITY_ROOT == "/home/abdulhadi/Work/city", ck.CITY_ROOT
for p in (ck.OUT_DIR, ck.MODULES_DIR, ck.REPORTS_DIR):
    assert p.startswith(ck.CITY_ROOT), p
    assert os.path.isdir(p), p
ok("constants", ck.CITY_ROOT)

# --- 2. layout readers ----------------------------------------------------
lay = ck.read_layout()
n_parcels = len(lay["parcels"])
assert n_parcels == 2545, n_parcels
r = ck.read_parcels("R")
assert all(p["district"] == "R" for p in r)
try:
    ck.read_parcels("ZZ")
    raise SystemExit("[FAIL] read_parcels accepted a bad district")
except RuntimeError as e:
    ok("read_parcels error path", str(e)[:60])
ok("read_layout", "%d parcels, %d R, %d edges, %d nodes"
   % (n_parcels, len(r), len(ck.read_road_edges()), len(ck.read_road_nodes())))

# --- 3. append_material (5 names + failure path) --------------------------
names = ["asphalt", "brick_red", "glass_office", "neon_red", "leaves_green"]
mats = [ck.append_material(n) for n in names]
assert [m.name for m in mats] == names, [m.name for m in mats]
ok("append_material x5", ",".join(names))
# second call must hit the cache (same datablock)
assert ck.append_material("asphalt").name == "asphalt"
try:
    ck.append_material("unobtainium_xyz")
    raise SystemExit("[FAIL] append_material accepted a missing name")
except RuntimeError as e:
    msg = str(e)
    assert "asphalt" in msg and "Available" in msg, msg
    ok("append_material error path", msg.splitlines()[0][:80])

# --- 4. collections, assign, dup, instance --------------------------------
bpy.ops.mesh.primitive_cube_add(size=2.0)
cube = bpy.context.active_object
cube.name = "SM_Selftest_Box_01"
coll = ck.ensure_collection("CityKitSelftest")
ck.link_obj(cube, coll)
ck.assign(cube, "brick_red")
assert cube.data.materials[0].name == "brick_red"
ok("ensure_collection + assign", coll.name)

cube.location = (1.0, 2.0, 0.0)
cube.scale = (2.0, 1.0, 1.0)
ck.update_view()                       # make sure matrix_world is current
world_before = [tuple(cube.matrix_world @ v.co) for v in cube.data.vertices]
assert ck.apply_all_transforms(cube) is True
ck.update_view()                       # refresh stale matrix_world after the bake
assert tuple(round(v, 4) for v in cube.scale) == (1.0, 1.0, 1.0), tuple(cube.scale)
world_after = [tuple(cube.matrix_world @ v.co) for v in cube.data.vertices]
assert max(max(abs(a - b) for a, b in zip(p, q))
           for p, q in zip(world_before, world_after)) < 1e-6
ok("apply_all_transforms", "scale baked, world-space geometry unchanged")

dup = ck.dup_mesh(cube, "SM_Selftest_Box_02", matrix=Matrix.Translation((5.0, 0.0, 0.0)))
assert dup.data is cube.data, "dup_mesh must SHARE the mesh datablock"
ck.link_obj(dup, coll)
ck.assign(dup, "concrete")
ok("dup_mesh (linked)", dup.name)

inst = ck.instance_collection(coll, "INST_Selftest", (0.0, 6.0, 0.0), rot_z=0.5, scale=2.0)
assert inst.instance_type == "COLLECTION" and inst.instance_collection == coll
ok("instance_collection", inst.name)

# --- 5. tri counting ------------------------------------------------------
t_cube = ck.tri_count(cube)
assert t_cube == 12, t_cube
t_coll = ck.tri_count(coll)
assert t_coll >= 24, t_coll
t_scene = ck.scene_tri_count()
assert t_scene >= 24, t_scene
ok("tri_count", "cube=%d coll=%d scene=%d" % (t_cube, t_coll, t_scene))

# --- 6. save_blend + make_preview (temp camera/light removed again) -------
tmp_blend = "/tmp/opencode/citykit_selftest.blend"
tmp_png = "/tmp/opencode/citykit_selftest.png"
for p in (tmp_blend, tmp_png):
    if os.path.exists(p):
        os.remove(p)
n_objs_before = len(bpy.data.objects)
saved = ck.save_blend(tmp_blend)
assert os.path.isfile(saved) and os.path.getsize(saved) > 1000
img = ck.make_preview(tmp_png, (9.0, -11.0, 6.0), (1.5, 0.0, 1.0), res=(960, 540))
assert os.path.isfile(img) and os.path.getsize(img) > 5000, os.path.getsize(img)
assert len(bpy.data.objects) == n_objs_before, \
    "make_preview left temp objects behind: %d -> %d" % (n_objs_before, len(bpy.data.objects))
assert not any(o.name.startswith("TMP_PREVIEW") for o in bpy.data.objects)
ok("save_blend + make_preview", "%d KB blend, %d KB png, objects %d"
   % (os.path.getsize(saved) // 1024, os.path.getsize(img) // 1024, len(bpy.data.objects)))

# --- 7. write_report (cleaned up again) -----------------------------------
rep = ck.write_report("_citykit_selftest", {"checks": len(PASS), "ok": True})
assert os.path.isfile(rep)
os.remove(rep)
ok("write_report", rep)

print("\nALL SELFTEST CHECKS PASSED (%d): %s" % (len(PASS), "; ".join(PASS)))
