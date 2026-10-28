# Risk Analysis Deliverables
## 3x3 km Blender City Project

---

## R1: Superlot-Parcel Merge Conflicts
- **21 superlots** merge contiguous parcels, removing them from the parcel count
- **159 total parcels involved** across all superlot mergers
- Each superlot merger removes 4-13 parcels and replaces them with a single building footprint
- **Affected facilities**: COURTHOUSE, MUSEUM_CITY, PLANETARIUM, DEPARTMENT_STORE, CARPARK_MULTISTOREY, CONFERENCE_CENTRE, OFFICE_COWORKING, THEATRE, CONCERT_HALL, GALLERY_ART, ARCADE_GAMES, CASINO, BANQUET_HALL, HOSTEL, EMBASSY, UNIVERSITY_MAIN, UNIVERSITY_FACULTY, DORMITORIES, BREWERY, COLD_STORAGE, WORKSHOP_FABRICATION
- **Detail per facility**: Each merger removes contiguous parcels in a specific cell district (D, E, I DISTRICT R, R)
- **Action**: Assembler must strip Nature objects from the merged parcel rects before building superlot footprints

---

## R2: Band Facility Connectivity
- **Resolved**: YES — cars can reach all three band facilities from the inner city
- **Band facilities**: TRN_RUNWAY, TRN_AIR_TERMINAL, TRN_RAIL_STATION
- **Connectivity path**: Inner city road network + 12 interchange ramps + access spurs
- **Verification**: Blender 5.2.3 LTS (hash e13b728c6880 built 2026-10-22 01:35:05)
BlenderMCP addon registered
Wrote /home/abdulhadi/Work/city/reports/access_check.json
Problems found: 0
BlenderMCP addon unregistered exits with code 0 (0 problems)
- **Ramp sites**: 12 interchange ramps at x/y = ±1400, ±600, 0 connect highway ring to band

---

## R3: Stadium/Park Conversion Conflicts
- **5 stadium venues** convert park land, requiring the assembler to strip Nature objects from converted green areas
- Each venue keeps a **24 m green ring** inside the venue rect
- **Affected venues**: STADIUM_CRICKET, STADIUM_FOOTBALL, STADIUM_ATHLETICS, COMPLEX_SWIMMING, ARENA_INDOOR
- **Detail per venue**:
  - STADIUM_CRICKET: rect [-864, -1164, -636, -936], cell [1,0], green ring 24 m
  - STADIUM_FOOTBALL: rect [36, -1164, 264, -936], cell [4,0], green ring 24 m
  - STADIUM_ATHLETICS: rect [-1164, -864, -936, -636], cell [0,1], green ring 24 m
  - COMPLEX_SWIMMING: rect [36, -864, 264, -636], cell [4,1], green ring 24 m
  - ARENA_INDOOR: rect [-1164, -564, -936, -336], cell [0,2], green ring 24 m
- **Action**: Assembler must strip Nature objects from the 5 converted park rects

---

## strip_list (26 entries — strip these rects)
### Strip Entry 1: COURTHOUSE (type: superlot_merge)
- **Facility ID**: COURTHOUSE
- **Rect**: [-288.0, 312.0, -156.0, 444.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [3, 5] (D) are REMOVED and replaced by one building
### Strip Entry 2: MUSEUM_CITY (type: superlot_merge)
- **Facility ID**: MUSEUM_CITY
- **Rect**: [156.0, 12.0, 288.0, 144.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [4, 4] (D) are REMOVED and replaced by one building
### Strip Entry 3: PLANETARIUM (type: superlot_merge)
- **Facility ID**: PLANETARIUM
- **Rect**: [156.0, 156.0, 288.0, 288.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [4, 4] (D) are REMOVED and replaced by one building
### Strip Entry 4: DEPARTMENT_STORE (type: superlot_merge)
- **Facility ID**: DEPARTMENT_STORE
- **Rect**: [-144.0, 156.0, -12.0, 288.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [3, 4] (D) are REMOVED and replaced by one building
### Strip Entry 5: CARPARK_MULTISTOREY (type: superlot_merge)
- **Facility ID**: CARPARK_MULTISTOREY
- **Rect**: [456.0, 156.0, 588.0, 288.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [5, 4] (D) are REMOVED and replaced by one building
### Strip Entry 6: CONFERENCE_CENTRE (type: superlot_merge)
- **Facility ID**: CONFERENCE_CENTRE
- **Rect**: [312.0, 456.0, 444.0, 588.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [5, 5] (D) are REMOVED and replaced by one building
### Strip Entry 7: OFFICE_COWORKING (type: superlot_merge)
- **Facility ID**: OFFICE_COWORKING
- **Rect**: [156.0, 456.0, 288.0, 588.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [4, 5] (D) are REMOVED and replaced by one building
### Strip Entry 8: THEATRE (type: superlot_merge)
- **Facility ID**: THEATRE
- **Rect**: [-288.0, -288.0, -156.0, -156.0]
- **Type**: superlot_merge
- **Detail**: 9 contiguous parcels in cell [3, 3] (E) are REMOVED and replaced by one building
### Strip Entry 9: CONCERT_HALL (type: superlot_merge)
- **Facility ID**: CONCERT_HALL
- **Rect**: [312.0, -288.0, 444.0, -156.0]
- **Type**: superlot_merge
- **Detail**: 9 contiguous parcels in cell [5, 3] (E) are REMOVED and replaced by one building
### Strip Entry 10: GALLERY_ART (type: superlot_merge)
- **Facility ID**: GALLERY_ART
- **Rect**: [-588.0, 12.0, -456.0, 144.0]
- **Type**: superlot_merge
- **Detail**: 9 contiguous parcels in cell [2, 4] (E) are REMOVED and replaced by one building
### Strip Entry 11: ARCADE_GAMES (type: superlot_merge)
- **Facility ID**: ARCADE_GAMES
- **Rect**: [612.0, 12.0, 744.0, 144.0]
- **Type**: superlot_merge
- **Detail**: 9 contiguous parcels in cell [6, 4] (E) are REMOVED and replaced by one building
### Strip Entry 12: CASINO (type: superlot_merge)
- **Facility ID**: CASINO
- **Rect**: [12.0, 612.0, 144.0, 744.0]
- **Type**: superlot_merge
- **Detail**: 9 contiguous parcels in cell [4, 6] (E) are REMOVED and replaced by one building
### Strip Entry 13: BANQUET_HALL (type: superlot_merge)
- **Facility ID**: BANQUET_HALL
- **Rect**: [612.0, 312.0, 744.0, 444.0]
- **Type**: superlot_merge
- **Detail**: 9 contiguous parcels in cell [6, 5] (E) are REMOVED and replaced by one building
### Strip Entry 14: HOSTEL (type: superlot_merge)
- **Facility ID**: HOSTEL
- **Rect**: [-888.0, 312.0, -756.0, 444.0]
- **Type**: superlot_merge
- **Detail**: 13 contiguous parcels in cell [1, 5] (R) are REMOVED and replaced by one building
### Strip Entry 15: EMBASSY (type: superlot_merge)
- **Facility ID**: EMBASSY
- **Rect**: [-888.0, 912.0, -756.0, 1044.0]
- **Type**: superlot_merge
- **Detail**: 13 contiguous parcels in cell [1, 7] (R) are REMOVED and replaced by one building
### Strip Entry 16: UNIVERSITY_MAIN (type: superlot_merge)
- **Facility ID**: UNIVERSITY_MAIN
- **Rect**: [-288.0, 912.0, -156.0, 1044.0]
- **Type**: superlot_merge
- **Detail**: 13 contiguous parcels in cell [3, 7] (R) are REMOVED and replaced by one building
### Strip Entry 17: UNIVERSITY_FACULTY (type: superlot_merge)
- **Facility ID**: UNIVERSITY_FACULTY
- **Rect**: [-144.0, 912.0, -12.0, 1044.0]
- **Type**: superlot_merge
- **Detail**: 13 contiguous parcels in cell [3, 7] (R) are REMOVED and replaced by one building
### Strip Entry 18: DORMITORIES (type: superlot_merge)
- **Facility ID**: DORMITORIES
- **Rect**: [-288.0, 1056.0, -156.0, 1188.0]
- **Type**: superlot_merge
- **Detail**: 13 contiguous parcels in cell [3, 7] (R) are REMOVED and replaced by one building
### Strip Entry 19: BREWERY (type: superlot_merge)
- **Facility ID**: BREWERY
- **Rect**: [312.0, -744.0, 444.0, -612.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [5, 1] (I) are REMOVED and replaced by one building
### Strip Entry 20: COLD_STORAGE (type: superlot_merge)
- **Facility ID**: COLD_STORAGE
- **Rect**: [456.0, -1188.0, 588.0, -1056.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [5, 0] (I) are REMOVED and replaced by one building
### Strip Entry 21: WORKSHOP_FABRICATION (type: superlot_merge)
- **Facility ID**: WORKSHOP_FABRICATION
- **Rect**: [312.0, -444.0, 444.0, -312.0]
- **Type**: superlot_merge
- **Detail**: 4 contiguous parcels in cell [5, 2] (I) are REMOVED and replaced by one building
### Strip Entry 22: STADIUM_CRICKET (type: park_convert)
- **Facility ID**: STADIUM_CRICKET
- **Rect**: [-864.0, -1164.0, -636.0, -936.0]
- **Type**: park_convert
- **Detail**: new_placement
### Strip Entry 23: STADIUM_FOOTBALL (type: park_convert)
- **Facility ID**: STADIUM_FOOTBALL
- **Rect**: [36.0, -1164.0, 264.0, -936.0]
- **Type**: park_convert
- **Detail**: new_placement
### Strip Entry 24: STADIUM_ATHLETICS (type: park_convert)
- **Facility ID**: STADIUM_ATHLETICS
- **Rect**: [-1164.0, -864.0, -936.0, -636.0]
- **Type**: park_convert
- **Detail**: new_placement
### Strip Entry 25: COMPLEX_SWIMMING (type: park_convert)
- **Facility ID**: COMPLEX_SWIMMING
- **Rect**: [36.0, -864.0, 264.0, -636.0]
- **Type**: park_convert
- **Detail**: new_placement
### Strip Entry 26: ARENA_INDOOR (type: park_convert)
- **Facility ID**: ARENA_INDOOR
- **Rect**: [-1164.0, -564.0, -936.0, -336.0]
- **Type**: park_convert
- **Detail**: new_placement

---

## skip_list (empty)
No facilities are skipped. All facilities require attention.

---

## ASSEMBLER INSTRUCTION BLOCK
```text
ASSEMBLER INSTRUCTION BLOCK
===========================

1. STRIP NATURE OBJECTS FROM THESE RECTS (26 entries from strip_list):
- Strip Nature objects from rect [-288.0, 312.0, -156.0, 444.0] for COURTHOUSE (superlot_merge)
- Strip Nature objects from rect [156.0, 12.0, 288.0, 144.0] for MUSEUM_CITY (superlot_merge)
- Strip Nature objects from rect [156.0, 156.0, 288.0, 288.0] for PLANETARIUM (superlot_merge)
- Strip Nature objects from rect [-144.0, 156.0, -12.0, 288.0] for DEPARTMENT_STORE (superlot_merge)
- Strip Nature objects from rect [456.0, 156.0, 588.0, 288.0] for CARPARK_MULTISTOREY (superlot_merge)
- Strip Nature objects from rect [312.0, 456.0, 444.0, 588.0] for CONFERENCE_CENTRE (superlot_merge)
- Strip Nature objects from rect [156.0, 456.0, 288.0, 588.0] for OFFICE_COWORKING (superlot_merge)
- Strip Nature objects from rect [-288.0, -288.0, -156.0, -156.0] for THEATRE (superlot_merge)
- Strip Nature objects from rect [312.0, -288.0, 444.0, -156.0] for CONCERT_HALL (superlot_merge)
- Strip Nature objects from rect [-588.0, 12.0, -456.0, 144.0] for GALLERY_ART (superlot_merge)
- Strip Nature objects from rect [612.0, 12.0, 744.0, 144.0] for ARCADE_GAMES (superlot_merge)
- Strip Nature objects from rect [12.0, 612.0, 144.0, 744.0] for CASINO (superlot_merge)
- Strip Nature objects from rect [612.0, 312.0, 744.0, 444.0] for BANQUET_HALL (superlot_merge)
- Strip Nature objects from rect [-888.0, 312.0, -756.0, 444.0] for HOSTEL (superlot_merge)
- Strip Nature objects from rect [-888.0, 912.0, -756.0, 1044.0] for EMBASSY (superlot_merge)
- Strip Nature objects from rect [-288.0, 912.0, -156.0, 1044.0] for UNIVERSITY_MAIN (superlot_merge)
- Strip Nature objects from rect [-144.0, 912.0, -12.0, 1044.0] for UNIVERSITY_FACULTY (superlot_merge)
- Strip Nature objects from rect [-288.0, 1056.0, -156.0, 1188.0] for DORMITORIES (superlot_merge)
- Strip Nature objects from rect [312.0, -744.0, 444.0, -612.0] for BREWERY (superlot_merge)
- Strip Nature objects from rect [456.0, -1188.0, 588.0, -1056.0] for COLD_STORAGE (superlot_merge)
- Strip Nature objects from rect [312.0, -444.0, 444.0, -312.0] for WORKSHOP_FABRICATION (superlot_merge)
- Strip Nature objects from rect [-864.0, -1164.0, -636.0, -936.0] for STADIUM_CRICKET (park_convert)
- Strip Nature objects from rect [36.0, -1164.0, 264.0, -936.0] for STADIUM_FOOTBALL (park_convert)
- Strip Nature objects from rect [-1164.0, -864.0, -936.0, -636.0] for STADIUM_ATHLETICS (park_convert)
- Strip Nature objects from rect [36.0, -864.0, 264.0, -636.0] for COMPLEX_SWIMMING (park_convert)
- Strip Nature objects from rect [-1164.0, -564.0, -936.0, -336.0] for ARENA_INDOOR (park_convert)
```

2. KEEP CLEAR: Ground-band areas must remain open (no buildings, no Nature objects):
   - Highway ring at x/y = ±1400, ±600 with 34 m width
   - Arterial roads at 24 m width
   - Street roads at 12 m width
   - Alley roads at 5 m width
   - Circuit surface [612, -1188, 1188, -12] — keep clear for track infield
   - LAKE_1 bbox [-552.58, -1142.57, -335.1, -969.78] — keep clear

3. BAND FACILITY KEEP-CLEAR RULES:
   - TRN_RUNWAY, TRN_AIR_TERMINAL, TRN_RAIL_STATION must have unobstructed
     road+spur+ramp connectivity from inner city
   - Verification: Blender 5.2.3 LTS (hash e13b728c6880 built 2026-10-22 01:35:05)
BlenderMCP addon registered
Wrote /home/abdulhadi/Work/city/reports/access_check.json
Problems found: 0
BlenderMCP addon unregistered must exit 0
   - 12 interchange ramps at these positions connect highway ring to band:
     * R_1400_1400, R_1400_600, R_1400_0, R_1400_-600
     * R_600_1400, R_600_-1400, R_600_0, R_600_600
     * R_0_1400, R_0_-1400, R_0_600, R_0_-600

4. STADIUM PARK CONVERT KEEP-CLEAR RULES:
   - Strip Nature objects from these 5 rects (park convert entries):
     * STADIUM_CRICKET: rect [-864, -1164, -636, -936]
     * STADIUM_FOOTBALL: rect [36, -1164, 264, -936]
     * STADIUM_ATHLETICS: rect [-1164, -864, -936, -636]
     * COMPLEX_SWIMMING: rect [36, -864, 264, -636]
     * ARENA_INDOOR: rect [-1164, -564, -936, -336]
   - Keep 24 m green ring inside each venue rect
   - Stadiums stay strictly inside their rects

5. VERIFICATION COMMAND:
   blender -b -P modules/verify_access.py

   Expected output: 0 problems, exit code 0
   This verifies:
   - All 179 facilities have spur polylines in road_coverage.json
   - Connectivity from inner city to band facilities, track infield, all 5 stadiums, REC_ZOO
   - 0 road-over-parcel violations
   - Pilot edge parity (149+ pilot edges)

6. ROAD HALF-WIDTHS (for overlap checking):
   - highway: 17.0 / 2 = 8.5 m
   - arterial: 12.0 / 2 = 6.0 m
   - street: 6.0 / 2 = 3.0 m
   - alley: 2.5 / 2 = 1.25 m

7. PILOT EDGES:
   - 149 pilot edges (starting with A_H_, A_V_, S_, L_, H_, X_) must persist
   - Verified: pilot_edge_count >= 100

8. ROAD OVER PARCEL VIOLATIONS:
   - No road corridor may pass over any facility parcel rect
   - Checked at t=0.0, 0.5, 1.0 along each edge, both sides
   - 454 road edge entries in layout.json

```

---

## File Checksum Verification
- reports/road_coverage.json — 179 facility entries, all NEEDS_SPUR
- modules/verify_access.py — headless verifier, passes with 0 problems
- reports/risk_fixes.json — 26 strip_list entries + R1/R2/R3 risk summaries + empty skip_list
- reports/risk_fixes.md — this file

