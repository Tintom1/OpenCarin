"""
Full annotated listing of a MIPS32 (big-endian) OS-9000 module.

Writes every instruction of the module's code segment, splits it into
functions (non-leaf prologue ``sw $ra, ($sp)``) and resolves the
``$fp``-relative calls used by the CARiN MIPS firmwares
(``lui/addiu $at`` + ``addu $at, $at, $fp`` + ``jalr $at``; target =
imm + FP_BIAS).

Usage:
    python scripts/firmware/mips_listing.py <firmware> <module> <out.asm>

Example (RoadRunner DVD route planner):
    python scripts/firmware/mips_listing.py \
        build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2 rpmod build/rr_rpmod.asm
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import capstone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mips_dis import FP_BIAS, find_module, load  # noqa: E402

AT_HI = re.compile(r"^\$at, (-?0x[0-9a-f]+|\d+)$")
AT_LO = re.compile(r"^\$at, \$at, (-?0x[0-9a-f]+|-?\d+)$")


def listing(data: bytes, m):
    blob = data[m.offset:m.offset + m.size]
    start = struct.unpack_from(">I", blob, 0x30)[0]
    end = struct.unpack_from(">I", blob, 0x38)[0]
    cs = capstone.Cs(capstone.CS_ARCH_MIPS,
                     capstone.CS_MODE_MIPS32 | capstone.CS_MODE_BIG_ENDIAN)
    out = []
    for off in range(start, end, 4):
        raw = blob[off:off + 4]
        ins = next(cs.disasm(raw, off, count=1), None)
        out.append((off, raw.hex(), ins.mnemonic if ins else ".word",
                    ins.op_str if ins else f"0x{raw.hex()}"))
    return out


def fp_calls(ins):
    """Map instruction offset -> absolute call target for $fp-relative jalr."""
    calls, hi = {}, None
    for off, _, mn, op in ins:
        if mn == "lui" and AT_HI.match(op):
            hi = int(AT_HI.match(op).group(1), 0) << 16
        elif mn == "addiu" and hi is not None and AT_LO.match(op):
            calls[off] = (hi + int(AT_LO.match(op).group(1), 0) + FP_BIAS) & 0xFFFFFFFF
            hi = None
    return calls


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 1
    data, mods = load(argv[1])
    m = find_module(mods, argv[2])
    ins = listing(data, m)
    starts = {off for off, _, mn, op in ins if mn == "sw" and op == "$ra, ($sp)"}
    calls = fp_calls(ins)
    with open(argv[3], "w") as fh:
        for off, raw, mn, op in ins:
            if off in starts:
                fh.write(f"\n; ---- sub_{off:06x}\n")
            note = f"   ; -> sub_{calls[off]:06x}" if off in calls else ""
            fh.write(f"{off:06x}: {raw}  {mn:<8} {op}{note}\n")
    print(f"{argv[2]}: {len(ins)} instructions, {len(starts)} functions -> {argv[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
