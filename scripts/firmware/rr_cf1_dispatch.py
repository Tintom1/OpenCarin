"""
BLOCK_TYPE dispatch of the CF=1 decoders in a MIPS ``db_pub`` module.

Finds the PC-relative jump table the block decoder uses when
``COMPRESSION_FLAG == 1``::

    lhu   $t0, 6(hdr) ; andi $s3, $t0, 0xf00 ; bne $s3, 0x100, ...  (CF byte == 1)
    lhu   $t0, 4(hdr)                                              (BLOCK_TYPE)
    sltiu $ra, $t0, N ; beqz $ra, <default>
    bal   .+8 ; sll $t0, $t0, 2
    addu  $t0, $ra, $t0 ; lw $t0, 0x14($t0) ; addu $ra, $ra, $t0 ; jr $ra
    .word <N offsets from the bal return address>

and, for every BLOCK_TYPE, walks the case body (following conditional
branches, stopping at ``b``/``jalr``/``jr``) to collect the ``$fp``-relative
call targets it loads into ``$at``.

Usage:
    python scripts/firmware/rr_cf1_dispatch.py [firmware] [module]

Default: RoadRunner ``bsw2`` (the DVD reader), module ``db_pub``.
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import capstone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mips_dis import FP_BIAS, find_module, load  # noqa: E402

FW = "build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2"


def _cs():
    cs = capstone.Cs(capstone.CS_ARCH_MIPS,
                     capstone.CS_MODE_MIPS32 | capstone.CS_MODE_BIG_ENDIAN)
    cs.detail = False
    return cs


def _ins(cs, blob, off):
    return next(cs.disasm(blob[off:off + 4], off, count=1), None)


def find_table(blob: bytes):
    """Return (sltiu_off, ncases, bal_ret, table_off)."""
    cs = _cs()
    for off in range(0, len(blob) - 0x20, 4):
        a = _ins(cs, blob, off)
        if a is None or a.mnemonic != "sltiu" or not a.op_str.startswith("$ra,"):
            continue
        # switch operand is BLOCK_TYPE (hdr+4), after the CF test (hdr+6 & 0xf00)
        prev = _ins(cs, blob, off - 4)
        if prev is None or prev.mnemonic != "lhu" or not re.search(r", 4\(\$\w+\)$", prev.op_str):
            continue
        if not any((i := _ins(cs, blob, o)) is not None and i.mnemonic == "andi"
                   and i.op_str.endswith(", 0xf00") for o in range(off - 0x40, off, 4)):
            continue
        bal = next((o for o in range(off + 4, off + 0x14, 4)
                    if (i := _ins(cs, blob, o)) is not None and i.mnemonic == "bal"), None)
        if bal is None:
            continue
        ret = bal + 8                         # bal return address (after delay slot)
        lw = next((i for o in range(ret, ret + 0x10, 4)
                   if (i := _ins(cs, blob, o)) is not None and i.mnemonic == "lw"), None)
        if lw is None:
            continue
        n = int(a.op_str.split(",")[-1], 0)
        disp = int(lw.op_str.split(",")[1].strip().split("(")[0], 0)
        return off, n, ret, ret + disp
    raise SystemExit("jump table not found")


def case_calls(blob: bytes, start: int) -> list[tuple[int, int]]:
    """(site, target) of every $fp-relative call loaded on paths from `start`."""
    cs = _cs()
    out, seen, work = [], set(), [start]
    while work:
        pc = work.pop()
        while pc not in seen:
            seen.add(pc)
            ins = _ins(cs, blob, pc)
            if ins is None:
                break
            mn, op = ins.mnemonic, ins.op_str
            if mn == "addiu" and op.startswith("$at, $at,"):
                out.append((pc, (int(op.split(",")[-1], 0) + FP_BIAS) & 0xFFFFFFFF))
            if mn in ("beqz", "bnez", "beq", "bne", "beql", "bnel"):
                work.append(int(op.split(",")[-1], 0))
            if mn in ("b", "jalr", "jr"):
                dly = _ins(cs, blob, pc + 4)       # delay slot
                if dly is not None and dly.mnemonic == "addiu" and \
                        dly.op_str.startswith("$at, $at,"):
                    out.append((pc + 4, (int(dly.op_str.split(",")[-1], 0) + FP_BIAS)
                                & 0xFFFFFFFF))
                break
            pc += 4
    return sorted(set(out))


def main(argv: list[str]) -> int:
    fw = argv[1] if len(argv) > 1 else FW
    mod = argv[2] if len(argv) > 2 else "db_pub"
    data, mods = load(fw)
    m = find_module(mods, mod)
    blob = data[m.offset:m.offset + m.size]
    sl, n, ret, tab = find_table(blob)
    print(f"{fw} {mod} @ {m.offset:#x}")
    print(f"sltiu at {sl:#06x}: {n} cases; bal returns to {ret:#06x}; table at {tab:#06x}")
    groups: dict[int, list[int]] = {}
    for t in range(n):
        rel = struct.unpack_from(">i", blob, tab + 4 * t)[0]
        groups.setdefault(ret + rel, []).append(t)
    for tgt, types in sorted(groups.items(), key=lambda kv: kv[1][0]):
        calls = case_calls(blob, tgt)
        names = ", ".join(f"sub_{c:06x} (load at {s:#06x})" for s, c in calls) or "—"
        print(f"  types {','.join(f'{t:#04x}' for t in types)}")
        print(f"      case @ {tgt:#06x} -> {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
