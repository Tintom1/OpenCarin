"""Step 6: write the redrawn tile into a fresh copy of the disc and rewrite everything that points into it.

Reads dataset/redraw.json (step 5: the old -> new offset of every S4 record and S6 node of the tile) and
dataset/xref_4c184f18.txt (`carindb-rs --iso <original> xref 0x4c184f18`: every block that holds the
tile's BLOCK_ID). Each hit is classified by block type (carin.parser.refs) and rewritten in place:

    0x00 (the tile)       the redrawn tile, re-encoded CF=1
    0x00 (neighbours)     S6 twin offsets (+12) of the nodes that twin with the tile's S6
    0x0E                  S4 offset / count of the street runs (zlib blocks, CF=1 block)
    0x10                  street directory entries (zlib)
    0x17                  TMC locations (zlib)
    0x04                  house-number records, one per S4 record (zlib)

and the same for the coarse tile (type 0x03, step 5b): the tile itself (zlib) and the S6 twin offsets of its
four neighbours (dataset/xref_5c58a51c.txt).

    uv run --with numpy python examples/04_update_modugno_roundabout/06_patch_references.py [--fresh]

`--fresh` first re-clones the working copy from the original (APFS clone, `cp -c`). Nothing is ever
written to the original. Every block must fit its sectors; none moves.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser import refs
from carin.parser.cf1.tile00 import Tile00
from carin.parser.refs import OffsetMap
from carin.parser.volume_edit import FitError, pack, reopen, write_block
from common import DATA, ISO_COPY

TILE = 0x4C184F18
ORIGINAL = Path(__file__).resolve().parents[2] / "dataset" / "NAV_DB_21708.ISO"
REPORT: list[str] = []


def log(msg: str) -> None:
    print(msg)
    REPORT.append(msg)


def twins(vol, hits, tile_id: int, omap: OffsetMap, out: dict, stats: Counter, label: str) -> None:
    """Neighbour tiles (same type, hit as a BLOCK_ID in their S6) get the new S6 offset of their twin in the edited tile."""
    for (sector, ty), _offs in sorted(hits.items()):
        if sector == tile_id >> 8 or ty not in (0x00, 0x03):
            continue
        b = vol.block(sector)
        nb = Tile00.parse(b.payload, vol.layout)
        changed = 0
        for nd in nb.nodes6:
            if nd.ext and nd.ext[0] == tile_id:
                new = omap.s6_new[nd.ext[1]]
                if new != nd.ext[1]:
                    nd.ext = (nd.ext[0], new, nd.ext[2])
                    changed += 1
        if changed:                                            # else a byte coincidence, not a neighbour
            out[sector] = (nb.build(), b, f"{label} neighbour: {changed} S6 twin offsets")
            stats[f"{label} neighbour S6 twins"] += changed


def read_hits(path: str) -> dict:
    hits = defaultdict(set)                                   # (sector, type) -> offsets
    for line in open(path):
        m = re.match(r"id=\S+ type=(\S+) sector=(\S+) offset=(\S+)", line)
        hits[(int(m[2], 16), int(m[1], 16))].add(int(m[3], 16))
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fresh", action="store_true", help="re-clone the working copy from the original first")
    ap.add_argument("--xref", default=str(DATA / "xref_4c184f18.txt"))
    args = ap.parse_args()
    assert ISO_COPY.resolve() != ORIGINAL.resolve(), "refusing to write to the original"
    if args.fresh:
        subprocess.run(["cp", "-c", str(ORIGINAL.resolve()), str(ISO_COPY)], check=True)
        log(f"fresh working copy: cp -c {ORIGINAL.name} -> {ISO_COPY.name}")

    info = json.load(open(DATA / "redraw.json"))
    assert info["fits"], "the redrawn tile does not fit"
    omap = OffsetMap.from_json(info["offsets"])
    new_tile = (DATA / f"tile_{TILE:#x}_redrawn.bin").read_bytes()
    vol = reopen(str(ISO_COPY))
    table = vol.layout

    hits = read_hits(args.xref)
    kinds = Counter(t for (_, t) in hits)
    log(f"blocks holding the tile's BLOCK_ID: {dict(sorted((hex(k), v) for k, v in kinds.items()))}")

    out: dict[int, tuple[bytes, object, str]] = {}            # sector -> (payload, block, what)
    own_sector = TILE >> 8
    blk = vol.block(own_sector)
    assert Tile00.parse(blk.payload, table).build() == blk.payload, "copy does not hold the untouched tile"
    out[own_sector] = (new_tile, blk, "the tile")

    stats = Counter()
    for (sector, ty), offs in sorted(hits.items()):
        if sector == own_sector:
            continue
        b = vol.block(sector)
        if ty == 0x0E:
            data, notes = refs.patch_0e(b.payload, table, TILE, omap)
            stats["0x0E runs"] += len(notes)
        elif ty == 0x10:
            data, notes = refs.patch_10(b.payload, table, TILE, omap)
            stats["0x10 entries"] += len(notes)
        elif ty == 0x17:
            data, notes = refs.patch_17(b.payload, TILE, omap)
            stats["0x17 offsets"] += len(notes)
        elif ty == 0x04:
            data, notes = refs.patch_04(b.payload, omap)
            stats["0x04 records"] += 1
        elif ty == 0x00:
            continue                                           # neighbours: handled by twins()
        else:
            continue                                           # 0x09, 0x03: BLOCK_ID only; 0x16: coincidence
        if data != b.payload:
            out[sector] = (data, b, f"type {ty:#04x}: " + "; ".join(notes[:2]) + (" ..." if len(notes) > 2 else ""))
    twins(vol, hits, TILE, omap, out, stats, "street")

    cinfo = json.load(open(DATA / "redraw_coarse.json"))                  # the coarse tile (step 5b)
    assert cinfo["fits"], "the redrawn coarse tile does not fit"
    COARSE = cinfo["tile"]
    comap = OffsetMap.from_json(cinfo["offsets"])
    cblk = vol.block(COARSE >> 8)
    assert Tile00.parse(cblk.payload, table).build() == cblk.payload
    out[COARSE >> 8] = ((DATA / f"tile_{COARSE:#x}_redrawn.bin").read_bytes(), cblk, "the coarse tile")
    twins(vol, read_hits(str(DATA / "xref_5c58a51c.txt")), COARSE, comap, out, stats, "coarse")
    log(f"to rewrite: {len(out)} blocks, " + ", ".join(f"{v} {k}" for k, v in stats.items()))

    raws = {}
    for sector, (payload, b, what) in out.items():
        try:
            raws[sector] = pack(vol, b, payload)
        except FitError as e:
            raise SystemExit(f"STOP: {e}")
    log("every block fits its sectors; writing")
    for sector, raw in raws.items():
        write_block(vol, str(ISO_COPY), sector, raw)

    vol2 = reopen(str(ISO_COPY))
    bad = [hex(s) for s, (payload, _b, _w) in out.items() if vol2.block(s).payload != payload]
    log(f"read back from the copy: {len(out) - len(bad)} / {len(out)} blocks decode to what was written" +
        (f"; DIFFER: {bad}" if bad else ""))
    for sector, (_p, _b, what) in sorted(out.items())[:6]:
        log(f"  {sector:#x}: {what}")
    (DATA / "patch_references.log").write_text("\n".join(REPORT) + "\n")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
