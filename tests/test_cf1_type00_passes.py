"""Section 4 passes 0x15 and 0x1B of the type 0x00 CF=1 decoder (RR db_pub sub_005594)."""
import struct

from carin.parser.cf1.core import BitReader, BitWriter, Cf1Context
from carin.parser.cf1.decoder_00 import dec_b

# T[0x05] descriptor, T[0x08] S4 record, T[0x09] S4 tail, T[0x4c] S13 record
TABLE = {0x05: 8, 0x08: 32, 0x09: 26, 0x4C: 8}
S4, S13 = 100, 200


def _ctx(bits):
    """S4: 2 records at 100 plus the sentinel at 164; S13: 1 record at 200."""
    dst = bytearray(256)
    struct.pack_into(">HH", dst, 8 + 4 * 4, S4, 2)
    struct.pack_into(">HH", dst, 8 + 4 * 13, S13, 1)
    w = BitWriter()
    for width, value in bits:
        w.put(width, value)
    ctx = Cf1Context(table=TABLE, src=w.to_bytes() + bytes(4), dst=dst)
    ctx.bits = BitReader(ctx.src, 0)
    ctx.pb = {"s13": 1}                  # bits_needed(e13.count + 1)
    return ctx


def _u16(ctx, off):
    return struct.unpack_from(">H", ctx.dst, off)[0]


def test_pass_15_reads_the_sentinel_record():
    # Mk3 db_pub +0x3c50, RR sub_005594 +0x5db8: after the loop, kind 0x15
    # reads the sentinel's +0x16 too; the port used to stop one record short
    ctx = _ctx([(1, 1), (1, 0), (1, 0), (1, 1), (1, 1)])
    dec_b(ctx, 0x15)
    assert [_u16(ctx, S4 + 32 * k + 0x16) for k in range(3)] == [S13, S13, S13 + 8]
    assert ctx.bits.pos == 5


def test_pass_1b_two_bytes_or_previous_no_sentinel():
    # RR sub_005594 +0x5b5c..0x5bc8: flag, then getbits(8) into +0x18 and +0x19
    ctx = _ctx([(1, 1), (8, 0x03), (8, 0x00), (1, 0), (1, 1)])
    dec_b(ctx, 0x1B)
    assert [_u16(ctx, S4 + 32 * k + 0x18) for k in range(3)] == [0x0300, 0x0300, 0]
    assert ctx.bits.pos == 18            # the trailing 1 is left unread
