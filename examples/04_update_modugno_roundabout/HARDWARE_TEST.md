# Hardware test request — the Modugno roundabout

**Status: nothing here has been run on a unit.** Every "ok" in `CHANGES.md` means "our decoders read it back and the
checks we could write pass". Whether the original unit accepts the edited disc is only known from a unit.

## What would be tested

`dataset/NAV_DB_21708_copy.ISO`: DVD `NAV_DB_21708` (BMW High 2016, DVD 1) with 331 blocks rewritten in place, none moved, same size as the
original (the byte difference is 6,113 sectors, all inside those blocks). It is rebuilt from the original by
`06_patch_references.py --fresh` (the whole pipeline is in `CHANGES.md`); the image is not in the repository.

The change is local: at 41°05'16.1"N 16°47'22.6"E (Modugno, Bari) the 2016 crossing is replaced by the roundabout OSM has
(6 ring nodes, 6 one-way ring records, 4 one-way links, Viale della Repubblica as two one-way arms), in the street tile `0x4c184f18`
and the coarse tile `0x5c58a51c`, plus every offset that points into them (315 `0x0E` blocks, 2 `0x10`, 2 `0x17`, `0x04`, 9 neighbour tiles).

## What is missing to put it on a unit (blocks everything below)

- **No DVD builder** (roadmap D15). The image would have to be burned as the DVD-ROM volume the unit expects. Which unit do you have, and
  with which medium: the original DVD navigation drive (RoadRunner) with a burned DVD, or an emulation of the drive? Please say before anything is built for it.
- On the **CD platform** (CNI1) the route of `01-architecture.md` section 4.4.1 and `docs/CARINDB_BLUEPRINT_EN.md` (CD-i Bridge, raw burn) exists, but
  this disc is a DVD with a different database revision (DB-REL 34); a CD of this region would be a different build.

## Scenario, in order (stop at the first failure and say where)

1. **Boot and map.** The unit reads the disc and shows the map at the car's position anywhere (the edit must not break the disc).
2. **Draw.** Place the map (or position) at Modugno, 41.0878 N, 16.7896 E. Zoom from the finest level out to the region level: the ring and its
   six arms are drawn (no old crossing), at every zoom level, with no stray line or gap at the tile edges.
3. **Address search.** Search *Modugno, Viale della Repubblica* and *Via Roma*, a house number on each (the one on the removed Via Roma arm, number 108, is gone
   on purpose). The result must land on the street, not elsewhere.
4. **Route across the ring, from each arm** (set the destination by map position): west (Via Roma) to Viale della Repubblica south-east, north-east (SP1) to
   west, from Viale della Repubblica north-west towards the town. Guidance must say "roundabout" / the exit, go **counter-clockwise** (right-hand traffic), and never use an arm against its one-way direction.
5. **A route that passes through the junction** from far away (another town to another), at least once each way.

## What pass and fail look like

- **Pass:** 1 to 5 as written; routes follow the ring counter-clockwise; no restart, freeze or error.
- **Fail, most informative first:** the unit does not boot or does not read the disc; the unit crashes or restarts when the map loads near Modugno (the first edit that broke
  an ordering rule behaved like this, `03-road-network.md` section 6.7); the ring is drawn but guidance ignores it (coarse level); the address search lands
  on the old position or on another street (the `0x0E` / `0x10` references); the map is drawn with a hole or a spike at the tile edge (S6 twins).

## What to send back

Photos or a short video of each step on the unit's screen (map at three zoom levels, the address result, a route with the guidance text), the unit's
model and software version, and for a crash: when it happened (disc inserted, map load, search, route), whether it repeats, and whether it also happens at another place on the map.
