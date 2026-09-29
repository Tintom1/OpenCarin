"""
Structural oracle for BLOCK_TYPE 0x00 (street-level tile).

The oracle is independent of the CF=1 decoder: it reads the section layout
itself, from the block's descriptor and the disc's RECORD_SIZE_TABLE
(`vol.layout`), and checks the decoded bytes of any block, whatever its
COMPRESSION_FLAG. CF=0 and CF=2 blocks are the ground truth: every check
must pass on all of them before it is applied to CF=1 output (`--cf 0,2`).

Layout (descriptor at T[0x05], fifteen {u16 off, u16 count} entries e0..e14):
  record size   S0-S2 T[0x40], S3 T[0x12], S4 T[0x08], S5 T[0x10], S6 T[0x06],
                S7 T[0x0c], S9 T[0x0f], S10 T[0x14], S11 T[0x13], S12 T[0x15],
                S13 T[0x4c], S14 T[0x59]; S8 is always empty in 0x00
  records       count, except S3 and S4: count + 1 (the decoder copies S3 with
                one extra record and writes a sentinel S4 record)
  placement     in index order from the prologue T[0x0b], each section starting
                at the end of the previous one rounded up to 4 bytes; an empty
                section sits at that position ("virtual offset")
  (measured on every CF=0/CF=2 0x00 block of 21708 and 21734)

Checks (name: what):
  desc      every non-empty section lies inside the block, S8 empty
  contig    placement above
  s4_node   S4 +0x00/+0x02 on a S5 or S6 record start (every record but the sentinel)
  s4_shape  S4 +0x04 on a S7 boundary, non-decreasing, sentinel = S7 end
  s4_next   S4 +0x06/+0x08 zero or a S4 record start
  s4_ptr    S4 +0x12 -> S10, +0x14 -> S12, +0x16 -> S13, +T[0x09]+4 -> S11:
            on a boundary, non-decreasing, sentinel = end of the target section.
            +0x16 is written by pass 0x15, sentinel included
  s4_name   S4 +T[0x09] on a S2 boundary (every record but the sentinel)
  s56_s4    S5/S6 +0x04 on a S4 record start
  names     S2 +0 zero or a string start; S14 +0 a string start
  p17_s1    S1 +0x06/+0x08: 0 on the first record, then on a S14 boundary,
            non-decreasing (pass 0x17)
  p17_mono  S0 +0x04, S2 +0x06, S2 +0x08 non-decreasing (pass 0x17)
  p18       S4 +0x18: low byte 0 on every record; 0 on the sentinel
  CF=1 only:
  text      each dec_text range is (0, 0) or starts at or after the end of the
            sections and ends inside the block
  pad       the bit after the last one read is 1 and every later bit of the
            block is 0. The 1 follows pass 0x1B, the last one the RoadRunner
            reads (db_pub sub_005e6c +0x6e70); no firmware reads the 1 itself
            (docs/carindb/04-cf1-codec.md 9.11.12). With --pad-zero the 1 is
            not expected (for decoders that stop earlier).

"Boundary" includes the one-past-the-end offset; a "string start" is an offset
at or after the end of the sections that is the end itself or follows a NUL.

`--dump18 FILE` writes, for every checked block, the S4 records' (+0x0B,
+0x10, +0x18) to a pickle for scripts/codec_cf1/pass18_baseline.py.

Usage:
    python scripts/codec_cf1/oracle_00.py [--iso PATH ...] [--cf 0,2|1]
        [--sample N --seed S] [--dump18 FILE] [--pad-zero] [-j N]
"""

from __future__ import annotations

import argparse
import collections
import pickle
import random
import struct
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser import cf1                       # noqa: E402
from carin.parser.iso import CarinVolume, IsoImage  # noqa: E402

DISCS = ["dataset/NAV_DB_21708.ISO", "dataset/NAV_DB_21734.ISO"]
# section -> RECORD_SIZE_TABLE index of its record size (S8 has none in 0x00)
REC = {0: 0x40, 1: 0x40, 2: 0x40, 3: 0x12, 4: 0x08, 5: 0x10, 6: 0x06, 7: 0x0C,
       9: 0x0F, 10: 0x14, 11: 0x13, 12: 0x15, 13: 0x4C, 14: 0x59}
PLUS1 = {3, 4}


def _u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def layout(d: bytes, T: dict):
    """{section: (virtual offset, records, record size, count)} and the end of the sections."""
    ent = [struct.unpack_from(">HH", d, T[0x05] + 4 * i) for i in range(15)]
    cur, out = T[0x0B], {}
    for i, key in REC.items():
        off, cnt = ent[i]
        n = cnt + (i in PLUS1) if cnt else 0
        vo = off if cnt else cur
        out[i] = (vo, n, T[key], cnt)
        cur = (vo + n * T[key] + 3) & ~3
    return ent, out, cur


def check(d: bytes, T: dict, ctx=None, raw=None, pad_zero=False):
    """List of (check, byte offset, detail) failures for one decoded block."""
    fails = []

    def fail(name, off, detail):
        fails.append((name, off, detail))

    ent, L, end = layout(d, T)
    # desc
    if ent[8][1]:
        fail("desc", T[0x05] + 32, f"e8 count {ent[8][1]}")
    for i, (vo, n, rec, cnt) in L.items():
        if cnt and vo + n * rec > len(d):
            fail("desc", T[0x05] + 4 * i, f"e{i} off={vo} n={n} rec={rec} len={len(d)}")
    if end > len(d):
        fail("desc", -1, f"sections end {end} > len {len(d)}")
    if fails:
        return fails
    # contig
    cur = T[0x0B]
    for i, (vo, n, rec, cnt) in L.items():
        if cnt and vo != cur:
            fail("contig", T[0x05] + 4 * i, f"e{i} off={vo} expected {cur}")
            return fails
        cur = (vo + n * rec + 3) & ~3

    def bounds(i, end_too=True):
        vo, n, rec, _ = L[i]
        return {vo + k * rec for k in range(n + end_too)}

    def sec_end(i):
        vo, n, rec, _ = L[i]
        return vo + n * rec

    vo4, n4, r4, c4 = L[4]
    tail = T[0x09]
    recs = [vo4 + k * r4 for k in range(n4)]
    body = recs[:-1]
    starts4 = bounds(4, False)
    # s4_node
    b56 = bounds(5, False) | bounds(6, False)
    for r in body:
        for f in (0, 2):
            if _u16(d, r + f) not in b56:
                fail("s4_node", r + f, f"S4 +{f} = {_u16(d, r + f)} not a S5/S6 record")
                break
    # s4_shape and s4_ptr
    for name, f, sec in (("s4_shape", 0x04, 7), ("s4_ptr", 0x12, 10), ("s4_ptr", 0x14, 12),
                         ("s4_ptr", 0x16, 13), ("s4_ptr", tail + 4, 11)):
        if not recs:
            break
        vals = [_u16(d, r + f) for r in recs]
        b = bounds(sec)
        bad = next((k for k, v in enumerate(vals) if v not in b), None)
        if bad is not None:
            fail(name, recs[bad] + f, f"S4[{bad}] +{f:#x} = {vals[bad]} not on S{sec} boundary")
        elif any(a > b_ for a, b_ in zip(vals, vals[1:])):
            fail(name, -1, f"S4 +{f:#x} decreasing (-> S{sec})")
        elif vals[-1] != sec_end(sec):
            fail(name, recs[-1] + f, f"sentinel +{f:#x} = {vals[-1]} != S{sec} end {sec_end(sec)}")
    # s4_next
    for r in body:
        for f in (6, 8):
            v = _u16(d, r + f)
            if v and v not in starts4:
                fail("s4_next", r + f, f"S4 +{f} = {v} not a S4 record")
                break
    # s4_name
    b2 = bounds(2)
    for r in body:
        if _u16(d, r + tail) not in b2:
            fail("s4_name", r + tail, f"S4 +{tail:#x} = {_u16(d, r + tail)} not on S2 boundary")
            break
    # s56_s4
    for sec in (5, 6):
        vo, n, rec, _ = L[sec]
        for k in range(n):
            if _u16(d, vo + k * rec + 4) not in starts4:
                fail("s56_s4", vo + k * rec + 4, f"S{sec}[{k}] +4 not a S4 record")
                break

    # names
    def string_start(p):
        return p == end or (end < p < len(d) and d[p - 1] == 0)

    for sec, zero_ok in ((2, True), (14, False)):
        vo, n, rec, _ = L[sec]
        for k in range(n):
            p = _u16(d, vo + k * rec)
            if not (zero_ok and p == 0) and not string_start(p):
                fail("names", vo + k * rec, f"S{sec}[{k}] +0 = {p} not a string start (end {end})")
                break
    # p17_s1
    vo, n, rec, _ = L[1]
    b14 = bounds(14)
    for f in (6, 8):
        vals = [_u16(d, vo + k * rec + f) for k in range(n)]
        if vals and vals[0]:
            fail("p17_s1", vo + f, f"S1[0] +{f} = {vals[0]}")
        elif any(v not in b14 for v in vals[1:]):
            fail("p17_s1", vo + f, f"S1 +{f} not on S14 boundary")
        elif any(a > b_ for a, b_ in zip(vals, vals[1:])):
            fail("p17_s1", vo + f, f"S1 +{f} decreasing")
    # p17_mono
    for sec, f in ((0, 4), (2, 6), (2, 8)):
        vo, n, rec, _ = L[sec]
        vals = [_u16(d, vo + k * rec + f) for k in range(n)]
        if any(a > b_ for a, b_ in zip(vals, vals[1:])):
            fail("p17_mono", vo + f, f"S{sec} +{f} decreasing")
    # p18
    for k, r in enumerate(recs):
        v = _u16(d, r + 0x18)
        if v & 0xFF or (k == len(recs) - 1 and v):
            fail("p18", r + 0x18, f"S4[{k}] +0x18 = {v:#06x}")
            break
    # CF=1 only
    if ctx is not None:
        for s, e in ctx.texts:
            if (s, e) != (0, 0) and not (end <= s <= e < len(d)):
                fail("text", -1, f"dec_text range ({s}, {e}), sections end {end}, len {len(d)}")
        br = ctx.bits
        total = (len(raw) - br.base) * 8

        def bit(i):
            return (raw[br.base + (i >> 3)] >> (7 - (i & 7))) & 1

        pos = br.pos
        if pos > total - (not pad_zero):
            fail("pad", len(raw), f"read {pos - total} bits past the block")
        elif not pad_zero and not bit(pos):
            fail("pad", br.base + (pos >> 3), "no 1 bit after the last read")
        else:
            pos += not pad_zero
            for i in range(pos, total):
                if bit(i):
                    fail("pad", br.base + (i >> 3),
                         f"non-zero bit {i - br.pos} bits after the last read "
                         f"({total - br.pos} left)")
                    break
    return fails


def s4_fields(d: bytes, T: dict):
    """(+0x0B, +0x10, +0x18) of every S4 record except the sentinel."""
    _, L, _ = layout(d, T)
    vo, n, rec, _ = L[4]
    return [(d[vo + k * rec + 0x0B], d[vo + k * rec + 0x10], _u16(d, vo + k * rec + 0x18))
            for k in range(max(n - 1, 0))]


# ---- driver -----------------------------------------------------------------

_W = {}


def _init(path, subrel, dump, pad_zero):
    vol = CarinVolume(IsoImage(path))
    vol.subrel = subrel
    _W.update(vol=vol, dump=dump, pad_zero=pad_zero)


def _run(item):
    sector, cf, length = item
    vol = _W["vol"]
    raw = vol.read_sectors(sector, length)
    ctx = None
    try:
        if cf == 0:
            d = raw
        elif cf == 2:
            d = raw[:8] + zlib.decompress(raw[8:])
        else:
            ctx = cf1.decode_ctx(raw, vol.layout, vol.db_rel, vol.subrel, vol.sector_size)
            d = bytes(ctx.dst)
    except Exception as exc:  # noqa: BLE001 - reported as a failure
        return item, [("decode", -1, f"{type(exc).__name__}: {exc}")], None
    fails = check(d, vol.layout, ctx, raw, _W["pad_zero"])
    fields = s4_fields(d, vol.layout) if _W["dump"] else None
    return item, fails, fields


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iso", action="append")
    ap.add_argument("--cf", default="0,1,2")
    ap.add_argument("--subrel", type=int, default=None,
                    help="CF=1 sub-revision (default: CarinVolume.calibrate)")
    ap.add_argument("--sample", type=int, default=0, help="random blocks per disc and CF (0 = all)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dump18", default=None)
    ap.add_argument("--pad-zero", action="store_true",
                    help="CF=1: expect only zeros after the last bit read")
    ap.add_argument("--examples", type=int, default=1)
    ap.add_argument("-j", "--jobs", type=int, default=8)
    args = ap.parse_args(argv[1:])
    cfs = {int(c) for c in args.cf.split(",")}
    rc, dump = 0, {}
    for path in args.iso or DISCS:
        vol = CarinVolume(IsoImage(path))
        todo = [(b.sector, b.comp, b.length) for b in vol.walk()
                if b.type == 0x00 and b.comp in cfs]
        if args.sample:
            rng = random.Random(args.seed)
            by_cf = collections.defaultdict(list)
            for it in todo:
                by_cf[it[1]].append(it)
            todo = [it for cf in sorted(by_cf)
                    for it in rng.sample(by_cf[cf], min(args.sample, len(by_cf[cf])))]
        subrel = args.subrel
        if subrel is None:
            subrel = vol.calibrate() if 1 in cfs else vol.subrel
        print(f"\n### {path}  DB-REL {vol.db_rel}  subrel {subrel}")
        tally = collections.Counter()
        checks = collections.defaultdict(collections.Counter)
        examples = collections.defaultdict(list)
        with Pool(args.jobs, _init, (path, subrel, bool(args.dump18), args.pad_zero)) as pool:
            for (s, cf, _l), fails, fields in pool.imap_unordered(_run, todo, chunksize=16):
                tally[(cf, "total")] += 1
                tally[(cf, "pass" if not fails else "fail")] += 1
                if fields is not None:
                    dump.setdefault(path, {})[(s, cf)] = fields
                for name in {f[0] for f in fails}:
                    checks[cf][name] += 1
                    if len(examples[(cf, name)]) < args.examples:
                        f = next(f for f in fails if f[0] == name)
                        examples[(cf, name)].append((s, f[1], f[2]))
        print(f"{'CF':>2} {'total':>7} {'pass':>7} {'fail':>7}")
        for cf in sorted(cfs):
            if not tally[(cf, "total")]:
                continue
            print(f"{cf:>2} {tally[(cf, 'total')]:>7} {tally[(cf, 'pass')]:>7} "
                  f"{tally[(cf, 'fail')]:>7}")
            for name, n in sorted(checks[cf].items()):
                print(f"        {name:<9} {n:>6} blocks")
                for s, off, det in examples[(cf, name)]:
                    print(f"            e.g. sector {s} byte {off}: {det}")
            if tally[(cf, "fail")]:
                rc = 1
    if args.dump18:
        with open(args.dump18, "wb") as fh:
            pickle.dump(dump, fh)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
