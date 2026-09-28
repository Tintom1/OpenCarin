import pytest

from carin.parser.cf1.core import BitWriter, Cf1Context, Cf1Error, bits_needed
from carin.parser.cf1.decoder_00 import dec_text, enc_text


def _roundtrip(blob: bytes, start: int) -> bytearray:
    src = bytearray(start) + blob
    ptrbits = bits_needed(len(src) + 64)
    bw = BitWriter()
    enc_text(bw, src, start, len(src) - 1, ptrbits)
    ctx = Cf1Context(table={}, src=bw.to_bytes() + bytes(8), dst=bytearray(len(src) + 64))
    ctx.ptrbits = ptrbits
    ctx.bits_init()
    dec_text(ctx, floor=start)
    return ctx.dst[:len(src)]


def test_text_roundtrip_covers_every_code_length():
    # a/e (1 bit), s/t/r/NUL (2), space..o (3), accented (7), escaped ASCII (7)
    blob = "aest r\0dghilno\0àéü\0m1-(b)\0".encode("latin-1")
    assert bytes(_roundtrip(blob, 40)[40:]) == blob


def test_text_floor_blocks_writes_below_it():
    blob = b"road\0"
    ptrbits = bits_needed(128)
    bw = BitWriter()
    enc_text(bw, bytearray(8) + blob, 8, 8 + len(blob) - 1, ptrbits)
    ctx = Cf1Context(table={}, src=bw.to_bytes() + bytes(8), dst=bytearray(128))
    ctx.ptrbits = ptrbits
    ctx.bits_init()
    dec_text(ctx, floor=16)
    assert not any(ctx.dst)


def test_text_rejects_bytes_without_a_code():
    with pytest.raises(Cf1Error):
        enc_text(BitWriter(), b"a!b", 0, 2, 8)
