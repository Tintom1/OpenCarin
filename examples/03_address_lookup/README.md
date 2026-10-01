# 03 — Address lookup

Finds a street address in a CARiN DVD the way the unit's address search does, and prints its
WGS84 position. Reads `NAV_DB_21708` (DB-REL 34) with the library only; no OSM data involved.

```bash
uv run python examples/03_address_lookup/lookup_address.py \
    --country italia --city modugno --street "via roma" --number 114
```

Result (about 6 s). Via Roma has several records on the disc (one per run of segments), so the
script lists each and only the one whose numbers hold 114 gives a position:

```
city      : modugno (post town: bari)   [0x0A -> 0x0D -> 0x0C]
street    : via roma   [0x0F -> 0x0E]  numbers even (112, 128)  odd None  tile 0x4c184f18, 1 segments

RESULT    : n. 114 on segment 42 of tile 0x4c184f18, numbers 112..128 (scheme 2)
  position: 41.088942, 16.791200
  segment : 41.088776, 16.790911  ->  41.090147, 16.793180  (6 points, class 2)
```

## Path through the database

| Step | Block | What it gives |
|---|---|---|
| country | `0x0A` | the country's city-trie root (names are lowercase, in the local language: `italia`) |
| city | `0x0D` letter trie → `0x0C` | the city record: post town, root of its road-name trie |
| street | `0x0F` letter trie → `0x0E` | street record → S1 → S2 link: a `0x00` tile, a run of S4 segments, the even/odd house-number envelope |
| geometry | `0x00` (CF=1, decoded by `carin.parser.cf1`) | the run's segments as WGS84 polylines |
| number | `0x04` | one record per S4 segment: the numbers on its two sides; the one that holds the number is the segment |

## Limits

- The point is **on the road centre line**, placed linearly between the segment's two stored numbers.
  Which side is left or right, and whether the first number is at the start node, are not known yet
  (`docs/carindb/06-objectives-roadmap.md`, A5), so the position can be off by the segment length
  and the sense of the interpolation is a guess. The segment's end points are printed too.
- Exact name match only (lowercase, as on the disc); the word-reordered alias records are skipped.
- Only the DB-REL 34 DVD layout is checked.
