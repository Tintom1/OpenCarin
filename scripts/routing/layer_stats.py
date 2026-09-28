"""
Compare decoded CF=1 scale-layer blocks with the plain (CF=0) and zlib (CF=2)
blocks of the same type: S0 category codes, draw flags, records per section,
S3 record size, share of named S1/S2 records.

Usage:
    python scripts/routing/layer_stats.py [--iso PATH ...] [--top 8]
"""

from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser.iso import CarinVolume, IsoImage  # noqa: E402
from oracle_14_16 import DISCS, TYPES, layout        # noqa: E402


def _u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iso", action="append")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args(argv[1:])
    for path in args.iso or DISCS:
        vol = CarinVolume(IsoImage(path))
        vol.calibrate()
        T = vol.layout
        st = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        for b in vol.walk():
            if b.type not in TYPES:
                continue
            d = vol.block(b.sector).data
            g = st[(b.type, "CF1" if b.comp == 1 else "CF0/2")]
            g["n"]["blocks"] += 1
            L, _end = layout(d, T)
            for i, (off, vo, n, rec, cnt) in enumerate(L):
                g["recs"][f"e{i}"] += cnt
            g["s3"][L[3][3]] += 1
            for k in range(L[0][2] - 1):                 # without the terminator
                r = L[0][0] + 4 * k
                g["code"][d[r]] += 1
                g["draw"][d[r + 1]] += 1
            for name, sec in (("S1", L[1]), ("S2", L[2])):
                for k in range(max(sec[2] - 1, 0)):
                    g["named"][(name, _u16(d, sec[0] + k * sec[3]) != 0)] += 1
        print(f"\n### {path}")
        for t in TYPES:
            for cf in ("CF0/2", "CF1"):
                g = st.get((t, cf))
                if not g:
                    continue
                n = g["n"]["blocks"]
                per = " ".join(f"{k}={v / n:.1f}" for k, v in sorted(g["recs"].items()))
                ncode = sum(g["code"].values()) or 1
                codes = " ".join(f"{c:#04x}:{v / ncode:.1%}"
                                 for c, v in g["code"].most_common(args.top))
                draw = g["draw"][1] / (sum(g["draw"].values()) or 1)
                named = {s: g["named"][(s, True)] / ((g["named"][(s, True)]
                         + g["named"][(s, False)]) or 1) for s in ("S1", "S2")}
                print(f"{t:#04x} {cf:<5} blocks={n:<6} mean count/blk: {per}")
                print(f"      S3 rec {dict(g['s3'])}  draw=1 {draw:.1%}  "
                      f"named S1 {named['S1']:.1%} S2 {named['S2']:.1%}  codes {len(g['code'])}")
                print(f"      top codes {codes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
