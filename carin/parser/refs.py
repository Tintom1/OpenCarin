"""References into a type 0x00 tile from other blocks, and how to rewrite them after the tile was edited.

Who points into a street tile (census of tile 0x4c184f18 of DVD 21708, `carindb-rs xref`, 2026-10-01;
`docs/carindb/03-road-network.md` section 6.7 "Editing a tile: references from outside"):

  type 0x0E  S2 link  (u32 BLOCK_ID at +16, u16 S4 offset at +20, u16 count at +22): a run of consecutive S4 records
  type 0x10  street directory entry (u32 BLOCK_ID, u16 S4 offset, u16 flag), 8 B, in section 4 of the block
  type 0x17  TMC location: x, y (u32), idA, idB (u32), offA, offB (u16): a BLOCK_ID is followed by the S4 offset in it
  type 0x04  house numbers: header +0x0C BLOCK_ID, one 10-byte record per S4 record, in S4 order
  type 0x00  neighbour tiles: S6 +8 BLOCK_ID / +12 u16 offset of the twin in *this* tile's S6
  also: 0x09 spatial cell, 0x03 S8 level link: BLOCK_ID only (no offsets)

All of them hold offsets of the tile as it was; `OffsetMap` says where each S4 record and S6 node went.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

S4_REC = 32


@dataclass
class OffsetMap:
    """Old in-tile offset -> new offset for the S4 records and S6 nodes of an edited tile."""
    seg_base: int                                   # old S4 start
    seg_order: list[int]                            # old S4 offsets, in index order
    seg_new: dict[int, Optional[int]]               # old offset -> new offset (None = record removed)
    seg_name: dict[int, int]                        # old offset -> S2 record index (street)
    s6_new: dict[int, int] = field(default_factory=dict)
    new_seg_base: int = 0
    new_order: list[int] = field(default_factory=list)   # new S4 offsets in new index order, as old offset or None for new records
    new_count: int = 0

    # -- construction ------------------------------------------------------------------------------
    @classmethod
    def capture(cls, tile) -> "OffsetMap":
        """Snapshot of an untouched tile; call `finish(tile)` after the edit."""
        seg, _n5, n6 = tile.offsets()
        _, start, _ = tile._layout()
        m = cls(seg_base=start[4], seg_order=[seg[id(s)] for s in tile.segs], seg_new={}, seg_name={})
        m._objs = {id(s): seg[id(s)] for s in tile.segs}
        m._n6 = {id(n): n6[id(n)] for n in tile.nodes6}
        for s in tile.segs:
            m.seg_name[seg[id(s)]] = s.name
        return m

    def finish(self, tile) -> "OffsetMap":
        seg, _n5, n6 = tile.offsets()
        _, start, _ = tile._layout()
        self.new_seg_base = start[4]
        self.new_count = len(tile.segs)
        self.seg_new = {o: None for o in self.seg_order}
        self.new_order = []
        for s in tile.segs:
            old = self._objs.get(id(s))
            if old is not None:
                self.seg_new[old] = seg[id(s)]
            self.new_order.append(old)
        self.s6_new = {o: n6[i] for i, o in self._n6.items() if i in n6}
        return self

    # -- queries -----------------------------------------------------------------------------------
    def index(self, off: int) -> int:
        i, r = divmod(off - self.seg_base, S4_REC)
        if r or not 0 <= i < len(self.seg_order):
            raise ValueError(f"{off} is not an S4 record boundary of the old tile")
        return i

    def run(self, off: int, count: int) -> Optional[tuple[int, int]]:
        """New (offset, count) of a run of consecutive old records; None if none of them is left.
        The surviving records must still be consecutive."""
        i = self.index(off)
        keep = [self.seg_new[self.seg_order[k]] for k in range(i, i + count)]
        keep = [k for k in keep if k is not None]
        if not keep:
            return None
        if any(b - a != S4_REC for a, b in zip(keep, keep[1:])):
            raise ValueError(f"run at {off} (+{count}) is no longer consecutive after the edit")
        return keep[0], len(keep)

    def target(self, off: int) -> Optional[int]:
        """New offset of one old record; a removed record is replaced by the nearest surviving record
        of the same street (S2 record), None if the street has none left in the tile."""
        new = self.seg_new[off]
        if new is not None:
            return new
        i = self.index(off)
        name = self.seg_name[off]
        best = None
        for k, o in enumerate(self.seg_order):
            if self.seg_new[o] is not None and self.seg_name[o] == name and \
                    (best is None or abs(k - i) < abs(best[0] - i)):
                best = (k, self.seg_new[o])
        return best[1] if best else None

    # -- (de)serialisation -------------------------------------------------------------------------
    def to_json(self) -> dict:
        return {"seg_base": self.seg_base, "seg_order": self.seg_order, "seg_new": {str(k): v for k, v in self.seg_new.items()},
                "seg_name": {str(k): v for k, v in self.seg_name.items()}, "s6_new": {str(k): v for k, v in self.s6_new.items()},
                "new_seg_base": self.new_seg_base, "new_order": self.new_order, "new_count": self.new_count}

    @classmethod
    def from_json(cls, d: dict) -> "OffsetMap":
        return cls(d["seg_base"], d["seg_order"], {int(k): v for k, v in d["seg_new"].items()},
                   {int(k): v for k, v in d["seg_name"].items()}, {int(k): v for k, v in d["s6_new"].items()},
                   d["new_seg_base"], d["new_order"], d["new_count"])


# ---------------------------------------------------------------------------------------------------
# patchers: decoded payload in, decoded payload out, plus a log of what changed

def patch_0e(payload: bytes, table: dict, tile_id: int, m: OffsetMap) -> tuple[bytes, list[str]]:
    """Rewrite the S4 offset / count of every S2 link of a 0x0E block that points at `tile_id`."""
    from .cf1.constants import T_DESC_BASE, T_REC_S2_0E
    out, notes = bytearray(payload), []
    base, rec = table[T_DESC_BASE], table[T_REC_S2_0E]
    e2_off, e2_cnt = struct.unpack_from(">HH", payload, base + 8)
    for i in range(e2_cnt):
        b = e2_off + i * rec
        bid, off, cnt = struct.unpack_from(">IHH", payload, b + 16)
        if bid != tile_id:
            continue
        new = m.run(off, cnt)
        if new is None:
            raise ValueError(f"0x0E S2 link {i}: every record of the run (offset {off}, {cnt}) was removed")
        if new != (off, cnt):
            struct.pack_into(">HH", out, b + 20, *new)
            notes.append(f"S2[{i}] ({off},{cnt}) -> {new}")
    return bytes(out), notes


def patch_10(payload: bytes, table: dict, tile_id: int, m: OffsetMap) -> tuple[bytes, list[str]]:
    """Rewrite the S4 offset of every street-directory entry (section 4, 8 B) of a 0x10 block naming `tile_id`."""
    from .cf1.constants import T_DESC_BASE
    out, notes = bytearray(payload), []
    s4, n4 = struct.unpack_from(">HH", payload, table[T_DESC_BASE] + 4 * 4)
    for k in range(n4):
        o = s4 + 8 * k
        bid, off, fl = struct.unpack_from(">IHH", payload, o)
        if bid != tile_id:
            continue
        new = m.target(off)
        if new is None:
            raise ValueError(f"0x10 entry {k}: street of the removed record at {off} has no record left")
        if new != off:
            struct.pack_into(">H", out, o + 4, new)
            notes.append(f"entry {k}: {off} -> {new}" + ("" if m.seg_new[off] is not None else " (record removed, same street)"))
    return bytes(out), notes


def patch_17(payload: bytes, tile_id: int, m: OffsetMap) -> tuple[bytes, list[str]]:
    """Rewrite the S4 offsets of TMC location records of a 0x17 block: x, y, idA, idB, offA, offB (u32 u32 u32 u32 u16 u16)."""
    out, notes = bytearray(payload), []
    pat = struct.pack(">I", tile_id)
    p = payload.find(pat)
    while p >= 0:
        prev = struct.unpack_from(">I", payload, p - 4)[0] if p >= 4 else 0
        as_a = (prev >> 24) == 0x0D                                  # a y coordinate precedes idA
        o = p + (8 if as_a else 6)
        off = struct.unpack_from(">H", payload, o)[0]
        if off:
            new = m.target(off)
            if new is None:
                raise ValueError(f"0x17 record at {p:#x}: offset {off} has no surviving record")
            if new != off:
                struct.pack_into(">H", out, o, new)
                notes.append(f"{p:#x} id{'A' if as_a else 'B'}: {off} -> {new}")
        p = payload.find(pat, p + 4)
    return bytes(out), notes


def patch_04(payload: bytes, m: OffsetMap) -> tuple[bytes, list[str]]:
    """Reorder a 0x04 block's house-number records to the edited tile: one 10-byte record per S4 record.
    Removed records are dropped (their numbers are lost), new ones carry no numbers. The block keeps its length."""
    off0, n = struct.unpack_from(">HH", payload, 8)               # descriptor {0x0010, N} at +8, BLOCK_ID at +0x0C
    if n != len(m.seg_order):
        raise ValueError(f"0x04 holds {n} records, the tile had {len(m.seg_order)}")
    recs = [payload[off0 + 10 * i: off0 + 10 * (i + 1)] for i in range(n)]
    old_index = {o: i for i, o in enumerate(m.seg_order)}
    empty = struct.pack(">5H", 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0)
    new = [recs[old_index[o]] if o is not None else empty for o in m.new_order]
    lost = [recs[old_index[o]] for o, nw in m.seg_new.items() if nw is None]
    notes = [f"{len(recs)} -> {len(new)} records; {sum(1 for r in lost if r != empty)} removed record(s) had house numbers"]
    tail = payload[off0 + 10 * n:]
    out = bytearray(payload[:off0]) + b"".join(new) + tail
    if len(out) > len(payload):
        extra = len(out) - len(payload)
        if any(out[len(payload):]) or extra > len(tail) or any(tail[-extra:]):
            raise ValueError("the grown 0x04 block no longer fits its decoded size")
        out = out[:len(payload)]
    out += bytes(len(payload) - len(out))
    struct.pack_into(">H", out, 10, len(new))
    return bytes(out), notes
