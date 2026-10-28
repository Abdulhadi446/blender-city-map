"""Validate every mesh in the currently-open blend and save it.

Fixes the Blender 5.2 EEVEE segfault traced to invalid mesh data in
civic.blend (SM_MuseumCity etc.). Safe/idempotent for every module blend.

Run per file:  blender -b out/<module>.blend -P modules/validate_meshes.py
"""
import bpy

fixed = 0
for me in bpy.data.meshes:
    try:
        if me.validate(verbose=False, clean_customdata=True):
            me.update()
            fixed += 1
    except Exception:
        pass

print("###VALIDATED meshes=%d repaired=%d file=%s" % (len(bpy.data.meshes), fixed, bpy.data.filepath))
if fixed:
    bpy.ops.wm.save_mainfile(compress=True)
    print("###SAVED")
