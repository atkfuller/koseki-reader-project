"""The date cases are all taken from the Takagi register, and every one of them
is checked against the *same* date printed in modern numerals elsewhere in the
same PDF -- so these are regression tests against real documents, not invented
strings."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.dates import DateParseError, find_era_dates, kanji_number, parse_date, parse_era_date


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


@pytest.mark.parametrize("src,want", [("廿", 20), ("廿九", 29), ("卅", 30), ("卅壱", 31)])
def test_contracted_tens(src, want):
    assert kanji_number(src) == want


def test_edo_eras():
    """Both forms appear on the oldest Takagi pages."""
    d = parse_era_date("慶応三年十月廿日")
    assert d.gregorian.year == 1867 and d.day == 20
    assert d.lunisolar  # month/day are old-calendar, only the year is Gregorian
    assert parse_era_date("天保九年壱月壱日").gregorian.year == 1838
    assert not parse_era_date("明治32年3月15日").lunisolar


def test_era_transition_is_validated():
    assert parse_era_date("昭和64年1月7日").gregorian == date(1989, 1, 7)
    assert parse_era_date("平成元年1月8日").gregorian == date(1989, 1, 8)
    with pytest.raises(DateParseError):
        parse_era_date("昭和64年2月1日")   # Showa had ended
    with pytest.raises(DateParseError):
        parse_era_date("令和元年3月1日")   # Reiwa had not begun


def test_seireki():
    assert parse_date("【配偶者の生年月日】西暦1940年1月1日") == date(1940, 1, 1)
    assert parse_date("令和5年10月17日").gregorian == date(2023, 10, 17)
