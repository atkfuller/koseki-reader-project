"""The date cases are all taken from the Takagi register, and every one of them
is checked against the *same* date printed in modern numerals elsewhere in the
same PDF -- so these are regression tests against real documents, not invented
strings."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.dates import DateParseError, find_era_dates, kanji_number, parse_era_date


@pytest.mark.parametrize("src,want", [
    ("〇", 0), ("五", 5), ("九", 9),
    ("十", 10), ("拾", 10),          # bare unit means one ten
    ("拾壱", 11), ("弐拾九", 29), ("参拾壱", 31), ("四拾五", 45),
    ("百", 100), ("弐百", 200),
    ("千弐百参拾参", 1233),           # 1233番地, page 12
    ("三百五十二", 352),              # 352番地 in ordinary kanji
])
def test_kanji_number(src, want):
    assert kanji_number(src) == want


@pytest.mark.parametrize("src,want", [
    # left: as written in the handwritten register
    # right: as printed in the computerised koseki for the same person
    ("昭和五年拾壱月弐拾九日", date(1930, 11, 29)),    # 幸道
    ("昭和八年八月拾五日", date(1933, 8, 15)),         # 恵美子
    ("昭和拾壱年参月九日", date(1936, 3, 9)),          # 美佐子
    ("昭和拾四年壱月四日", date(1939, 1, 4)),          # 道雄
    ("明治参拾六年七月参拾壱日", date(1903, 7, 31)),   # ムメノ
    ("明治32年3月15日", date(1899, 3, 15)),            # 清太
    ("令和六年壱月弐拾弐日", date(2024, 1, 22)),       # certification date
    ("平成13年2月3日", date(2001, 2, 3)),
    ("大正元年七月参拾日", date(1912, 7, 30)),         # 元年 = year 1
])
def test_parse_era_date(src, want):
    assert parse_era_date(src).gregorian == want


def test_era_boundaries():
    """Era year 1 maps to the year the era began, not the year after."""
    assert parse_era_date("明治元年壱月壱日").gregorian.year == 1868
    assert parse_era_date("大正元年八月壱日").gregorian.year == 1912
    assert parse_era_date("昭和元年拾弐月弐拾五日").gregorian.year == 1926
    assert parse_era_date("平成元年壱月八日").gregorian.year == 1989
    assert parse_era_date("令和元年五月壱日").gregorian.year == 2019


def test_rejects_non_dates():
    with pytest.raises(DateParseError):
        parse_era_date("高木清太")
    with pytest.raises(DateParseError):
        parse_era_date("昭和五年拾参月弐拾九日")  # month 13


def test_find_era_dates_skips_junk():
    """OCR output is noisy; a bad match must not sink the whole line."""
    text = "昭和五年拾壱月弐拾九日出生 昭和五年拾参月壱日 明治参拾六年七月参拾壱日"
    found = find_era_dates(text)
    assert [d.gregorian for d in found] == [date(1930, 11, 29), date(1903, 7, 31)]
