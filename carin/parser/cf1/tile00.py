"""Editable, layout-independent model of a decoded type 0x00 block (DB-REL >= 27).

`Tile00.parse(decoded, table)` turns the bytes of a street tile into objects that
refer to each other directly (a segment holds its two node objects, the next
segment of each node cycle, its shape points, its turns ...). `build()` lays the
sections out again in the canonical order and writes every pointer field of the
catalog below, so records can be added or removed without chasing offsets.
Two tiles that differ only in where their sections sit have equal `graph()`s.

Pointer catalog (docs/carindb/03-road-network.md section 6.7, 04-cf1-codec.md 9.11.4;
every one of these is an absolute in-tile byte offset of the decoded block):

  S4 (segment, 32 B)   +0x00 +0x02  node in S5 or S6        +0x04  first shape point (S7)
                       +0x06 +0x08  next segment in the cycle of the start / end node (S4, 0 = none)
                       +0x12 first S10 entry   +0x14 first S12 triple   +0x16 first S13 entry
                       T[9]+0 street record (S2)               T[9]+4 first S11 signpost
                       The S7 / S10 / S11 / S12 / S13 pointers are monotone: a segment owns the
                       entries from its pointer to the next segment's (the sentinel closes the last).
  S5, S6 (node)        +0x04 first segment of the node cycle (S4, 0 = none)
  S3 (level group)     +0 first segment (S4)   +2 first node (S5); the sentinel is the end
  S10, S13 (turn, toll) +4 target segment (S4) when the u32 BLOCK_ID at +0 is the tile's own
  S11 (signpost)       +0 +2 text
  S0 +0 text, +4 S14 | S1 +0 +2 text, +4 S0, +6 +8 S14 | S2 +0 +2 text, +4 S1, +6 S14 | S14 +0 text
  Not pointers: S0 +2, S2 +8, S9, S12, the S6 twin fields (+8 u32 BLOCK_ID, +12 u16 offset *in the
  neighbour tile*) and the header words after the descriptor.
"""
from __future__ import annotations

import struct
from typing import Optional

from .constants import (T_DESC_BASE, T_PROLOG, T_REC_S0, T_REC_S3, T_REC_S4, T_REC_S5, T_REC_S6,
                        T_REC_S7, T_REC_S9, T_REC_S10, T_REC_S11, T_REC_S12, T_REC_S13,
                        T_REC_S14, T_TAIL_S4)

SECTOR = 512
ORDER = (0, 1, 2, 3, 4, 5, 6, 7, 9, 8, 10, 11, 12, 13, 14)     # physical order of the sections
S8_REC = 4                                                        # u32 BLOCK_ID per cell (coarse tiles)


class TileError(Exception):
    """The tile does not follow the canonical layout this model assumes."""


class Node:
    """A section 5 or 6 record. `first` is the first segment of its cycle."""

    def __init__(self, sec: int, u: int, v: int, flags: int, first: "Seg | None" = None,
                 ext: "tuple | None" = None):
        self.sec, self.u, self.v, self.flags, self.first, self.ext = sec, u, v, flags, first, ext

    @property
    def xy(self):
        return (self.u, self.v)


class Seg:
    """A section 4 record with everything it owns or points at."""

    PTR = (0x00, 0x02, 0x04, 0x06, 0x08, 0x12, 0x14, 0x16)

    def __init__(self, raw: bytes, tail: Optional[int]):
        """`tail` is the offset of the street-record pointer (T[9]); None for the 26-byte records of coarse tiles."""
        self.raw = bytearray(raw)
        self.tail = tail
        for o in self.PTR + (() if tail is None else (tail, tail + 4)):
            self.raw[o:o + 2] = b"\0\0"
        self.a: Optional[Node] = None
        self.b: Optional[Node] = None
        self.nxt_a: Optional[Seg] = None
        self.nxt_b: Optional[Seg] = None
        self.shape: list[bytes] = []          # S7 records (6 B)
        self.turns: list[list] = []           # S10: [tid, Seg | int, flag]
        self.tmc: list[bytes] = []            # S12 triples (6 B)
        self.tolls: list[list] = []           # S13: [tid, Seg | int, flag]
        self.signs: list[list] = []           # S11: [text0, text2, flag] (text relative to the blob, None = null)
        self.name = 0                         # index of the S2 record

    # field helpers on the raw bytes (offsets of table 6.7)
    def u8(self, o): return self.raw[o]
    def u16(self, o): return struct.unpack_from(">H", self.raw, o)[0]
    def set16(self, o, v): struct.pack_into(">H", self.raw, o, v & 0xFFFF)

    def clone(self) -> "Seg":
        s = Seg(self.raw, self.tail)
        s.raw = bytearray(self.raw)
        s.name = self.name
        return s


class Tile00:
    """A parsed type 0x00 tile; see the module docstring."""

    def __init__(self):
        self.table: dict = {}
        self.prolog = b""
        self.tile_id = 0
        self.segs: list[Seg] = []
        self.s4_sentinel = b""
        self.nodes5: list[Node] = []
        self.nodes6: list[Node] = []
        self.groups: list[list[int]] = []         # S3: [segments, S5 nodes] per level group
        self.passive: dict[int, list[list]] = {}  # S0, S1, S2, S14: records as lists of field values
        self.raw_sections: dict[int, list[bytes]] = {}   # S8, S9
        self.gaps: dict[int, bytes] = {}          # bytes between a section's end and the next start
        self.blob = b""
        self.extra_sectors = 0
        self.hdr_words = b""

    # ------------------------------------------------------------------ parse
    @classmethod
    def parse(cls, d: bytes, table: dict) -> "Tile00":
        from .decoder_00 import text_end
        t = cls()
        t.table = table
        T = table
        t.coarse = False
        rec4, tail = T[T_REC_S4], T[T_TAIL_S4]
        if rec4 != 32 or tail != 26:
            raise TileError(f"only the DB-REL >= 27 record layout is modelled (rec {rec4}, tail {tail})")
        base = T[T_DESC_BASE]
        ent = {i: struct.unpack_from(">HH", d, base + 4 * i) for i in range(15)}
        if struct.unpack_from(">H", d, 4)[0] in (1, 2, 3):        # BLOCK_TYPE 0x01-0x03
            rec4, tail = 26, None                       # coarse tiles (0x01-0x03): no street record, flags or signposts
            t.coarse = True
        rec = {0: T[T_REC_S0], 1: T[T_REC_S0], 2: T[T_REC_S0], 3: T[T_REC_S3], 4: rec4,
               5: T[T_REC_S5], 6: T[T_REC_S6], 7: T[T_REC_S7], 8: S8_REC, 9: T[T_REC_S9],
               10: T[T_REC_S10], 11: T[T_REC_S11], 12: T[T_REC_S12], 13: T[T_REC_S13], 14: T[T_REC_S14]}
        extra = {3: 1, 4: 1}
        t.tile_id = struct.unpack_from(">I", d, 0)[0]
        t.prolog = bytes(d[:T[T_PROLOG]])
        start = {s: ent[s][0] for s in ORDER}
        count = {s: ent[s][1] for s in ORDER}
        pos = T[T_PROLOG]
        t.zero_empty = set()
        for s in ORDER:
            if not count[s] and start[s] == 0 and pos:
                t.zero_empty.add(s)                    # an empty section may be written as offset 0 (coarse S14)
                start[s] = pos
            if start[s] != pos:
                raise TileError(f"S{s} starts at {start[s]}, expected {pos} (gap {start[s] - pos})")
            end = pos + (count[s] + extra.get(s, 0)) * rec[s]
            nxt = ORDER[ORDER.index(s) + 1] if s != 14 else None
            if nxt is None:
                gap = 0
                pos = end
            else:
                gap = (end if not count[nxt] and ent[nxt][0] == 0 else ent[nxt][0]) - end
                if gap < 0:
                    raise TileError(f"S{s} overlaps S{nxt}")
                t.gaps[s] = bytes(d[end:end + gap])
                pos = end + gap
        text_start = pos
        t.blob = bytes(d[text_start:text_end(d, text_start) + 1]) if text_start < len(d) else b""
        used = text_start + len(t.blob)
        t.extra_sectors = (len(d) - -(-used // SECTOR) * SECTOR) // SECTOR
        if t.extra_sectors < 0 or any(d[used:]):
            raise TileError("data after the name blob")
        if (len(d) - text_start - len(t.blob)) and any(d[used:]):
            raise TileError("non-zero padding")
        t._text_start = text_start

        def idx_of(v: int, sec: int, what: str, allow_null=False) -> Optional[int]:
            if v == 0 and allow_null:
                return None
            i, m = divmod(v - start[sec], rec[sec])
            if m or not 0 <= i <= count[sec]:                  # index == count is the end of the section
                raise TileError(f"{what}: {v} is not a record boundary of S{sec}")
            return i

        def text_rel(v: int, what: str) -> Optional[int]:
            if v == 0:
                return None                                    # null pointer (rel 0 is the blob's first byte)
            if not text_start <= v <= text_start + len(t.blob):
                raise TileError(f"{what}: {v} is outside the name blob")
            return v - text_start

        # nodes (S5, S6)
        n5, n6 = [], []
        by_off = {}
        for sec, lst in ((5, n5), (6, n6)):
            for i in range(count[sec]):
                o = start[sec] + rec[sec] * i
                u, v, first, flags = struct.unpack_from(">HHHH", d, o)
                ext = struct.unpack_from(">IHH", d, o + 8) if sec == 6 else None
                if sec == 6 and rec[6] != 16:
                    raise TileError("S6 record is not 16 B")
                nd = Node(sec, u, v, flags, ext=ext)
                nd._first = first
                lst.append(nd)
                by_off[o] = nd
        t.nodes5, t.nodes6 = n5, n6

        # segments
        s4 = start[4]
        n4 = count[4]
        segs = [Seg(d[s4 + rec4 * i: s4 + rec4 * (i + 1)], tail) for i in range(n4)]
        seg_by_off = {s4 + rec4 * i: segs[i] for i in range(n4)}
        sent = d[s4 + rec4 * n4: s4 + rec4 * (n4 + 1)]
        t.s4_sentinel = bytes(sent)

        def ru16(o): return struct.unpack_from(">H", d, o)[0]

        def seg_ref(v, what):
            if v == 0:
                return None
            if v not in seg_by_off:
                raise TileError(f"{what}: {v} is not a segment")
            return seg_by_off[v]

        for nd in n5 + n6:
            nd.first = seg_ref(nd._first, "node first")
            del nd._first
        for i, sg in enumerate(segs):
            o = s4 + rec4 * i
            for f, attr in ((0x00, "a"), (0x02, "b")):
                v = ru16(o + f)
                if v not in by_off:
                    raise TileError(f"S4[{i}] +{f:#x}: {v} is not a node")
                setattr(sg, attr, by_off[v])
            sg.nxt_a = seg_ref(ru16(o + 0x06), "next start")
            sg.nxt_b = seg_ref(ru16(o + 0x08), "next end")
            if tail is not None:
                sg.name = idx_of(ru16(o + tail), 2, "street record")
        # ranges owned by each segment: S7, S10, S11, S12, S13
        fields = [(0x04, 7), (0x12, 10), (0x14, 12), (0x16, 13)] + ([(tail + 4, 11)] if tail is not None else [])
        sent_ptr = {f: ru16(s4 + rec4 * n4 + f) for f, _ in fields}
        for f, sec in fields:
            ptrs = [ru16(s4 + rec4 * i + f) for i in range(n4)] + [sent_ptr[f]]
            end_sec = start[sec] + count[sec] * rec[sec]
            if ptrs[-1] != end_sec or any(a > b for a, b in zip(ptrs, ptrs[1:])) or \
               (n4 and ptrs[0] != start[sec]):
                raise TileError(f"S4 +{f:#x} -> S{sec} is not a monotone cover of the section")
            for i, sg in enumerate(segs):
                ents = [bytes(d[p:p + rec[sec]]) for p in range(ptrs[i], ptrs[i + 1], rec[sec])]
                if (ptrs[i + 1] - ptrs[i]) % rec[sec]:
                    raise TileError(f"S4[{i}] range in S{sec} is not whole records")
                if sec == 7:
                    sg.shape = ents
                elif sec == 12:
                    sg.tmc = ents
                elif sec in (10, 13):
                    lst = []
                    for e in ents:
                        tid, off, fl = struct.unpack(">IHH", e)
                        lst.append([tid, seg_by_off[off] if tid == t.tile_id and off in seg_by_off else
                                    (off if tid != t.tile_id else _bad(off, i, sec)), fl])
                    (sg.turns if sec == 10 else sg.tolls).extend(lst)
                else:
                    for e in ents:
                        p0, p2, fl = struct.unpack(">HHH", e)
                        sg.signs.append([text_rel(p0, "S11 +0"), text_rel(p2, "S11 +2"), fl])
        t.segs = segs

        # S3 level groups
        s3 = start[3]
        firsts = [struct.unpack_from(">HH", d, s3 + 4 * k) for k in range(count[3] + 1)]
        sg4 = [idx_of(a, 4, "S3 segment") for a, _ in firsts]
        sg5 = [idx_of(b, 5, "S3 node") for _, b in firsts]
        if sg4[0] != 0 or sg5[0] != 0 or sg4[-1] != n4 or sg5[-1] != count[5] or \
           any(x > y for x, y in zip(sg4, sg4[1:])) or any(x > y for x, y in zip(sg5, sg5[1:])):
            raise TileError("S3 groups do not tile S4 and S5")
        t.groups = [[sg4[k + 1] - sg4[k], sg5[k + 1] - sg5[k]] for k in range(count[3])]

        # passive sections
        ptr_spec = {0: {0: "t", 4: 14}, 1: {0: "t", 2: "t", 4: 0, 6: 14, 8: 14},
                    2: {0: "t", 2: "t", 4: 1, 6: 14}, 14: {0: "t"}}
        for s in (0, 1, 2, 14):
            recs = []
            for i in range(count[s]):
                o = start[s] + rec[s] * i
                if s == 14:
                    f = [struct.unpack_from(">H", d, o)[0], d[o + 2], d[o + 3]]
                else:
                    f = list(struct.unpack_from(">5H", d, o))
                for fo, tgt in ptr_spec.get(s, {}).items():
                    k = fo // 2 if s != 14 else 0
                    v = f[k]
                    if tgt == "t":
                        f[k] = ("t", text_rel(v, f"S{s}[{i}] +{fo}")) if v else 0
                    else:
                        f[k] = ("S", tgt, idx_of(v, tgt, f"S{s}[{i}] +{fo}", allow_null=True)) if v else 0
                recs.append(f)
            t.passive[s] = recs
        for s in (8, 9):
            t.raw_sections[s] = [bytes(d[start[s] + rec[s] * i: start[s] + rec[s] * (i + 1)])
                                 for i in range(count[s])]
        t._start, t._count, t._rec = start, count, rec
        t.rec4, t.tail = rec4, tail
        from ..geometry import tile_frame
        t.frame = tile_frame(bytes(d), table)
        return t

    # ------------------------------------------------------------------ build
    def _layout(self):
        """(section counts, section start offsets, name blob start) of the tile as it would be built."""
        T = self.table
        rec = self._rec
        segs = self.segs
        count = {0: len(self.passive[0]), 1: len(self.passive[1]), 2: len(self.passive[2]),
                 3: len(self.groups), 4: len(segs), 5: len(self.nodes5), 6: len(self.nodes6),
                 7: sum(len(s.shape) for s in segs), 8: len(self.raw_sections[8]),
                 9: len(self.raw_sections[9]), 10: sum(len(s.turns) for s in segs),
                 11: sum(len(s.signs) for s in segs), 12: sum(len(s.tmc) for s in segs),
                 13: sum(len(s.tolls) for s in segs), 14: len(self.passive[14])}
        extra = {3: 1, 4: 1}
        start, pos = {}, T[T_PROLOG]
        for s in ORDER:
            start[s] = pos
            pos += (count[s] + extra.get(s, 0)) * rec[s] + len(self.gaps.get(s, b""))
        return count, start, pos

    def offsets(self):
        """In-tile byte offsets of the current model: (segments, S5 nodes, S6 nodes), each {id(obj): offset}."""
        count, start, _ = self._layout()
        rec = self._rec
        return ({id(s): start[4] + rec[4] * i for i, s in enumerate(self.segs)},
                {id(n): start[5] + rec[5] * i for i, n in enumerate(self.nodes5)},
                {id(n): start[6] + rec[6] * i for i, n in enumerate(self.nodes6)})

    def build(self) -> bytes:
        T = self.table
        rec4, tail = self.rec4, self.tail
        rec = dict(self._rec)
        segs = self.segs
        n4 = len(segs)
        count, start, text_start = self._layout()
        fields = [(0x04, 7), (0x12, 10), (0x14, 12), (0x16, 13)] + ([(tail + 4, 11)] if tail is not None else [])
        extra = {3: 1, 4: 1}
        total = text_start + len(self.blob)
        size = (-(-total // SECTOR) + self.extra_sectors) * SECTOR
        out = bytearray(size)
        out[:len(self.prolog)] = self.prolog
        if self.coarse and self.prolog[6] == 2:                    # zlib block: header +7 is the decoded size in sectors
            out[7] = size // SECTOR
        base = T[T_DESC_BASE]
        for s in range(15):
            struct.pack_into(">HH", out, base + 4 * s, 0 if (s in self.zero_empty and not count[s]) else start[s], count[s])
        node_off = {}
        for sec, lst in ((5, self.nodes5), (6, self.nodes6)):
            for i, nd in enumerate(lst):
                node_off[id(nd)] = start[sec] + rec[sec] * i
        seg_off = {id(sg): start[4] + rec4 * i for i, sg in enumerate(segs)}
        p16 = lambda o, v: struct.pack_into(">H", out, o, v)

        def seg_ptr(sg):
            return seg_off[id(sg)] if sg is not None else 0

        def text_abs(v):
            return text_start + v if v is not None else 0

        # nodes
        for sec, lst in ((5, self.nodes5), (6, self.nodes6)):
            for nd in lst:
                o = node_off[id(nd)]
                struct.pack_into(">HHHH", out, o, nd.u, nd.v, seg_ptr(nd.first), nd.flags)
                if sec == 6:
                    struct.pack_into(">IHH", out, o + 8, *nd.ext)
        # segments and the ranges they own
        cur = {7: start[7], 10: start[10], 11: start[11], 12: start[12], 13: start[13]}
        for i, sg in enumerate(segs):
            o = start[4] + rec4 * i
            out[o:o + rec4] = sg.raw
            p16(o, node_off[id(sg.a)])
            p16(o + 2, node_off[id(sg.b)])
            p16(o + 6, seg_ptr(sg.nxt_a))
            p16(o + 8, seg_ptr(sg.nxt_b))
            if tail is not None:
                p16(o + tail, start[2] + rec[2] * sg.name)
            for f, sec in fields:
                p16(o + f, cur[sec])
            for e in sg.shape:
                out[cur[7]:cur[7] + 6] = e
                cur[7] += 6
            for lst, sec in ((sg.turns, 10), (sg.tolls, 13)):
                for tid, tgt, fl in lst:
                    struct.pack_into(">IHH", out, cur[sec], tid, seg_off[id(tgt)] if isinstance(tgt, Seg) else tgt, fl)
                    cur[sec] += 8
            for e in sg.tmc:
                out[cur[12]:cur[12] + 6] = e
                cur[12] += 6
            for p0, p2, fl in sg.signs:
                struct.pack_into(">HHH", out, cur[11], text_abs(p0), text_abs(p2), fl)
                cur[11] += 6
        o = start[4] + rec4 * n4                                   # sentinel
        out[o:o + rec4] = self.s4_sentinel
        for f, sec in fields:
            p16(o + f, cur[sec])
        # S3
        g4, g5 = 0, 0
        for k, (a, b) in enumerate(self.groups + [[0, 0]]):
            struct.pack_into(">HH", out, start[3] + 4 * k, start[4] + rec4 * g4, start[5] + rec[5] * g5)
            g4 += a
            g5 += b
        # passive sections
        ptr_spec = {0: {0: "t", 4: 14}, 1: {0: "t", 2: "t", 4: 0, 6: 14, 8: 14},
                    2: {0: "t", 2: "t", 4: 1, 6: 14}, 14: {0: "t"}}
        for s in (0, 1, 2, 14):
            for i, f in enumerate(self.passive[s]):
                o = start[s] + rec[s] * i
                vals = []
                for k, v in enumerate(f):
                    if isinstance(v, tuple):
                        v = text_abs(v[1]) if v[0] == "t" else start[v[1]] + rec[v[1]] * v[2]
                    vals.append(v)
                if s == 14:
                    struct.pack_into(">HBB", out, o, *vals)
                else:
                    struct.pack_into(">5H", out, o, *vals)
        for s in (8, 9):
            for i, r in enumerate(self.raw_sections[s]):
                out[start[s] + rec[s] * i: start[s] + rec[s] * (i + 1)] = r
        for s, g in self.gaps.items():
            e = start[s] + (count[s] + extra.get(s, 0)) * rec[s]
            out[e:e + len(g)] = g
        out[text_start:text_start + len(self.blob)] = self.blob
        return bytes(out)

    # ------------------------------------------------------------------ editing
    # Rules the unit needs (03-road-network.md 6.7): a segment's start node is the end with the lower
    # (x, y); the S5 nodes are (x, y)-sorted inside their level group; level group k holds the
    # segments of road class k (+0x10 & 15) and the S5 nodes whose lowest class is k; the segments at a
    # node form a cycle, clockwise by the bearing leaving the node, from the smallest.
    # `build()` does not enforce them: `check()` reports what is broken, `normalize()` repairs the
    # derived parts (node order, node cycles).

    def seg_slice(self, g: int) -> tuple[int, int]:
        lo = sum(x[0] for x in self.groups[:g])
        return lo, lo + self.groups[g][0]

    def node_slice(self, g: int) -> tuple[int, int]:
        lo = sum(x[1] for x in self.groups[:g])
        return lo, lo + self.groups[g][1]

    def insert_seg(self, seg: Seg, group: int, pos: Optional[int] = None) -> None:
        """Add a segment to level group `group` (at `pos` inside the group, default the end)."""
        lo, hi = self.seg_slice(group)
        self.segs.insert(hi if pos is None else lo + pos, seg)
        self.groups[group][0] += 1

    def insert_node(self, node: Node, group: int) -> None:
        """Add an S5 node to level group `group`; `normalize()` puts it in (x, y) order."""
        lo, hi = self.node_slice(group)
        self.nodes5.insert(hi, node)
        self.groups[group][1] += 1

    def remove_seg(self, seg: Seg) -> None:
        """Remove a segment with the shape, turns and signposts it owns, and every turn or toll entry
        that names it. Node cycles are repaired by `normalize()`; nodes left without segments stay."""
        i = self.segs.index(seg)
        g = next(k for k in range(len(self.groups)) if self.seg_slice(k)[0] <= i < self.seg_slice(k)[1])
        del self.segs[i]
        self.groups[g][0] -= 1
        for s in self.segs:
            s.turns = [x for x in s.turns if x[1] is not seg]
            s.tolls = [x for x in s.tolls if x[1] is not seg]
            if s.nxt_a is seg:
                s.nxt_a = None
            if s.nxt_b is seg:
                s.nxt_b = None
        for nd in self.nodes5 + self.nodes6:
            if nd.first is seg:
                nd.first = None

    def remove_node(self, node: Node) -> None:
        lst = self.nodes5 if node.sec == 5 else self.nodes6
        i = lst.index(node)
        if node.sec == 5:
            g = next(k for k in range(len(self.groups)) if self.node_slice(k)[0] <= i < self.node_slice(k)[1])
            self.groups[g][1] -= 1
        del lst[i]

    def members(self, node: Node) -> list[tuple]:
        """(bearing, position, 'a'|'b', seg) of the segments at a node, in cycle order."""
        out = []
        for i, s in enumerate(self.segs):
            if s.a is node:
                out.append((s.raw[0x0E], i, "a", s))
            if s.b is node:
                out.append((s.raw[0x0F], i, "b", s))
        return sorted(out, key=lambda x: x[:3])

    def rebuild_cycles(self, nodes=None) -> None:
        """Set `first` of the given nodes (default all) and the next-segment links of their segments."""
        by_node: dict[int, list] = {}
        for i, s in enumerate(self.segs):
            by_node.setdefault(id(s.a), []).append((s.raw[0x0E], i, "a", s))
            by_node.setdefault(id(s.b), []).append((s.raw[0x0F], i, "b", s))
        for nd in (self.nodes5 + self.nodes6) if nodes is None else nodes:
            m = sorted(by_node.get(id(nd), []), key=lambda x: x[:3])
            if not m:
                nd.first = None
                continue
            nd.first = m[0][3]
            for k, (_, _, side, s) in enumerate(m):
                nxt = m[(k + 1) % len(m)][3]
                if nd.sec == 6 and len(m) == 1:
                    nxt = None                                       # edge nodes: a lone segment has no successor
                setattr(s, "nxt_a" if side == "a" else "nxt_b", nxt)

    def normalize(self) -> None:
        """Sort every group's S5 nodes by (x, y) and rebuild all node cycles."""
        out, lo = [], 0
        for _, nn in self.groups:
            out += sorted(self.nodes5[lo:lo + nn], key=lambda n: (n.u, n.v))
            lo += nn
        self.nodes5 = out
        self.rebuild_cycles()

    def check(self) -> list[str]:
        """Violations of the rules above, as messages (empty list = the tile follows all of them)."""
        bad = []
        n_s = len(self.segs)
        if sum(g[0] for g in self.groups) != n_s or sum(g[1] for g in self.groups) != len(self.nodes5):
            bad.append("S3 groups do not cover S4 / S5")
        known = {id(n) for n in self.nodes5 + self.nodes6}
        sid = {id(s) for s in self.segs}
        for i, s in enumerate(self.segs):
            if id(s.a) not in known or id(s.b) not in known:
                bad.append(f"S4[{i}] ends on a node that is not in S5 / S6")
            elif not s.a.xy < s.b.xy:
                bad.append(f"S4[{i}] starts at {s.a.xy}, ends at {s.b.xy}: start must have the lower (x, y)")
            for x in (s.nxt_a, s.nxt_b) + tuple(t[1] for t in s.turns + s.tolls if isinstance(t[1], Seg)):
                if x is not None and id(x) not in sid:
                    bad.append(f"S4[{i}] points at a segment that is not in the tile")
            for tid, tgt, _ in s.turns:
                if isinstance(tgt, Seg) and id(tgt) in sid and \
                        not {id(s.a), id(s.b)} & {id(tgt.a), id(tgt.b)}:
                    bad.append(f"S10 entry of S4[{i}] targets S4[{self.segs.index(tgt)}], no shared node")
        lo = 0
        for g, (ns, nn) in enumerate(self.groups):
            nodes = self.nodes5[lo:lo + nn]
            if [n.xy for n in nodes] != sorted(n.xy for n in nodes):
                bad.append(f"S5 nodes of group {g} are not (x, y)-sorted")
            lo += nn
        for g in range(len(self.groups)):
            a, b = self.seg_slice(g)
            for i in range(a, b):
                if self.segs[i].raw[0x10] & 15 != g:
                    bad.append(f"S4[{i}] has class {self.segs[i].raw[0x10] & 15} but sits in level group {g}")
            a, b = self.node_slice(g)
            for nd in self.nodes5[a:b]:
                cls = [s.raw[0x10] & 15 for s in self.segs if s.a is nd or s.b is nd]
                if cls and min(cls) != g:
                    bad.append(f"S5 node {nd.xy} has lowest class {min(cls)} but sits in level group {g}")
        for nd in self.nodes5 + self.nodes6:
            m = self.members(nd)
            if not m:
                if nd.first is not None:
                    bad.append(f"node {nd.xy} has no segment but points at one")
                continue
            if nd.first is not m[0][3]:
                bad.append(f"node {nd.xy}: first segment is not the smallest bearing")
            for k, (_, _, side, s) in enumerate(m):
                want = m[(k + 1) % len(m)][3]
                if nd.sec == 6 and len(m) == 1:
                    want = None
                if (s.nxt_a if side == "a" else s.nxt_b) is not want:
                    bad.append(f"node {nd.xy}: next-segment link of S4[{self.segs.index(s)}] breaks the cycle")
        return bad

    # ------------------------------------------------------------------ geometry helpers
    def local(self, lon: float, lat: float) -> tuple[int, int]:
        """Tile-grid (u, v) of a WGS84 point."""
        from ..geometry import VERTEX_SHIFT
        from ..iso import to_carin
        x, y = to_carin(lon, lat)
        return (round((x - self.frame.x0) / (1 << VERTEX_SHIFT)), round((y - self.frame.y0) / (1 << VERTEX_SHIFT)))

    def lonlat(self, u: int, v: int) -> tuple[float, float]:
        return self.frame.to_wgs84(u, v)

    def polyline(self, seg: Seg) -> list[tuple[float, float]]:
        """lon/lat of a segment: start node, shape points, end node."""
        pts = [seg.a.xy] + [struct.unpack_from(">HH", e) for e in seg.shape] + [seg.b.xy]
        return [self.lonlat(u, v) for u, v in pts]

    def finalize(self, seg: Seg) -> None:
        """Set length (+0x0C, metres) and the two bearings (+0x0E / +0x0F, 1/256 turn) from the geometry."""
        from math import atan2, cos, hypot, pi, radians
        p = self.polyline(seg)

        def to_m(c):
            return (c[0] * cos(radians(p[0][1])) * 111_320.0, c[1] * 111_320.0)

        def bearing(a, b):
            e, n = (b[0] - a[0]) * cos(radians(a[1])), b[1] - a[1]
            return round(atan2(e, n) / (2 * pi) * 256) % 256

        m = [to_m(c) for c in p]
        seg.set16(0x0C, round(sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(m, m[1:]))))
        seg.raw[0x0E] = bearing(p[0], p[1])
        seg.raw[0x0F] = bearing(p[-1], p[-2])

    # ------------------------------------------------------------------ views
    def text(self, rel: int) -> Optional[str]:
        if rel is None:
            return None
        end = self.blob.find(b"\0", rel)
        return self.blob[rel:end if end >= 0 else None].decode("latin-1")

    def graph(self) -> dict:
        """Layout-independent description: equal for two tiles that differ only in section positions."""
        nodes = {}
        for sec, lst in ((5, self.nodes5), (6, self.nodes6)):
            for i, nd in enumerate(lst):
                nodes[id(nd)] = (sec, i)
        sidx = {id(s): i for i, s in enumerate(self.segs)}
        ref = lambda s: sidx[id(s)] if s is not None else None
        tref = lambda x: sidx[id(x)] if isinstance(x, Seg) else ("ext", x)

        def pas(s, f):
            out = []
            for v in f:
                if isinstance(v, tuple):
                    out.append(self.text(v[1]) if v[0] == "t" else v)
                else:
                    out.append(v)
            return tuple(out)

        return {
            "tile_id": self.tile_id,
            "header": self.prolog[68:],
            "segments": [{
                "raw": bytes(s.raw), "a": nodes[id(s.a)], "b": nodes[id(s.b)],
                "next_a": ref(s.nxt_a), "next_b": ref(s.nxt_b), "shape": list(s.shape),
                "turns": [(tid, tref(g), fl) for tid, g, fl in s.turns],
                "tolls": [(tid, tref(g), fl) for tid, g, fl in s.tolls],
                "tmc": list(s.tmc), "signs": [(self.text(a), self.text(b), fl) for a, b, fl in s.signs],
                "name": s.name} for s in self.segs],
            "nodes5": [(n.u, n.v, n.flags, ref(n.first)) for n in self.nodes5],
            "nodes6": [(n.u, n.v, n.flags, ref(n.first), n.ext) for n in self.nodes6],
            "groups": [tuple(g) for g in self.groups],
            "passive": {s: [pas(s, f) for f in recs] for s, recs in self.passive.items()},
            "raw": {s: list(v) for s, v in self.raw_sections.items()},
            "gaps": dict(self.gaps), "blob": self.blob, "extra_sectors": self.extra_sectors,
            "s4_sentinel": bytes(self.s4_sentinel[:0]),
        }


def _bad(off, i, sec):
    raise TileError(f"S4[{i}] -> S{sec}: own-tile entry {off} is not a segment")


def diff_graph(a: dict, b: dict) -> list[str]:
    """Names of the top-level parts (and segment indices) where two graphs differ."""
    out = []
    for k in a:
        if k == "segments":
            if len(a[k]) != len(b[k]):
                out.append(f"segments: {len(a[k])} vs {len(b[k])}")
            out += [f"segment {i}" for i, (x, y) in enumerate(zip(a[k], b[k])) if x != y]
        elif a[k] != b[k]:
            out.append(k)
    return out
