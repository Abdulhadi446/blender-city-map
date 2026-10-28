# flyover — Phase B pilot (NE ring corner + ramp X_N_600)

## Files

- script: `/home/abdulhadi/Work/city/modules/flyover.py`
- blend: `/home/abdulhadi/Work/city/out/flyover.blend`
- preview (aerial): `/home/abdulhadi/Work/city/out/flyover_preview.png`
- preview (ground): `/home/abdulhadi/Work/city/out/flyover_ground_preview.png`

## Counts

- objects: **1243** (Meshes 1191 / Colliders 52 / Lights 0)
- triangles (instanced): **44680**
- triangles (unique meshes): **23592**

## Materials used

- asphalt
- asphalt_highway
- asphalt_worn
- concrete
- concrete_poured
- dirt
- gravel
- marking_white
- marking_yellow
- metal_steel

## Geometry facts for the Assembler

- **ring_deck_top_z**: 8.0
- **ring_deck_soffit_z**: 6.5
- **ring_deck_width_m**: 34.0
- **ring_path**: H_07 x=1400 y=600->1280, 120 m arc (c=1280,1280), H_08 y=1400 x=1280->600
- **ring_path_length_m**: 1548.49
- **corner_radius_m**: 120.0
- **min_ground_clearance_m**: 6.5
- **ramp_start**: [600.0, 1400.0, 7.99]
- **ramp_end**: [600.0, 1200.0, 0.0]
- **ramp_end_width_m**: 24.0
- **ramp_plan_length_m**: 218.48
- **ramp_gradient_pct**: 3.9716
- **ramp_bulge_m**: 40.0
- **ramp_barrier_stop_s**: 181.3
- **global_z_min**: -0.05
- **global_z_max**: 9.08

### Ramp landing cross-section

- **line**: y=1200.0, x from 588.0 to 612.0, z=0.000 (flush)
- **width_m**: 24.0
- **heading**: due south (-Y), ramp deck top flush with arterial z=0
- **flare**: 18.0 m wide above y=1212, linear flare to 24.0 m at y=1200
- **matches**: arterial corridor envelope halfwidth 12.0 m; the ramp footprint sits on the junction patch (carriageway 590.5..609.5) and the cut-out sidewalk gap (588..612)
- **surfaces**: asphalt, no step (>0.5 m gap/overlap: none)
- **ground band**: service road 10 m wide (u +/-5) along the ring centreline, x=1400 strip y 600..1400 and y=1400 strip x 600..1400 (rounded corner), gravel verge u 5..14, dirt verge u 14..20, all tops at z 0.0 / -0.05

## Checks

- deck_z_is_8m: PASS
- deck_soffit_6_5m: PASS
- clearance_ge_5_5m: PASS
- ramp_gradient_le_4pct: PASS
- ramp_lands_at_600_1200_z0: PASS
- nothing_below_minus_0_05: PASS

## Known issues

- The ramp start (600,1400) sits inside the ring deck: the ramp slab top is 7.99 m there (1 cm below the 8.00 m deck) so the two surfaces never z-fight; the ramp becomes visible exactly at the deck edge y=1383 with a 1 cm ledge.
- To stay under the 4 % gradient the ramp is swept (raised-cosine bulge 40 m east of x=600); its plan footprint reaches x~640 at y~1300, outside the 18 m straight corridor in layout.json.
- Ramp terminus overlaps the y=1200 arterial junction for its last 12 m (y 1200..1212) with a wedge nose: top 0.48 m at y=1212 falling to 0.00 m at y=1200. No step at the landing line.
- Instance transforms (location/rotation/scale) are intentionally NOT applied — applying them would bake into the shared mesh and destroy the instancing. All swept/unique meshes are built in world space, so their matrix_basis is already identity.

## Wanted from other agents

- MISSING MATERIAL: none — every material used exists in materials.blend.
- Signage/gantry agents may attach to the deck edges (top z=8.0, barrier top z=9.05, barrier at |u| 16.4..17.0).
- The Assembler should not place ground roads or buildings inside the ground band (service road + verges, u +/-20 around the ring centreline).
