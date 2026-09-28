"""CF=1 Codec parsers and encoders."""
import struct
from .constants import *
from .core import Cf1Error, SECTOR, Cf1Context, bits_needed
from .decoder_00 import decode_type00
from .decoder_0e import decode_type0E, encode_type0E, decode_s2_coords, decode_s2_links
from .decoder_14 import decode_type14_16

DECODERS = {
    0x00: decode_type00,
    0x0E: decode_type0E,
    0x14: decode_type14_16,
    0x15: decode_type14_16,
    0x16: decode_type14_16,
}


def decode_block(raw: bytes, table: dict[int, int], dbrel: int,
                 subrel: int = 9, sector_size: int = SECTOR) -> bytes:
    """Decodifica un blocco CF=1. `raw` sono i byte su disco, header incluso."""
    btype = struct.unpack_from(">H", raw, 4)[0]
    cf, usize = raw[6], raw[7]
    if not cf & 1:
        raise Cf1Error(f"blocco non compresso (COMPRESSION_FLAG={cf})")
    if btype not in DECODERS:
        raise Cf1Error(f"BLOCK_TYPE {btype:#04x}: decoder non ancora portato")
    total = usize * sector_size
    ctx = Cf1Context(table=table, src=raw, dst=bytearray(total), dbrel=dbrel,
                     subrel=subrel)
    ctx.ptrbits = bits_needed(total)
    DECODERS[btype](ctx)
    ctx.dst[6] = 0
    ctx.dst[7] = 0
    if ctx.m_hi:            # 0x0E: preserve M_lo/M_hi so decode_s2_coords can read them
        ctx.dst[6] = ctx.m_lo
        ctx.dst[7] = ctx.m_hi
    elif hasattr(ctx, "widths") and ctx.widths: # 0x00: preserve widths
        ctx.dst[6] = ctx.widths[0]
        ctx.dst[7] = ctx.widths[1]
    return bytes(ctx.dst)
