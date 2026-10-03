"""Minimal ISO 9660 reader + CARINdb virtual volume mapper.

Reads the navigation image directly (no mount required) and exposes the
CARINdb block address space that spans DB_0 + DB_1.

Reference: docs/CARINDB_BLUEPRINT.md sections 1 and 2.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Dict, Iterator, Optional

from . import cf1

ISO_SECTOR = 2048
CARIN_SECTOR = 512
CARIN_WINDOW = 0x400000  # CARINdb sectors covered by one DB_n file (2 GiB)

BLOCK_HDR = ">IHBB"
BLOCK_HDR_SIZE = 8
SECTION_DESC = ">HH"


@dataclass(frozen=True)
class IsoFile:
    path: str
    lba: int
    size: int

    @property
    def offset(self) -> int:
        return self.lba * ISO_SECTOR


class IsoImage:
    """Just enough ISO 9660 to locate file extents by path."""

    def __init__(self, path: str):
        self._f = open(path, "rb")
        self.files: Dict[str, IsoFile] = {}
        self._read_pvd()

    def _read_pvd(self) -> None:
        self._f.seek(16 * ISO_SECTOR)
        pvd = self._f.read(ISO_SECTOR)
        if pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise ValueError("not an ISO 9660 primary volume descriptor")
        self.volume_id = pvd[40:72].decode("latin-1").strip()
        self.publisher = pvd[318:446].decode("latin-1").strip()
        root = pvd[156:190]
        root_lba = struct.unpack_from("<I", root, 2)[0]
        root_size = struct.unpack_from("<I", root, 10)[0]
        self._walk(root_lba, root_size, "")

    def _walk(self, lba: int, size: int, prefix: str) -> None:
        self._f.seek(lba * ISO_SECTOR)
        data = self._f.read(size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # padding to the next logical sector
                pos = (pos // ISO_SECTOR + 1) * ISO_SECTOR
                if pos >= len(data):
                    break
                continue
            rec = data[pos:pos + rec_len]
            ext_lba = struct.unpack_from("<I", rec, 2)[0]
            ext_size = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            name_len = rec[32]
            name = rec[33:33 + name_len].decode("latin-1")
            pos += rec_len
            if name_len == 1 and name in ("\x00", "\x01"):
                continue  # '.' and '..'
            name = name.split(";")[0]
            full = f"{prefix}/{name}"
            if flags & 0x02:
                self._walk(ext_lba, ext_size, full)
            else:
                self.files[full] = IsoFile(full, ext_lba, ext_size)

    def read(self, iso_file: IsoFile, offset: int, length: int) -> bytes:
        if offset >= iso_file.size:
            return b""
        length = min(length, iso_file.size - offset)
        self._f.seek(iso_file.offset + offset)
        return self._f.read(length)

    def close(self) -> None:
        self._f.close()


class RawImage:
    """A bare `carindb` file (no ISO 9660 wrapper), e.g. one extracted from a CD.

    Offers the part of the IsoImage interface that CarinVolume uses: the file is exposed as
    `/carindb`, so `CarinVolume(RawImage(path))` works like it does for a disc image.
    """

    def __init__(self, path: str):
        self._f = open(path, "rb")
        self._f.seek(0, 2)
        self.files: Dict[str, IsoFile] = {"/" + CD_DB_NAME: IsoFile("/" + CD_DB_NAME, 0, self._f.tell())}
        self.volume_id = ""
        self.publisher = ""

    def read(self, iso_file: IsoFile, offset: int, length: int) -> bytes:
        if offset >= iso_file.size:
            return b""
        length = min(length, iso_file.size - offset)
        self._f.seek(iso_file.offset + offset)
        return self._f.read(length)

    def close(self) -> None:
        self._f.close()


def open_image(path: str):
    """Open an ISO 9660 image, or a bare `carindb` file when `path` is not an ISO."""
    try:
        return IsoImage(path)
    except ValueError:
        return RawImage(path)


@dataclass
class CarinBlock:
    sector: int          # absolute virtual CARINdb sector
    length: int          # on-disk length, in volume sectors (512 DVD, 2048 CD)
    type: int
    comp: int            # 0 = raw, 1 = structure-aware bit packing, 2 = zlib
    usize: int           # decompressed size, in volume sectors
    raw: bytes           # on-disk bytes, header included
    data: Optional[bytes]  # decoded bytes, header included (None if the type has no decoder yet)

    @property
    def payload(self) -> bytes:
        if self.data is None:
            raise ValueError(
                f"block {self.sector}: no CF={self.comp} decoder for BLOCK_TYPE "
                f"{self.type:#04x} yet (see blueprint section 9.11)"
            )
        return self.data

    def sections(self, n: int):
        return [
            struct.unpack_from(SECTION_DESC, self.payload, BLOCK_HDR_SIZE + 4 * i)
            for i in range(n)
        ]


DVD_DB_PATHS = ("/DB/DB_0", "/DB/DB_1")   # split volume, 512-byte sectors
CD_DB_NAME = "carindb"                    # single file on CD discs, 2048-byte sectors


class CarinVolume:
    """CARINdb block address space spanning DB_0 .. DB_n, or a single carindb.

    Two on-disc layouts exist. DVD-era images split the database into
    /DB/DB_0, /DB/DB_1 and count block addresses (BLOCK_ID >> 8, length,
    usize) in 512-byte sectors. CD-era images carry one /carindb file and
    count the same fields in 2048-byte sectors, but not always: a 2007 CD with
    DB-REL 34 counts them in 512-byte sectors. For a single /carindb the unit is
    therefore probed (see `probe_sector_size`) unless `sector_size` is given.
    When `db_paths` is not given the layout is detected from the image.

    `subrel` is the CF=1 sub-revision (see cf1.probe). The default keeps the
    historical value 9; call calibrate() to detect it from the data.
    """

    def __init__(self, image: IsoImage, db_paths=None, subrel: int = 9,
                 sector_size: Optional[int] = None):
        self.image = image
        if db_paths is None:
            db_paths, detected = self._detect_layout(image)
            if sector_size is None and detected == ISO_SECTOR:
                detected = self.probe_sector_size(image, image.files[db_paths[0]])
        else:
            detected = CARIN_SECTOR
        self.sector_size = sector_size or detected
        self.subrel = subrel
        self.parts = [image.files[p] for p in db_paths]
        self.sectors = [f.size // self.sector_size for f in self.parts]
        self._layout: Optional[dict] = None
        self._db_rel = 0

    @staticmethod
    def _detect_layout(image: IsoImage):
        if all(p in image.files for p in DVD_DB_PATHS):
            return DVD_DB_PATHS, CARIN_SECTOR
        for path in image.files:
            if path.lower() == "/" + CD_DB_NAME:
                return (path,), ISO_SECTOR
        raise ValueError("no CARINdb found (expected /DB/DB_0 + /DB/DB_1 or /carindb)")

    @staticmethod
    def count_blocks(image, iso_file: IsoFile, unit: int, window: int = 4 << 20) -> int:
        """Number of block headers found in the first `window` bytes when sectors are `unit` bytes.

        A header is valid when the upper 24 bits of its BLOCK_ID equal its own sector number and
        the length (low 8 bits) is not zero; the scan then jumps over the block, like `walk`.
        With the wrong unit the sector numbers never match and only chance hits remain.
        """
        buf = image.read(iso_file, 0, window)
        sector = count = 0
        while (sector + 1) * unit <= len(buf):
            bid = struct.unpack_from(">I", buf, sector * unit)[0]
            length = bid & 0xFF
            if (bid >> 8) == sector and length:
                count += 1
                sector += length
            else:
                sector += 1
        return count

    @classmethod
    def probe_sector_size(cls, image, iso_file: IsoFile) -> int:
        """Pick the sector unit (2048 or 512) whose block chain holds together at the file start.

        Defaults to 2048 (the usual CD unit) unless 512 finds clearly more block headers.
        """
        n2048 = cls.count_blocks(image, iso_file, ISO_SECTOR)
        n512 = cls.count_blocks(image, iso_file, CARIN_SECTOR)
        return CARIN_SECTOR if n512 >= 8 and n512 > 2 * n2048 else ISO_SECTOR

    @property
    def layout(self) -> dict:
        """RECORD_SIZE_TABLE del superblock — parametrizza il codec CF=1 (§9.11)."""
        if self._layout is None:
            sb = self.read_sectors(0, 2)
            off, count = struct.unpack_from(">HH", sb, 0x28)
            self._layout = dict(
                struct.unpack_from(">HH", sb, off + 4 * i) for i in range(count)
            )
            self._db_rel = struct.unpack_from(">H", sb, 0x1A)[0]
        return self._layout

    @property
    def db_rel(self) -> int:
        self.layout  # popola anche _db_rel
        return self._db_rel

    def read_sectors(self, sector: int, count: int) -> bytes:
        idx, local = divmod(sector, CARIN_WINDOW)
        if idx >= len(self.parts):
            raise ValueError(f"sector {sector} outside volume")
        return self.image.read(self.parts[idx], local * self.sector_size,
                               count * self.sector_size)

    def block(self, sector: int) -> CarinBlock:
        head = self.read_sectors(sector, 1)
        bid, btype, cf, us = struct.unpack_from(BLOCK_HDR, head)
        if (bid >> 8) != sector:
            raise ValueError(f"sector {sector}: BLOCK_ID says {bid >> 8}")
        length = bid & 0xFF
        raw = head if length == 1 else self.read_sectors(sector, length)
        if cf == 0:
            data = raw
        elif cf == 2:
            data = raw[:BLOCK_HDR_SIZE] + zlib.decompress(raw[BLOCK_HDR_SIZE:])
        elif cf & 1:
            try:
                data = cf1.decode_block(raw, self.layout, self.db_rel,
                                        subrel=self.subrel,
                                        sector_size=self.sector_size)
            except cf1.Cf1Error:
                data = None          # tipo di blocco non ancora portato
        else:
            data = None
        return CarinBlock(sector, length, btype, cf, us, raw, data)

    def walk(self, part: Optional[int] = None) -> Iterator[CarinBlock]:
        """Follow the block chain. Yields header-only blocks (raw not sliced)."""
        parts = range(len(self.parts)) if part is None else [part]
        for idx in parts:
            base = idx * CARIN_WINDOW
            nsec = self.sectors[idx]
            sector = 0
            buf, buf_base = b"", -1
            CHUNK = 1 << 22
            while sector < nsec:
                off = sector * self.sector_size
                if buf_base < 0 or off < buf_base or off + BLOCK_HDR_SIZE > buf_base + len(buf):
                    buf = self.image.read(self.parts[idx], off, CHUNK)
                    buf_base = off
                    if len(buf) < BLOCK_HDR_SIZE:
                        break
                bid, btype, cf, us = struct.unpack_from(BLOCK_HDR, buf, off - buf_base)
                length = bid & 0xFF
                if (bid >> 8) != base + sector or length == 0:
                    sector += 1
                    continue
                yield CarinBlock(base + sector, length, btype, cf, us, b"", None)
                sector += length

    def calibrate(self, sample: int = 48) -> int:
        """Detect the CF=1 sub-revision from the data and store it in `subrel`.

        Decodes up to `sample` CF=1 type 0x00 blocks spread across the volume
        under each candidate sub-revision and keeps the one whose blocks pass
        the section-4 -> section-7 structural check (see cf1.probe).
        """
        from .cf1.probe import detect_subrel

        heads = [b for b in self.walk() if b.type == 0x00 and b.comp & 1]
        if not heads:
            return self.subrel
        step = max(1, len(heads) // sample)
        raws = [self.read_sectors(b.sector, b.length) for b in heads[::step][:sample]]
        self.subrel = detect_subrel(raws, self.layout, self.db_rel,
                                    self.sector_size, cf1.decode_block)
        return self.subrel


# --------------------------------------------------------------------------
# Geographic frame (docs/CARINDB_BLUEPRINT.md section 7)
# A full 360 deg turn is 2_000_000_000 CARIN units; the origin sits on the
# equator at 30 deg West.  Calibrated against 38 city labels, rms 2.0 km.
# --------------------------------------------------------------------------

CARIN_UNITS_PER_TURN = 2_000_000_000
K = CARIN_UNITS_PER_TURN / 360.0          # 5_555_555.5555... units per degree
LON_ORIGIN = -30.0
LAT_ORIGIN = 0.0

# plausible coverage window, used to recognise a bbox inside service data
_X_RANGE = (-60_000_000, 1_000_000_000)
_Y_RANGE = (0, 450_000_000)
QUADTREE_UNIT = 98_304          # find_bbox only; not the smallest tile side (24,576 on the DVDs)


def to_wgs84(x: int, y: int):
    return (x / K + LON_ORIGIN, y / K + LAT_ORIGIN)


def to_carin(lon: float, lat: float):
    return (round((lon - LON_ORIGIN) * K), round((lat - LAT_ORIGIN) * K))


def find_bbox(payload: bytes):
    """Locate the 4 x int32 bounding box that follows the section descriptor.

    Superseded: the bbox sits at a fixed offset per block type (02-geo.md §7.4), and
    tile sides are the 0x07 root side / 2^k, not multiples of 98304. On DVD 21708,
    2,837 of 128,690 tiles have a side that is not a multiple of 98304, so their
    bbox breaks the rule below (21734: 3,887 of 147,272;
    scripts/geo/check_spatial_index.py).
    For a lookup by position use carin.parser.spatial.

    The descriptor entry count varies per block, so the bbox is found by
    scanning 4-aligned positions up to the first section offset.  A genuine box
    sits on the CARIN quadtree: both sides are multiples of 98304 units and the
    aspect ratio is 1:1, 1:2 or 2:1.
    Returns (offset, (x0, y0, x1, y1)) or None.
    """
    if len(payload) < 0x30:
        return None
    first = struct.unpack_from(">H", payload, BLOCK_HDR_SIZE)[0]
    limit = min(first if first > 16 else len(payload), len(payload) - 16, 512)
    for off in range(12, limit, 4):
        x0, y0, x1, y1 = struct.unpack_from(">4i", payload, off)
        if not (x0 < x1 and y0 < y1):
            continue
        if not (_X_RANGE[0] <= x0 and x1 <= _X_RANGE[1]):
            continue
        if not (_Y_RANGE[0] <= y0 and y1 <= _Y_RANGE[1]):
            continue
        w, h = x1 - x0, y1 - y0
        if w % QUADTREE_UNIT or h % QUADTREE_UNIT:
            continue
        if w not in (h, 2 * h) and h != 2 * w:
            continue
        if w > 200_000_000:
            continue
        return off, (x0, y0, x1, y1)
    return None
