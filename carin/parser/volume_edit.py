"""Write edited blocks back into a disc image, in place.

A block keeps its sectors: the re-encoded bytes must fit the extent the BLOCK_ID names (its low byte is
the length in sectors, repeated in every reference), the rest is zero padding. Nothing is moved.
The caller passes the path of a *copy* of the image; the original is never opened for writing here.
"""
from __future__ import annotations

import zlib

from . import cf1
from .iso import CARIN_WINDOW, CarinBlock, CarinVolume, IsoImage


class FitError(Exception):
    """The re-encoded block does not fit its sectors."""


def pack(vol: CarinVolume, blk: CarinBlock, payload: bytes) -> bytes:
    """Raw bytes of a block (header included) for a decoded `payload`, same compression as the original, padded to its extent."""
    room = blk.length * vol.sector_size
    if blk.comp == 0:
        raw = payload
    elif blk.comp == 2:
        raw = payload[:8] + zlib.compress(payload[8:], 9)
    elif blk.comp & 1:
        enc = {0x00: cf1.encode_type00, 0x0E: cf1.encode_type0E}.get(blk.type)
        if enc is None:
            raise FitError(f"no CF=1 encoder for BLOCK_TYPE {blk.type:#04x}")
        raw = enc(payload, vol.layout, vol.db_rel, vol.subrel)
    else:
        raise FitError(f"unknown COMPRESSION_FLAG {blk.comp}")
    if len(raw) > room:
        raise FitError(f"block {blk.sector:#x} (type {blk.type:#04x}): {len(raw)} bytes do not fit {room}")
    return raw + bytes(room - len(raw))


def write_block(vol: CarinVolume, image_path: str, sector: int, raw: bytes) -> None:
    """Overwrite the sectors of block `sector` (virtual CARINdb address) in the image file."""
    idx, local = divmod(sector, CARIN_WINDOW)
    off = vol.parts[idx].offset + local * vol.sector_size
    with open(image_path, "r+b") as f:
        f.seek(off)
        f.write(raw)


def reopen(image_path: str) -> CarinVolume:
    vol = CarinVolume(IsoImage(image_path))
    vol.calibrate()
    return vol
