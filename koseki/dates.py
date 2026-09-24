"""Japanese era dates -> Gregorian, including the 大字 (daiji) forms.

Two numeral systems show up in these documents and only one of them is widely
supported by off-the-shelf tooling:

  ordinary kanji  一二三四五六七八九十   -- modern printed koseki
  daiji           壱弐参肆伍陸漆捌玖拾   -- the handwritten registers

Daiji are the legally mandated "anti-tampering" numerals: 一 can be turned into
二 or 三 with a brush stroke, 壱 cannot. Every handwritten date in the Takagi
register uses them, so a converter that only knows 一十百 reads none of them.
Worked example from page 5 of that file:

    昭和五年拾壱月弐拾九日  ->  1930-11-29

and page 1 of the same PDF prints that person's birth date as 昭和5年11月29日,
which is how the parser was checked.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

# Era 1 is the year the era began, so gregorian = offset + era_year.
ERA_OFFSETS = {
    # Late Edo: the oldest Takagi page has a 戸主 born 天保九年 (1838), and
    # 慶応三年 appears too. These are rare but not optional.
    "天保": 1829,  # Tenpo  1 = 1830
    "弘化": 1843,  # Koka   1 = 1844
    "嘉永": 1847,  # Kaei   1 = 1848
    "安政": 1853,  # Ansei  1 = 1854
    "万延": 1859,  # Man'en 1 = 1860
    "文久": 1860,  # Bunkyu 1 = 1861
    "元治": 1863,  # Genji  1 = 1864
    "慶応": 1864,  # Keio   1 = 1865
    "明治": 1867,  # Meiji 1  = 1868
    "大正": 1911,  # Taisho 1 = 1912
    "昭和": 1925,  # Showa 1  = 1926
    "平成": 1988,  # Heisei 1 = 1989
    "令和": 2018,  # Reiwa 1  = 2019
}

# Modern era changeovers fall mid-year, so 昭和64年 and 平成元年 are both 1989
# and only the month/day says which is right. The changeover day itself is
# accepted under both names: registers written on the day do use the old era.
ERA_STARTS = {
    "大正": date(1912, 7, 30),
    "昭和": date(1926, 12, 25),
    "平成": date(1989, 1, 8),
    "令和": date(2019, 5, 1),
}
_ERA_ORDER = list(ERA_OFFSETS)

# Japan switched to the Gregorian calendar on 明治6年1月1日. Before that, month
# and day are lunisolar: the year is right, 月/日 are not Gregorian.
GREGORIAN_ADOPTED = date(1873, 1, 1)

# First year of an era is written 元年 ("origin year"), never 一年.
GANNEN = "元"

_DIGITS = {
    "〇": 0, "零": 0,
    "一": 1, "壱": 1, "壹": 1,
    "二": 2, "弐": 2, "貳": 2, "弍": 2,
    "三": 3, "参": 3, "參": 3, "叁": 3,
    "四": 4, "肆": 4,
    "五": 5, "伍": 5,
    "六": 6, "陸": 6,
    "七": 7, "漆": 7, "柒": 7,
    "八": 8, "捌": 8,
    "九": 9, "玖": 9, "琁": 9,
}
# Contracted tens, written as one glyph: 廿日 = 20th, 廿九 = 29.
_TENS = {"廿": 20, "卅": 30, "丗": 30}
_UNITS = {
    "十": 10, "拾": 10, "什": 10,
    "百": 100, "佰": 100, "陌": 100,
    "千": 1000, "仟": 1000, "阡": 1000,
}

_NUM = f"{''.join(_DIGITS)}{''.join(_TENS)}{''.join(_UNITS)}0-9"
_ERA_RE = re.compile(
    rf"(?P<era>{'|'.join(ERA_OFFSETS)})\s*(?P<y>[{_NUM}{GANNEN}]+)\s*年"
    rf"\s*(?P<m>[{_NUM}]+)\s*月"
    rf"\s*(?P<d>[{_NUM}]+)\s*日"
)
_SEIREKI_RE = re.compile(r"西暦\s*(?P<y>[0-9]{4})\s*年\s*(?P<m>[0-9]{1,2})\s*月\s*(?P<d>[0-9]{1,2})\s*日")


class DateParseError(ValueError):
    pass


def kanji_number(s: str) -> int:
    """Parse a kanji numeral, ordinary or daiji, including 拾壱 and 弐拾九 forms.

    Handles the positional style (千九百 = 1900) as well as the bare-unit style
    where the leading 1 is implied (拾壱 = 11, not 10x11).
    """
    s = unicodedata.normalize("NFKC", s).strip()
    if not s:
        raise DateParseError("empty numeral")
    if s == GANNEN:
        return 1
    if s.isdigit():
        return int(s)

    total = 0        # completed higher-unit groups
    section = 0      # value accumulating against the current unit
    digit: int | None = None
    for ch in s:
        if ch in _DIGITS:
            digit = _DIGITS[ch]
        elif ch in _TENS:
            section += _TENS[ch]
        elif ch in _UNITS:
            unit = _UNITS[ch]
            # 拾 with nothing before it means one ten, not zero tens.
            section += (digit if digit is not None else 1) * unit
            digit = None
            if unit >= 100:
                total += section
                section = 0
        else:
            raise DateParseError(f"not a numeral character: {ch!r} in {s!r}")
    return total + section + (digit or 0)


@dataclass(frozen=True)
class EraDate:
    era: str
    year: int
    month: int
    day: int
    gregorian: date
    source: str

    @property
    def lunisolar(self) -> bool:
        """True when month/day are old-calendar and `gregorian` is only year-accurate."""
        return self.gregorian < GREGORIAN_ADOPTED

    def __str__(self) -> str:
        return f"{self.gregorian.isoformat()} ({self.era}{self.year}年{self.month}月{self.day}日)"


def parse_era_date(text: str) -> EraDate:
    """Parse the first era date in `text`. Raises DateParseError if there is none."""
    m = _ERA_RE.search(unicodedata.normalize("NFKC", text))
    if not m:
        raise DateParseError(f"no era date found in {text!r}")
    era = m.group("era")
    year, month, day = (kanji_number(m.group(g)) for g in ("y", "m", "d"))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise DateParseError(f"implausible date in {m.group(0)!r}")
    gregorian = date(ERA_OFFSETS[era] + year, month, day)
    _check_era_range(era, gregorian, m.group(0))
    return EraDate(era, year, month, day, gregorian, m.group(0))


def _check_era_range(era: str, d: date, src: str) -> None:
    """Reject 昭和64年2月 and the like: a date the era had already ended by."""
    start = ERA_STARTS.get(era)
    if start and d < start:
        raise DateParseError(f"{src!r} is before {era} began ({start})")
    nxt = _ERA_ORDER[_ERA_ORDER.index(era) + 1] if era != _ERA_ORDER[-1] else None
    end = ERA_STARTS.get(nxt) if nxt else None
    if end and d > end:
        raise DateParseError(f"{src!r} is after {era} ended ({end})")


def parse_date(text: str) -> EraDate | date:
    """An era date, or a 西暦 (Western-calendar) one -- the modern koseki prints
    foreign spouses' birth dates as 西暦1940年1月1日."""
    m = _SEIREKI_RE.search(unicodedata.normalize("NFKC", text))
    if m:
        return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
    return parse_era_date(text)


def find_era_dates(text: str) -> list[EraDate]:
    """Every era date in `text`, skipping matches that do not resolve."""
    out = []
    for m in _ERA_RE.finditer(unicodedata.normalize("NFKC", text)):
        try:
            out.append(parse_era_date(m.group(0)))
        except (DateParseError, ValueError):
            continue
    return out
