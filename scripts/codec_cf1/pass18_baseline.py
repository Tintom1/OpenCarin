"""
Statistics of the section 4 field +0x18 of BLOCK_TYPE 0x00 tiles.

Run on plain tiles (CF=0 and CF=2, the default) it is the baseline that the
CF=1 decoder's +0x18 must reproduce; `--cf 1` computes the same numbers from
the CF=1 decoder's output.

Per disc and CF:
  values    distribution of the u16 +0x18 over all segments (sentinel excluded)
  role      +0x18 & 3 against the slip role derived from +0x0B & 0x0F, as the
            RR route planner does below DB-REL 27 (rpmod sub_0630cc):
            1, 8 -> 1; 2, 9 -> 2; 3, 0xA -> 3; anything else -> 0.
            The high byte is used: +0x18 is stored as two bytes (RR db_pub
            sub_005594 +0x5b8c..0x5ba4 writes +0x18 and +0x19 with getbits(8)).
  repeat    fraction of segments (from the second of each tile) whose +0x18
            equals the previous segment's
  first     distribution of the first segment's +0x18
  by class  +0x18 per road class / class-6 subtype (+0x10)

Usage:
    python scripts/codec_cf1/pass18_baseline.py [--iso PATH ...] [--cf 0,2|1]
        [--sample N --seed S] [-j N]
"""

from __future__ import annotations

import argparse
import collections
import random
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser import cf1                       # noqa: E402
from carin.parser.iso import CarinVolume, IsoImage  # noqa: E402
from oracle_00 import DISCS, s4_fields             # noqa: E402

ROLE = {1: 1, 8: 1, 2: 2, 9: 2, 3: 3, 0xA: 3}

_W = {}


def _init(path, subrel):
    vol = CarinVolume(IsoImage(path))
    vol.subrel = subrel
    _W["vol"] = vol


def _run(item):
    sector, cf, length = item
    vol = _W["vol"]
    raw = vol.read_sectors(sector, length)
    if cf == 0:
        d = raw
    elif cf == 2:
        d = raw[:8] + zlib.decompress(raw[8:])
    else:
        try:
            d = cf1.decode_block(raw, vol.layout, vol.db_rel, vol.subrel, vol.sector_size)
        except Exception:  # noqa: BLE001
            return item, None
    return item, s4_fields(d, vol.layout)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iso", action="append")
    ap.add_argument("--cf", default="0,2")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("-j", "--jobs", type=int, default=8)
    args = ap.parse_args(argv[1:])
    cfs = {int(c) for c in args.cf.split(",")}
    for path in args.iso or DISCS:
        vol = CarinVolume(IsoImage(path))
        todo = [(b.sector, b.comp, b.length) for b in vol.walk()
                if b.type == 0x00 and b.comp in cfs]
        if args.sample:
            todo = random.Random(args.seed).sample(todo, min(args.sample, len(todo)))
        subrel = vol.calibrate() if 1 in cfs else vol.subrel
        values, first, role, byclass = (collections.Counter() for _ in range(4))
        rep = [0, 0]
        tiles = failed = segs = 0
        with Pool(args.jobs, _init, (path, subrel)) as pool:
            for _item, fields in pool.imap_unordered(_run, todo, chunksize=16):
                if fields is None:
                    failed += 1
                    continue
                tiles += 1
                if not fields:
                    continue
                first[fields[0][2]] += 1
                for k, (b0b, b10, v) in enumerate(fields):
                    segs += 1
                    values[v] += 1
                    role[(ROLE.get(b0b & 0x0F, 0), (v >> 8) & 3)] += 1
                    cls = b10 & 0x0F
                    key = f"class {cls}" + (f" sub {(b10 >> 4) & 7}" if cls == 6 else "")
                    byclass[(key, v)] += 1
                    if k:
                        rep[0] += v == fields[k - 1][2]
                        rep[1] += 1
        print(f"\n### {path}  CF {sorted(cfs)}  tiles {tiles}  segments {segs}"
              + (f"  decode failures {failed}" if failed else ""))
        print("values:", ", ".join(f"{v:#06x} {n}" for v, n in sorted(values.items())))
        agree = sum(n for (r, m), n in role.items() if r == m)
        print(f"role (+0x0B) vs +0x18 & 3: agree {agree} / {segs}")
        for (r, m), n in sorted(role.items()):
            if r != m:
                print(f"    role {r}  +0x18&3 {m}: {n}")
        print(f"repeat previous: {rep[0]} / {rep[1]}"
              + (f" ({rep[0] / rep[1]:.4f})" if rep[1] else ""))
        print("first segment:", ", ".join(f"{v:#06x} {n}" for v, n in sorted(first.items())))
        print("non-zero by class:")
        for (key, v), n in sorted(byclass.items()):
            if v:
                tot = sum(m for (k2, _), m in byclass.items() if k2 == key)
                print(f"    {key:<14} {v:#06x} {n:>6} / {tot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
