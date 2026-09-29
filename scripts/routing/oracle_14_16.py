"""
Structural oracle for the scale-layer blocks 0x14, 0x15, 0x16, 0x1C, 0x1D, 0x1E.

The oracle is independent of the CF=1 decoder: it reads the section layout
itself, from the block's descriptor and the disc's RECORD_SIZE_TABLE
(`vol.layout`), and checks the decoded bytes of any block, whatever its
COMPRESSION_FLAG. CF=0 and CF=2 blocks are the ground truth: every check
must pass on all of them before it is applied to CF=1 output (`--cf 0,2`).

Layout (RoadRunner `db_pub`, `bsw2` 0101; offsets inside the module):
  descriptor at T[0x05], six {u16 off, u16 count} entries e0..e5
  e0 S0  T[0x3b] B/rec, count+1 records   sub_004228 +0x42a8..0x42dc (kind 0x80)
  e1 S1  T[0x3a] B/rec, count+1 records   (kind 0x7f)
  e2 S2  T[0x3c] B/rec, count+1 records   (kind 0x81)
  e3 S3  8 B/rec if u16[T[0x05]+T[0x3f]+0x10] == 0 else 4, count records
                                          sub_004228 +0x42e0..0x4314
  e4     T[0x15] B/rec, count records     sub_004b88 +0x4e48 (DB-REL >= 20 pass)
  e5     T[0x59] B/rec, count records     sub_004b88 +0x4f18 (DB-REL >= 23 pass)

Checks (name: what, why):
  desc      every non-empty section starts at or after the prologue T[0x3d]
            and ends inside the block
  contig    non-empty sections are in index order, the first starts at
            T[0x3d] and each starts where the previous ends
  s0_code   S0 +0 <= 0x7f and +1 in {0, 1} (read with getbits(7) / getbits(1))
  s0_ptr    S0 +2 lands on a record boundary of S1 or S2 (02-geo.md 8.4),
            non-decreasing
  s3_ptr    S1 +2 then S2 +2, in order: on an S3 record boundary, non-decreasing,
            first = start of S3, last = end of S3
  s3_geo    4-byte S3: (x << sh, y << sh) inside the block's bbox size,
            sh = u16 at 0x32; 8-byte S3: X, Y inside the disc range
  s1_xy     S1 +8/+12 (i32) inside the disc range; terminator record 0, 0
  names     S1 +0 / S2 +0: 0 or the start of a string after the sections;
            terminator 0. e5 +0: start of a string
  p14_s1    S1 +0x10 == 0  (written by the DB-REL >= 20 pass)
  p14_s2    S2 +0x08 on an e4 record boundary  (DB-REL >= 20 pass)
  p17       S1 +0x12, S2 +0x0c on an e5 record boundary, or the value 4
            (DB-REL >= 23 pass)
  s2_e      S2 +0x0e: terminator 0; from the second record on, either equal
            to the previous record's or non-zero (the tail pass, see
            decoder_14._s2_tail; the firmware does not read it)
  CF=1 only:
  text      each dec_text range is (0, 0) or starts after the sections and
            ends inside the block
  pad       every bit of the block after the last one read is zero

"On a record boundary" includes the one-past-the-end offset. An empty
section's position is where the previous one ends ("virtual offset").

The disc range is the union of the bboxes (i32 x4 at 0x20) of all blocks of
the six types on the disc.

Usage:
    python scripts/routing/oracle_14_16.py [--iso PATH ...] [--cf 0,2|1]
        [--types 0x14,0x1c] [--candidate] [--legacy-eu] [-j N]

`--candidate` decodes CF=1 blocks with `decode_type14_16` even for types not
registered in `cf1.DECODERS`. `--legacy-eu` also reports the old check
(S1 X/Y inside 20 W..50 E, 25..75 N) for comparison; it is not part of PASS.
"""

from __future__ import annotations

import argparse
import collections
import struct
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser import cf1                       # noqa: E402
from carin.parser.iso import CarinVolume, IsoImage  # noqa: E402

DISCS = ["dataset/NAV_DB_21708.ISO", "dataset/NAV_DB_21734.ISO"]
TYPES = (0x14, 0x15, 0x16, 0x1C, 0x1D, 0x1E)
K = 2_000_000_000 / 360
LEGACY_EU = (int(10 * K), int(80 * K), int(25 * K), int(75 * K))  # old oracle constants
NULL_E5 = 4


def _u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def layout(d: bytes, T: dict):
    """Per-section (offset, virtual offset, records, record size) from the descriptor."""
    base = T[0x05]
    ent = [struct.unpack_from(">HH", d, base + 4 * i) for i in range(6)]
    s3 = 8 if _u16(d, base + T[0x3F] + 0x10) == 0 else 4
    rec = [T[0x3B], T[0x3A], T[0x3C], s3, T[0x15], T[0x59]]
    out, cur = [], T[0x3D]
    for i, (off, cnt) in enumerate(ent):
        n = (cnt + 1 if i < 3 else cnt) if cnt else 0
        vo = off if cnt else cur
        out.append((off, vo, n, rec[i], cnt))
        cur = vo + n * rec[i]
    return out, cur


def check(d: bytes, T: dict, disc: tuple, dbrel: int, ctx=None, raw=None, legacy=False):
    """List of (check, byte offset, detail) failures for one decoded block."""
    fails = []

    def fail(name, off, detail):
        fails.append((name, off, detail))

    L, end = layout(d, T)
    prolog = T[0x3D]
    # desc
    for i, (off, vo, n, rec, cnt) in enumerate(L):
        if cnt and not (off >= prolog and off + n * rec <= len(d)):
            fail("desc", T[0x05] + 4 * i, f"e{i} off={off} n={n} rec={rec} len={len(d)}")
    if fails:
        return fails
    # contig
    cur = prolog
    for i, (off, vo, n, rec, cnt) in enumerate(L):
        if cnt:
            if off != cur:
                fail("contig", T[0x05] + 4 * i, f"e{i} off={off} expected {cur}")
                return fails
            cur = off + n * rec
    s0, s1, s2, s3, e4, e5 = L

    def bounds(sec):
        off, vo, n, rec, cnt = sec
        return {vo + k * rec for k in range(n + 1)}

    b1 = bounds(s1) if s1[4] else set()
    b2 = bounds(s2) if s2[4] else set()
    # s0
    prev = -1
    for k in range(s0[2]):
        r = s0[0] + k * s0[3]
        if d[r] > 0x7F or d[r + 1] > 1:
            fail("s0_code", r, f"code={d[r]:#x} draw={d[r + 1]}")
        p = _u16(d, r + 2)
        if p not in b1 and p not in b2:
            fail("s0_ptr", r + 2, f"S0[{k}] -> {p} not on S1/S2 boundary")
        elif p < prev:
            fail("s0_ptr", r + 2, f"S0[{k}] -> {p} < previous {prev}")
        prev = p
    # s3_ptr
    seq = [(s[0] + k * s[3] + 2) for s in (s1, s2) if s[4] for k in range(s[2])]
    if seq:
        b3 = bounds(s3)
        vals = [_u16(d, o) for o in seq]
        for o, p in zip(seq, vals):
            if p not in b3:
                fail("s3_ptr", o, f"-> {p} not on S3 boundary [{s3[1]}, {s3[1] + s3[2] * s3[3]}]")
                break
        else:
            if any(a > b for a, b in zip(vals, vals[1:])):
                j = next(j for j in range(len(vals) - 1) if vals[j] > vals[j + 1])
                fail("s3_ptr", seq[j + 1], f"{vals[j + 1]} < previous {vals[j]}")
            if vals[0] != s3[1]:
                fail("s3_ptr", seq[0], f"first {vals[0]} != S3 start {s3[1]}")
            if vals[-1] != s3[1] + s3[2] * s3[3]:
                fail("s3_ptr", seq[-1], f"last {vals[-1]} != S3 end {s3[1] + s3[2] * s3[3]}")
    # s3_geo
    bx0, by0, bx1, by1 = struct.unpack_from(">4i", d, 0x20)
    if s3[4]:
        if s3[3] == 4:
            sh = _u16(d, 0x32)
            for k in range(s3[2]):
                r = s3[0] + 4 * k
                x, y = _u16(d, r), _u16(d, r + 2)
                if (x << sh) > bx1 - bx0 or (y << sh) > by1 - by0:
                    fail("s3_geo", r, f"S3[{k}] ({x},{y})<<{sh} outside bbox "
                         f"{bx1 - bx0}x{by1 - by0}")
                    break
        else:
            for k in range(s3[2]):
                r = s3[0] + 8 * k
                x, y = struct.unpack_from(">ii", d, r)
                if not (disc[0] <= x <= disc[2] and disc[1] <= y <= disc[3]):
                    fail("s3_geo", r, f"S3[{k}] ({x},{y}) outside disc range")
                    break
    # s1_xy + legacy
    legacy_bad = 0
    for k in range(s1[2]):
        r = s1[0] + k * s1[3]
        x, y = struct.unpack_from(">ii", d, r + 8)
        if k == s1[2] - 1:
            if (x, y) != (0, 0):
                fail("s1_xy", r + 8, f"terminator S1[{k}] X,Y = {x},{y}")
            continue
        if not (disc[0] <= x <= disc[2] and disc[1] <= y <= disc[3]):
            fail("s1_xy", r + 8, f"S1[{k}] X,Y = {x},{y} outside disc range")
        ux, uy = struct.unpack_from(">II", d, r + 8)
        if legacy and not (LEGACY_EU[0] <= ux <= LEGACY_EU[1] and LEGACY_EU[2] <= uy <= LEGACY_EU[3]):
            legacy_bad += 1

    # names
    def string_start(p):
        return p == end or (end < p < len(d) and d[p - 1] == 0)

    for name, sec in (("S1", s1), ("S2", s2)):
        for k in range(sec[2]):
            r = sec[0] + k * sec[3]
            p = _u16(d, r)
            if k == sec[2] - 1:
                if p:
                    fail("names", r, f"terminator {name}[{k}] +0 = {p}")
            elif p and not string_start(p):
                fail("names", r, f"{name}[{k}] +0 = {p} not a string start (sections end {end})")
    for k in range(e5[2]):
        r = e5[0] + 4 * k
        p = _u16(d, r)
        if not string_start(p):
            fail("names", r, f"e5[{k}] +0 = {p} not a string start (sections end {end})")
    # passes
    if dbrel >= 20:
        b4 = bounds(e4)
        for k in range(s1[2]):
            r = s1[0] + k * s1[3]
            if _u16(d, r + 0x10):
                fail("p14_s1", r + 0x10, f"S1[{k}] +0x10 = {_u16(d, r + 0x10)}")
        for k in range(s2[2]):
            r = s2[0] + k * s2[3]
            if _u16(d, r + 8) not in b4:
                fail("p14_s2", r + 8, f"S2[{k}] +8 = {_u16(d, r + 8)} not on e4 boundary")
    if dbrel >= 23:
        b5 = bounds(e5) | {NULL_E5}
        for name, sec, fo in (("S1", s1, 0x12), ("S2", s2, 0x0C)):
            for k in range(sec[2]):
                r = sec[0] + k * sec[3]
                if _u16(d, r + fo) not in b5:
                    fail("p17", r + fo, f"{name}[{k}] +{fo:#x} = {_u16(d, r + fo)} "
                         "not on e5 boundary")
    # s2_e
    if s2[4]:
        vals = [_u16(d, s2[0] + k * s2[3] + 0x0E) for k in range(s2[2])]
        if vals[-1]:
            fail("s2_e", s2[0] + (s2[2] - 1) * s2[3] + 0x0E, f"terminator +0x0e = {vals[-1]}")
        for k in range(1, s2[2] - 1):
            if vals[k] == 0 and vals[k - 1] != 0:
                fail("s2_e", s2[0] + k * s2[3] + 0x0E,
                     f"S2[{k}] +0x0e changes {vals[k - 1]} -> 0")
                break
    # CF=1 only
    if ctx is not None:
        for s, e in ctx.texts:
            if (s, e) != (0, 0) and not (end <= s <= e < len(d)):
                fail("text", -1, f"dec_text range ({s}, {e}), sections end {end}, len {len(d)}")
        br = ctx.bits
        total = (len(raw) - br.base) * 8
        if br.pos > total:
            fail("pad", len(raw), f"read {br.pos - total} bits past the block")
        else:
            for i in range(br.pos, total):
                if (raw[br.base + (i >> 3)] >> (7 - (i & 7))) & 1:
                    fail("pad", br.base + (i >> 3),
                         f"non-zero bit {i - br.pos} bits after the last read "
                         f"({total - br.pos} left)")
                    break
    if legacy:
        fails.append(("_legacy_eu", -1, legacy_bad))
    return fails


# ---- driver -----------------------------------------------------------------

_W = {}


def _init(path, subrel, candidate, legacy, disc):
    vol = CarinVolume(IsoImage(path))
    if subrel is None:
        vol.calibrate()
    else:
        vol.subrel = subrel
    _W.update(vol=vol, candidate=candidate, legacy=legacy, disc=disc)


def _run(item):
    sector, btype, cf, length = item
    vol = _W["vol"]
    raw = vol.read_sectors(sector, length)
    ctx = None
    try:
        if cf == 0:
            d = raw
        elif cf == 2:
            d = raw[:8] + zlib.decompress(raw[8:])
        else:
            dec = cf1.decode_type14_16 if _W["candidate"] else None
            ctx = cf1.decode_ctx(raw, vol.layout, vol.db_rel, vol.subrel,
                                 vol.sector_size, decoder=dec)
            d = bytes(ctx.dst)
    except Exception as exc:  # noqa: BLE001 - reported as a failure
        return item, [("decode", -1, f"{type(exc).__name__}: {exc}")], None
    fails = check(d, vol.layout, _W["disc"], vol.db_rel, ctx, raw, _W["legacy"])
    legacy = None
    if fails and fails[-1][0] == "_legacy_eu":
        legacy = fails.pop()[2]
    return item, fails, legacy


def disc_range(vol, blocks):
    r = [1 << 40, 1 << 40, -(1 << 40), -(1 << 40)]
    for s, _t, cf, length in blocks:
        raw = vol.read_sectors(s, length if cf == 2 else 1)
        d = raw[:8] + zlib.decompress(raw[8:]) if cf == 2 else raw
        x0, y0, x1, y1 = struct.unpack_from(">4i", d, 0x20)
        r = [min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)]
    return tuple(r)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iso", action="append")
    ap.add_argument("--cf", default="0,1,2")
    ap.add_argument("--types", default=",".join(f"{t:#04x}" for t in TYPES))
    ap.add_argument("--subrel", type=int, default=None,
                    help="CF=1 sub-revision (default: CarinVolume.calibrate)")
    ap.add_argument("--candidate", action="store_true")
    ap.add_argument("--legacy-eu", action="store_true")
    ap.add_argument("--examples", type=int, default=1)
    ap.add_argument("-j", "--jobs", type=int, default=8)
    args = ap.parse_args(argv[1:])
    cfs = {int(c) for c in args.cf.split(",")}
    types = {int(t, 0) for t in args.types.split(",")}
    rc = 0
    for path in args.iso or DISCS:
        vol = CarinVolume(IsoImage(path))
        allb = [(b.sector, b.type, b.comp, b.length) for b in vol.walk() if b.type in TYPES]
        disc = disc_range(vol, allb)
        todo = [b for b in allb if b[1] in types and b[2] in cfs]
        subrel = args.subrel
        if subrel is None and 1 in cfs:
            subrel = vol.calibrate()
        print(f"\n### {path}  DB-REL {vol.db_rel}  subrel {subrel}  "
              f"disc range X {disc[0]}..{disc[2]} Y {disc[1]}..{disc[3]}")
        tally = collections.Counter()
        checks = collections.defaultdict(collections.Counter)
        examples = collections.defaultdict(list)
        legacy = collections.Counter()
        with Pool(args.jobs, _init, (path, subrel, args.candidate, args.legacy_eu, disc)) as pool:
            for (s, t, cf, _l), fails, leg in pool.imap_unordered(_run, todo, chunksize=16):
                key = (t, cf)
                tally[key + ("total",)] += 1
                tally[key + ("pass" if not fails else "fail",)] += 1
                if leg is not None:
                    legacy[key + (leg > 0,)] += 1
                for name in {f[0] for f in fails}:
                    checks[key][name] += 1
                    if len(examples[key + (name,)]) < args.examples:
                        f = next(f for f in fails if f[0] == name)
                        examples[key + (name,)].append((s, f[1], f[2]))
        print(f"{'type':>5} {'CF':>2} {'total':>6} {'pass':>6} {'fail':>6}"
              + ("  legacy_eu_fail" if args.legacy_eu else ""))
        for t in sorted(types):
            for cf in sorted(cfs):
                key = (t, cf)
                if not tally[key + ("total",)]:
                    continue
                line = (f"{t:#5x} {cf:>2} {tally[key + ('total',)]:>6} "
                        f"{tally[key + ('pass',)]:>6} {tally[key + ('fail',)]:>6}")
                if args.legacy_eu:
                    line += f"  {legacy[key + (True,)]:>6}"
                print(line)
                for name, n in sorted(checks[key].items()):
                    print(f"        {name:<8} {n:>6} blocks")
                    for s, off, det in examples[key + (name,)]:
                        print(f"            e.g. sector {s} byte {off}: {det}")
                if tally[key + ("fail",)]:
                    rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
