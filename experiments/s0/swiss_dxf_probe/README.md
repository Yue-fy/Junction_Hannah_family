# Swiss Dwellings DXF probe (S0, Fri 23:40)

Dependency-free probes (plain DXF group-code parsing, no ezdxf) that check how far the DXF layers alone answer
the swiss_dwellings questions. Run with any Python 3: `python3 swiss_poly_check.py $STOA_DATA`
(run from this directory; `swiss_count_check.py` reuses the parser in `swiss_poly_check.py`).

Results on 150 random floors (seeded):
- Room net area ("net floor area of room 2.10 (...)"): area of the ROOM_OUTLINE LWPOLYLINE that contains the room
  number TEXT (ROOM_TEXT layer, pattern `\d+\.\d+`), DXF units = metres: **592/594 within 2%**.
  Note 76% of these questions ask about rooms whose area is NOT printed on the plan; when printed ("16.78 m²"),
  the printed value is always right (142/142).
- Windows: count(WINDOW LWPOLYLINE) / 3: **300/300 exact**.
- Rooms labelled X: exact match on ROOM_TEXT strings: 1631/1872 (87%); misses look like label-matching issues.
- Apartments: count(UNIT_OUTLINE): 264/300 (88%), overcounts sometimes.
- Doors: count(DOOR ARC): 184/300 (61%), overcounts (double doors?).
- Fixtures (WC, washbasin, bathtub, shower): not tried; FIXTURE layer has LWPOLYLINE + CIRCLE, needs classification.
