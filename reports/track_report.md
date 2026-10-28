# Track module report (Phase C — RACE-TRACK)

- **module**: track
- **blend**: /home/abdulhadi/Work/city/out/track.blend
- **previews**: `["/home/abdulhadi/Work/city/out/track_preview.png", "/home/abdulhadi/Work/city/out/track_ground_preview.png"]`
- **collections**: `["Track", "Track/Meshes", "Track/Colliders", "Track/Lights"]`
- **objects**: 1173
- **triangles_unique**: 163430
- **triangles_expanded**: 163430
- **materials**: `["asphalt", "asphalt_worn", "concrete", "concrete_poured", "emissive_warm", "glass_dark", "grass", "gravel", "kerb_red", "kerb_white", "marking_white", "marking_yellow", "metal_painted_dark", "metal_steel", "roof_bitumen", "roof_metal", "sign_metal", "track_asphalt"]`
- **circuit**: `{"length_m": 3386.02, "layout_length_m": 3388.88, "stations": 847, "spacing_m": 3.998, "width_m": 14.0, "orientation": "CW", "bbox": [694.14, -1130.23, 1144.02, -70.02], "start_finish": [698.4, -717.6], "closed": true, "self_intersecting": false}`
- **pit**: `{"lane_x": 722.4, "lane_width_m": 12.0, "y_from": -894.0, "y_to": -306.0, "bays": 14, "building_rect": [738.4, -894.0, 768.4, -306.0], "building_height_m": 8.2, "paddock_rect": [768.4, -748.0, 828.0, -645.0]}`
- **grandstands**: `{"main": {"rect": [636.4, -858.72, 662.4, -423.6], "faces": "E", "rows": 30, "blocks": 4, "height_m": 17.4}, "hairpin": {"rect": [1168.0, -364.8, 1184.0, -247.2], "faces": "W", "rows": 20, "blocks": 2, "height_m": 12.2}}`
- **support**: `{"control_tower": {"rect": [772.4, -635.28, 788.4, -619.28], "height_m": 28.5, "sign": "TIMING"}, "medical": {"rect": [812.0, -916.0, 850.0, -886.0]}, "kiosks": [[616.0, -806.0, 628.0, -790.0], [616.0, -622.0, 628.0, -606.0], [616.0, -458.0, 628.0, -442.0]], "access_road": {"entry_x": 612.0, "y": -1040.0, "width_m": 8.0, "bridge_span": [686.0, 710.0], "bridge_clear_m": 4.4, "loop_rect": [796.0, -772.0, 874.0, -556.0]}, "marshal_posts": 16, "masts": 8, "lights": ["LT_track_01", "LT_track_02", "LT_track_03", "LT_track_04", "LT_track_05", "LT_track_06", "LT_track_07", "LT_track_08"]}`
- **barriers**: `{"armco_segments": 781, "armco_objects": 235, "tyre_stacks": 820, "tyre_objects": 137, "fence_panels": 181, "fence_objects": 164, "cones": 14}`
- **verify**: `{"problems": [], "tris_unique": 163430, "tris_expanded": 163430, "objects": 1173, "bbox": [612.0, -1184.94, 1185.93, -15.01], "outside_t": 0, "corridor_overlaps": 0, "lights": 8, "circuit_length_m": 3386.02, "circuit_stations": 847, "circuit_orientation": "CW", "previews_ok": true}`
- **notes**: `["instanced objects keep translation/rotation (shared meshes) \u2014 do not apply transforms on them; unique meshes are authored in world space", "armco / tyre banks / debris fence are run-batched (4-6 placements baked per mesh object, custom props kind + segments/stacks/panels keep the counts) so the module lands inside the 400-1500 object budget", "scene world 'World' is set to a light sky so the previews are not black; the Assembler may replace it", "ground plane / infield fill outside the built bands is the Assembler's job", "hairpin grandstand shifted 1.7 m west of the parcel rect to stay clear of the x=1200 arterial corridor"]`
- **needed_from_others**: `["Assembler: continuous ground plane under the circuit (z=0)", "Assembler: do not re-light the circuit \u2014 LT_track_01..08 exist"]`
- **wall_clock_s**: 131.3
