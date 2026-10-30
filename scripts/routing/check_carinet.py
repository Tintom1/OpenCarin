"""
Check the layout of the CARINET file (RDS-TMC event texts) against the disc.

Claims tested (01-architecture.md §4.5):
  1. Root block 0x66 at sector 0 (2 sectors): S0 = (BLOCK_ID, last event code) of the 0x64 chain
     plus a terminator {0, 0x07FF}; S1 = (BLOCK_ID, last event code `limit`, text set) of every
     0x65 block, in chain order.
  2. Every BLOCK_ID in the file is (sector << 8) | length in 512-byte sectors and matches the
     block it points to; the 0x64 chain starts at sector 2, the 0x65 blocks follow it without a
     gap and end with the file; next / previous pointers (+0x0C / +0x10) link the 0x65 blocks in
     S1 order, the +0x14 high byte of a 0x65 block is its text set.
  3. 0x65: records (event code, phrase offset) ascend by code, the last code is `limit`, every
     offset is a NUL-terminated string inside the block.
  4. 0x64: one record per event code (low 11 bits of the key); the codes ascend within a block and
     the last one is the S0 limit; the codes are the union of the codes of the text sets. Key and
     attribute word stay in range: nature (key >> 11 & 3) 0..2, directionality (key >> 13) 0..2,
     duration (bits 4-6) 0..4, urgency (bits 7-8) 0..2, update class (bits 9-14) 1..39, bit 15 clear.
Reported, not failed: codes missing from a text set; events with an attribute-word quantifier
(low nibble 1..12) whose text has no `Q` placeholder (the German and Danish phrases do not use it);
text sets without a language in the `0x0A` country records of --carindb.

Usage:
    python scripts/routing/check_carinet.py PATH [--carindb PATH [--sector-size 512]]

PATH is the CARINET file, or an ISO image that holds /CARINET.
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.carinet import (EVENT_TYPE, ROOT_TYPE, TEXT_TYPE, UNIT, parse_events, parse_texts,
                                  read_carinet)
from carin.parser.iso import CarinVolume, IsoImage, open_image


def load(path: str) -> bytes:
    try:
        img = IsoImage(path)
    except ValueError:
        return Path(path).read_bytes()
    for name, f in img.files.items():
        if name.upper().lstrip("/") == "CARINET":
            return img.read(f, 0, f.size)
    raise SystemExit("no /CARINET in the image")


def check(data: bytes) -> Tuple[Counter, dict]:
    """Run the structural checks. Returns (failures, report)."""
    fail: Counter = Counter()
    c = read_carinet(data)                      # raises ValueError if the chains do not parse
    s0, n0 = struct.unpack_from(">HH", data, 8)

    # 2. layout of the file
    fail["root BLOCK_ID != 2"] += struct.unpack_from(">I", data, 0)[0] != 2
    sector = 2
    ev_blocks = []
    block_id = struct.unpack_from(">I", data, s0)[0]
    while block_id:
        fail["0x64 block does not follow the previous one"] += (block_id >> 8) != sector
        sector = (block_id >> 8) + (block_id & 0xFF)
        ev_blocks.append(block_id)
        block_id = struct.unpack_from(">I", data, (block_id >> 8) * UNIT + 0x0C)[0]
    fail["0x65 blocks do not start after the 0x64 chain"] += c.blocks[0].block_id >> 8 != sector
    end = sector
    for i, b in enumerate(c.blocks):
        start, size = (b.block_id >> 8) * UNIT, (b.block_id & 0xFF) * UNIT
        blk = data[start:start + size]
        fail["0x65 blocks not contiguous"] += (b.block_id >> 8) != end
        end = (b.block_id >> 8) + (b.block_id & 0xFF)
        hdr = struct.unpack_from(">IHHHH", blk, 0)
        fail["0x65 header != (BLOCK_ID, type)"] += hdr[0] != b.block_id or hdr[1] != TEXT_TYPE
        nxt, prv = struct.unpack_from(">II", blk, 0x0C)
        fail["0x65 next != following S1 block"] += nxt != (c.blocks[i + 1].block_id if i + 1 < len(c.blocks) else 0)
        fail["0x65 prev != preceding S1 block"] += prv != (c.blocks[i - 1].block_id if i else 0)
        fail["0x65 +0x14 high byte != text set"] += blk[0x14] != b.group
        # 3. records
        off, cnt = struct.unpack_from(">HH", blk, 8)
        codes = [struct.unpack_from(">H", blk, off + 4 * k)[0] for k in range(cnt)]
        fail["0x65 codes not strictly ascending"] += codes != sorted(set(codes))
        fail["0x65 last code != limit"] += codes[-1] != b.limit
        parse_texts(blk)                         # every offset is a NUL-terminated string
    fail["0x65 blocks do not end with the file"] += end * UNIT != len(data)

    # 1. root S0 over the 0x64 chain
    recs = [struct.unpack_from(">IHH", data, s0 + 8 * k) for k in range(n0 + 1)]
    fail["S0 is not the 0x64 chain + terminator"] += [r[0] for r in recs[:-1]] != ev_blocks or recs[-1][:2] != (0, 0x7FF)
    codes64 = []
    for r in recs[:-1]:
        blk = data[(r[0] >> 8) * UNIT:((r[0] >> 8) + (r[0] & 0xFF)) * UNIT]
        fail["0x64 header != (BLOCK_ID, type)"] += struct.unpack_from(">IH", blk, 0) != (r[0], EVENT_TYPE)
        ev = parse_events(blk)
        fail["0x64 codes not ascending"] += [e.code for e in ev] != sorted(e.code for e in ev)
        fail["0x64 last code != S0 limit"] += ev[-1].code != r[1]
        fail["0x64 key or attribute word out of range"] += sum(
            e.key_bits & 3 > 2 or e.directionality > 2 or e.attrs >> 15 or (e.attrs >> 4) & 7 > 4
            or (e.attrs >> 7) & 3 > 2 or not 1 <= e.update_class <= 39 for e in ev)
        codes64 += [e.code for e in ev]
    fail["0x64 has a code twice"] += len(codes64) != len(set(codes64))
    union = set().union(*(set(t) for t in c.texts.values()))
    fail["0x64 codes != codes of the text sets"] += set(codes64) != union
    fail["root type"] += struct.unpack_from(">H", data, 4)[0] != ROOT_TYPE

    # reported
    report = {"events": len(c.events), "blocks": len(c.blocks), "sets": {}}
    for g, t in sorted(c.texts.items()):
        noq = [k for k, e in c.events.items() if e.quantifier is not None and k in t and "Q" not in t[k]]
        report["sets"][g] = {"codes": len(t), "missing": len(union - set(t)), "quantifier_without_Q": len(noq)}
    report["quantifier"] = Counter(e.quantifier for e in c.events.values())
    report["nature"] = Counter(e.nature for e in c.events.values())
    report["duration"] = Counter(e.duration for e in c.events.values())
    report["urgency"] = Counter(e.urgency for e in c.events.values())
    report["update_classes"] = len({e.update_class for e in c.events.values()})
    return fail, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--carindb", help="also list the LANGUAGE ids of the 0x0A country records")
    ap.add_argument("--sector-size", type=int, default=None)
    args = ap.parse_args()

    fail, rep = check(load(args.path))
    print(f"{rep['events']} events, {rep['blocks']} text blocks, {len(rep['sets'])} text sets")
    for g, s in rep["sets"].items():
        print(f"  set {g:2}: {s['codes']} codes, {s['missing']} missing, "
              f"{s['quantifier_without_Q']} quantifier events without Q")
    print("quantifier (attrs & 0xF, None = 0xF):", dict(sorted(rep["quantifier"].items(), key=lambda x: (x[0] is None, x[0]))))
    print("distinct update classes (attrs >> 9 & 0x3F):", rep["update_classes"])
    for name in ("nature", "duration", "urgency"):
        print(f"{name}:", dict(rep[name]))

    if args.carindb:
        vol = CarinVolume(open_image(args.carindb), sector_size=args.sector_size)
        vol.calibrate()
        langs = Counter()
        for b in vol.walk():
            if b.type == 0x0A:
                p = vol.block(b.sector).payload
                off, cnt = struct.unpack_from(">HH", p, 8)
                langs.update(struct.unpack_from(">H", p, off + 8 * i + 2)[0] for i in range(cnt))
        sets = set(rep["sets"])
        print("0x0A LANGUAGE ids (countries):", dict(sorted(langs.items())))
        print("  without a text set:", sorted(k for k in langs if k not in sets and k != 255),
              "| text sets no country uses:", sorted(sets - set(langs)))

    bad = {k: v for k, v in fail.items() if v}
    print("failures:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
