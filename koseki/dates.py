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
    "明治": 1867,  # Meiji 1  = 1868
    "大正": 1911,  # Taisho 1 = 1912
    "昭和": 1925,  # Showa 1  = 1926
    "平成": 1988,  # Heisei 1 = 1989
    "令和": 2018,  # Reiwa 1  = 2019
}

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
_UNITS = {
    "十": 10, "拾": 10, "什": 10,
    "百": 100, "佰": 100, "陌": 100,
    "千": 1000, "仟": 1000, "阡": 1000,
}

_ERA_RE = re.compile(
    rf"(?P<era>{'|'.join(ERA_OFFSETS)})\s*(?P<y>[{''.join(_DIGITS)}{''.join(_UNITS)}{GANNEN}0-9]+)\s*年"
    rf"\s*(?P<m>[{''.join(_DIGITS)}{''.join(_UNITS)}0-9]+)\s*月"
    rf"\s*(?P<d>[{''.join(_DIGITS)}{''.join(_UNITS)}0-9]+)\s*日"
)


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
    return EraDate(era, year, month, day, gregorian, m.group(0))


def find_era_dates(text: str) -> list[EraDate]:
    """Every era date in `text`, skipping matches that do not resolve."""
    out = []
    for m in _ERA_RE.finditer(unicodedata.normalize("NFKC", text)):
        try:
            out.append(parse_era_date(m.group(0)))
        except (DateParseError, ValueError):
            continue
    return out
