import struct
from types import SimpleNamespace

import pytest

from carin.parser.iso import CarinVolume, IsoFile
from carin.parser.cf1.probe import name_pointer_score, shape_pointer_score


def _image(*paths):
    return SimpleNamespace(files={p: IsoFile(p, 0, 4096) for p in paths})


def test_detects_dvd_split_layout():
    paths, unit = CarinVolume._detect_layout(_image("/DB/DB_0", "/DB/DB_1", "/X"))
    assert paths == ("/DB/DB_0", "/DB/DB_1") and unit == 512


def test_detects_cd_single_file_layout():
    paths, unit = CarinVolume._detect_layout(_image("/ABSTRACT", "/carindb"))
    assert paths == ("/carindb",) and unit == 2048


def test_no_database_raises():
    with pytest.raises(ValueError):
        CarinVolume._detect_layout(_image("/ABSTRACT"))


def _type00_block(pointers, s4=64, rec4=32, s7=256, n7=10):
    data = bytearray(512)
    struct.pack_into(">HH", data, 8 + 4 * 4, s4, len(pointers))
    struct.pack_into(">HH", data, 8 + 7 * 4, s7, n7)
    for i, p in enumerate(pointers):
        struct.pack_into(">H", data, s4 + rec4 * i + 4, p)
    return bytes(data)


TABLE = {0x05: 8, 0x08: 32, 0x0C: 6}


def test_shape_pointer_score_accepts_consistent_pointers():
    assert shape_pointer_score(_type00_block([256, 262, 274, 280]), TABLE) == 1.0


def test_shape_pointer_score_rejects_misaligned_pointers():
    assert shape_pointer_score(_type00_block([256, 259, 5000, 12]), TABLE) < 0.5


def _named_block(pointers, text=b"\0high street\0mill lane\0station road\0", s2=40, rec2=10, t=400):
    data = bytearray(512)
    struct.pack_into(">HH", data, 8 + 2 * 4, s2, len(pointers))
    data[t:t + len(text)] = text
    for i, p in enumerate(pointers):
        struct.pack_into(">H", data, s2 + rec2 * i, p and t + p)
    return bytes(data)


NAME_TABLE = {0x05: 8, 0x40: 10}


def test_name_pointer_score_accepts_real_strings():
    assert name_pointer_score(_named_block([1, 13, 0, 23]), NAME_TABLE) == 1.0


def test_name_pointer_score_rejects_pointers_into_the_middle_of_text():
    assert name_pointer_score(_named_block([3, 15, 26]), NAME_TABLE) == 0.0


def test_name_pointer_score_needs_three_named_records():
    assert name_pointer_score(_named_block([1, 0, 13]), NAME_TABLE) is None
