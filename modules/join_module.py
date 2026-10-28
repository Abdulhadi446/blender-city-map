"""Join all SM_/LOD mesh objects of a module into a few meshes (per top collection).

Run: blender -b out/props.blend -P modules/join_module.py -- --name SM_Props_Joined
Reduces object count massively (instances become real geometry) at the cost of
file size; used so the linked city master stays under Blender's object limit.
"""
import bpy, sys, time

arg = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
name = arg[arg.index("--name")+1] if "--name" in arg else "SM_Joined"

t0 = time.time()
meshes = [o for o in bpy.data.objects
          if o.type == 'MESH' and not o.name.startswith('COL_')
          and not o.name.startswith('COL')]
if not meshes:
    print("###NOTHING", flush=True); sys.exit(0)

# join in chunks of 8000 to keep operator overhead sane
CH = 8000
made = []
for i in range(0, len(meshes), CH):
    chunk = meshes[i:i+CH]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in chunk:
        o.select_set(True)
    act = chunk[0]
    bpy.context.view_layer.objects.active = act
    try:
        bpy.ops.object.join()
    except Exception as e:
        print("###JOIN_ERR", e, flush=True)
        continue
    act.name = "%s_%02d" % (name, i // CH)
    act.data.name = act.name
    made.append(act)

tot = sum(len(o.data.polygons) for o in made)
print("###JOINED name=%s objs_in=%d objs_out=%d tris=%d sec=%.1f"
      % (name, len(meshes), len(made), tot, time.time()-t0), flush=True)
bpy.ops.wm.save_mainfile(compress=True)
print("###SAVED", flush=True)
