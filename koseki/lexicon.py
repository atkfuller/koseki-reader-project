"""Fixed vocabulary: OCR fix-ups, the emigration toponym gazetteer, and English
labels for the computerised koseki's 【field】 names.

None of this goes through machine translation, on purpose. Names, places and
legal terms are the parts MT damages most, and the parts a genealogist or a
lawyer most needs to be exact. What is not in these tables stays Japanese.
"""
from __future__ import annotations

import re
import unicodedata

from .dates import DateParseError, parse_date

# --- OCR corrections --------------------------------------------------------
# Only substitutions that cannot be a real reading. Each is applied to whole
# substrings, logged with the original, and never touches a personal name
# field (a registry spelling is the legal spelling, even when it looks odd).
OCR_FIXES = {
    # PP-OCR drops the dakuten on ブ in every ブラジル on pages 1-2. プラジル
    # is not a word.
    "プラジル": "ブラジル",
    # The register prints the station as ビリグヰ with the archaic kana ヰ;
    # PP-OCR has no ヰ in its vocabulary and reads the nearest shape, キ.
    "ビリグキ": "ビリグヰ",
}

# Labels whose value is a personal name. OCR_FIXES never applies to these.
NAME_LABELS = {"名", "父", "母", "配偶者氏名", "養父", "養母"}

# Old (kyujitai) or variant forms of name kanji, mapped to the everyday form.
# Registries legitimately print either, and OCR swaps them freely: page 2 of
# the Takagi register prints 恵美子 and PaddleOCR returned 惠美子 at 0.996
# confidence. Since the registry spelling is the legal spelling, a name that
# contains either side of a pair is flagged for review, never rewritten.
NAME_VARIANTS = {
    "惠": "恵", "髙": "高", "﨑": "崎", "邊": "辺", "邉": "辺", "澤": "沢",
    "濱": "浜", "齋": "斎", "齊": "斉", "廣": "広", "國": "国", "榮": "栄",
    "德": "徳", "藏": "蔵", "眞": "真", "龍": "竜", "櫻": "桜", "壽": "寿",
    "彌": "弥", "實": "実", "淺": "浅", "關": "関", "瀨": "瀬", "條": "条",
    "嶋": "島", "冨": "富", "學": "学", "將": "将", "靜": "静", "黑": "黒",
}


def fix_ocr(text: str, label: str | None = None) -> tuple[str, list[tuple[str, str]]]:
    """Apply OCR_FIXES to `text`. Returns (fixed, [(wrong, right), ...])."""
    if label in NAME_LABELS:
        return text, []
    applied = []
    for wrong, right in OCR_FIXES.items():
        if wrong in text:
            text = text.replace(wrong, right)
            applied.append((wrong, right))
    return text, applied


# --- Toponyms ---------------------------------------------------------------
# Katakana and kanji-abbreviation forms of Brazilian places, mapped to the
# Portuguese spelling. Round-tripping ビリグヰ through MT gives "Biligui";
# the settlement is Birigui. Longest keys are matched first.
TOPONYMS = {
    "ブラジル国": "Brazil",
    "ブラジル": "Brazil",
    "伯国": "Brazil",
    "伯剌西爾": "Brazil",
    "サンパウロ州": "São Paulo State",
    "聖州": "São Paulo State",
    "サンパウロ": "São Paulo",
    "ノロエステ線": "Noroeste Line",
    "ビリグヰ駅": "Birigui Station",
    "ビリグイ駅": "Birigui Station",
    "バルパライゾ駅": "Valparaíso Station",
    "ミランドポリス駅": "Mirandópolis Station",
    "アラサツバ": "Araçatuba",
    "ロンドリーナ市": "Londrina",
    "バウルー": "Bauru",
    # Japanese places. Readings checked against Japan Post's postcode data
    # (西隈上 = ニシクマノウエ) and the gazetteer of merged villages
    # (椿子村 = つばこむら, a former village of 浮羽郡).
    "福岡県": "Fukuoka Prefecture",
    "うきは市": "Ukiha City",
    "浮羽郡": "Ukiha District",
    "浮羽町": "Ukiha-machi",
    "西隈上": "Nishi-Kumanoue",
    "椿子村": "Tsubako Village",
}
_TOPO_KEYS = sorted(TOPONYMS, key=len, reverse=True)
# 大字 marks a pre-merger village section; romanised addresses drop it.
_ADDR_SKIP = ("大字",)
_LOT_RE = re.compile(r"(?P<a>\d+)番地(?P<b>\d+)?$")


def place_en(value: str) -> str | None:
    """English for a place, most specific first, or None if any part is unknown.

    All-or-nothing: a half-romanised address is worse than the Japanese, because
    it looks finished.
    """
    value = unicodedata.normalize("NFKC", value)
    parts, i = [], 0
    while i < len(value):
        if skip := next((k for k in _ADDR_SKIP if value.startswith(k, i)), None):
            i += len(skip)
            continue
        if parts and (m := _LOT_RE.match(value, i)):
            # 352番地2 -> "352-2 Nishi-Kumanoue": the lot number leads its block
            lot = m.group("a") + (f"-{m.group('b')}" if m.group("b") else "")
            parts[-1] = f"{lot} {parts[-1]}"
            break
        for k in _TOPO_KEYS:
            if value.startswith(k, i):
                parts.append(TOPONYMS[k])
                i += len(k)
                break
        else:
            return None
    return ", ".join(reversed(parts)) if parts else None


_CONSUL_RE = re.compile(r"^在(?P<place>.+?)(?P<general>総)?領事$")


def official_en(value: str) -> str | None:
    """在バウルー領事 -> Consul at Bauru; 在サンパウロ総領事 -> Consul General at São Paulo."""
    m = _CONSUL_RE.match(value)
    if not m:
        return None
    place = place_en(m.group("place"))
    if not place:
        return None
    return f"{'Consul General' if m.group('general') else 'Consul'} at {place}"


# --- Field labels -----------------------------------------------------------
LABELS_EN = {
    "本籍": "Registered domicile",
    "氏名": "Name",
    "名": "Given name",
    "生年月日": "Date of birth",
    "父": "Father",
    "母": "Mother",
    "続柄": "Relationship to parents",
    "出生日": "Date of birth",
    "出生地": "Place of birth",
    "届出日": "Date of notification",
    "届出人": "Notified by",
    "送付を受けた日": "Date record was received",
    "受理者": "Accepted by",
    "改製日": "Date of revision",
    "改製事由": "Reason for revision",
    "更正日": "Date of correction",
    "更正事項": "Item corrected",
    "更正事由": "Reason for correction",
    "従前の記録": "Previous record",
    "婚姻日": "Date of marriage",
    "配偶者氏名": "Spouse's name",
    "配偶者の国籍": "Spouse's nationality",
    "配偶者の生年月日": "Spouse's date of birth",
    "婚姻の方式": "Form of marriage",
    "証書提出日": "Date certificate submitted",
    "新本籍": "New registered domicile",
    "従前戸籍": "Previous registry",
    "特記事項": "Special notes",
    "死亡日": "Date of death",
    "死亡時分": "Time of death",
    "死亡地": "Place of death",
    "除籍日": "Date of removal",
}

EVENTS_EN = {
    "出生": "Birth",
    "婚姻": "Marriage",
    "死亡": "Death",
    "離婚": "Divorce",
    "養子縁組": "Adoption",
    "縁組": "Adoption",
    "認知": "Acknowledgement of paternity",
    "入籍": "Entry into registry",
    "除籍": "Removal from registry",
    "転籍": "Transfer of registered domicile",
    "分籍": "Separation from registry",
    "戸籍改製": "Registry revision",
    "改製": "Registry revision",
    "更正": "Correction",
    "消除": "Cancellation",
}

# The event a record is about, when the left-hand label was not read: the
# first field of every 身分事項 block names it.
EVENT_BY_FIRST_FIELD = {
    "出生日": "出生", "婚姻日": "婚姻", "死亡日": "死亡", "離婚日": "離婚",
    "縁組日": "養子縁組", "認知日": "認知", "入籍日": "入籍", "転籍日": "転籍",
    "改製日": "戸籍改製", "更正日": "更正", "消除日": "消除",
}

_ORD = {"長": "eldest", "二": "second", "弐": "second", "三": "third", "四": "fourth",
        "五": "fifth", "六": "sixth", "七": "seventh", "八": "eighth", "九": "ninth"}
_KIN = {"父": "Father", "母": "Mother", "妻": "Wife", "夫": "Husband", "本人": "Self",
        "孫": "Grandchild", "姪": "Niece", "甥": "Nephew", "養子": "Adopted son",
        "養女": "Adopted daughter"}


def kin_en(value: str) -> str | None:
    """長男 -> eldest son, 弐女 -> second daughter, 父 -> Father."""
    if value in _KIN:
        return _KIN[value]
    if len(value) == 2 and value[0] in _ORD and value[1] in "男女":
        return f"{_ORD[value[0]]} {'son' if value[1] == '男' else 'daughter'}"
    return None


_FORM_RE = re.compile(r"^(?P<country>.+?)の方式$")


# --- Dates ------------------------------------------------------------------
_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def date_en(iso: str) -> str:
    """2005-03-20 -> 20 March 2005."""
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {_MONTHS[m - 1]} {y}"


# --- Personal names ---------------------------------------------------------
# The registry records how a name is written, not how it is read (furigana
# only became part of the koseki in 2025, after this certificate was issued),
# so a kanji name has no romanisation the document can vouch for. These are
# readings the name is almost always given; a kanji name not listed here stays
# in kanji rather than get a guess. 高木 = Takagi is confirmed by the spouse's
# katakana タカギ on the same certificate.
SURNAMES = {"高木": "Takagi", "矢野": "Yano"}
GIVEN_NAMES = {"恵美子": "Emiko", "美佐子": "Misako", "道雄": "Michio"}

# Katakana to modified Hepburn. Hiragana is shifted to katakana first.
_KANA = dict(zip(
    "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヰヱヲン"
    "ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポヴ",
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no "
    "ha hi fu he ho ma mi mu me mo ya yu yo ra ri ru re ro wa i e o n "
    "ga gi gu ge go za ji zu ze zo da ji zu de do ba bi bu be bo pa pi pu pe po vu".split()))
_YOON = {"ャ": "a", "ュ": "u", "ョ": "o"}
_MACRON = dict(zip("aiueo", "āīūēō"))


def kana_romaji(text: str) -> str | None:
    """ムメノ -> Mumeno, マサヲ -> Masao. None if `text` is not all kana."""
    text = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)
    out, double = "", False
    for c in text:
        if c == "ッ":
            double = True
            continue
        if c in _YOON and out and out[-1] == "i":
            # キャ -> kya, シャ -> sha, チャ -> cha, ジャ -> ja
            out = out[:-1] + ("" if out[-2:-1] in "hj" else "y") + _YOON[c]
            continue
        if c == "ー" and out and out[-1] in _MACRON:
            out = out[:-1] + _MACRON[out[-1]]
            continue
        r = _KANA.get(c)
        if r is None:
            return None
        if double:
            out += "t" if r.startswith("ch") else r[0]
            double = False
        out += r
    return out.capitalize() if out else None


def _name_part(part: str, table: dict[str, str]) -> str | None:
    key = "".join(NAME_VARIANTS.get(c, c) for c in part)
    return table.get(key) or kana_romaji(part)


def name_en(value: str, given_only: bool = False) -> str | None:
    """高木恵美子 -> Emiko Takagi; タカギ，クミコ -> Kumiko Takagi.

    All-or-nothing, like place_en: a name with any part unread stays Japanese.
    """
    value = unicodedata.normalize("NFKC", value).replace(" ", "")
    if "," in value:          # foreign-style SURNAME,GIVEN in katakana
        sur, _, given = value.partition(",")
        parts = [_name_part(given, GIVEN_NAMES), _name_part(sur, SURNAMES)]
    elif given_only:
        parts = [_name_part(value, GIVEN_NAMES)]
    else:
        plain = "".join(NAME_VARIANTS.get(c, c) for c in value)   # 髙木 reads as 高木
        sur = next((k for k in sorted(SURNAMES, key=len, reverse=True)
                    if plain.startswith(k) and len(value) > len(k)), None)
        if sur is None:
            return None
        parts = [_name_part(value[len(sur):], GIVEN_NAMES), SURNAMES[sur]]
    return " ".join(parts) if all(parts) else None  # type: ignore[arg-type]


# --- Fixed legal wording ----------------------------------------------------
# Sentences the computerised koseki prints verbatim, or with only a date or a
# name slotted in. Anything else in a prose field stays Japanese.
PHRASES = {
    # The 1994 ordinance that allowed registers to be kept on computer; every
    # computerised koseki cites it as the reason for its revision.
    "平成6年法務省令第51号附則第2条第1項による改製":
        "Revised under Supplementary Provisions Article 2(1) of Ministry of Justice "
        "Ordinance No. 51 of 1994 (conversion to a computerised register)",
    "これは,戸籍に記録されている事項の全部を証明した書面である。":
        "This document certifies all matters recorded in the family register.",
}

_REDISTRICT_RE = re.compile(r"^(?P<date>.+?日)行政区画変更市となった上,土地の名称変更$")
_SUBMITTED_RE = re.compile(r"^(?P<kin>妻|夫)(?P<name>.+)証書提出$")
_MAYOR_RE = re.compile(r"^(?P<place>.+?[市町村])長$")


def phrase_en(value: str) -> str | None:
    value = unicodedata.normalize("NFKC", value).replace("，", ",")
    if value in PHRASES:
        return PHRASES[value]
    if m := _REDISTRICT_RE.match(value):
        try:
            when = date_en(parse_date(m.group("date")).gregorian.isoformat())  # type: ignore[union-attr]
        except (DateParseError, ValueError, AttributeError):
            return None
        return (f"Change of administrative boundaries on {when}: became a city, "
                f"and the place name was changed")
    if m := _SUBMITTED_RE.match(value):
        who = name_en(m.group("name"))
        kin = {"妻": "wife", "夫": "husband"}[m.group("kin")]
        return f"Certificate submitted by {kin} {who}" if who else None
    if m := _MAYOR_RE.match(value):
        place = place_en(m.group("place"))
        return f"Mayor of {place}" if place else None
    return None


def value_en(label: str, value: str) -> str | None:
    """English for a field value, where it comes from a table, not a translator."""
    if label in {"続柄", "届出人"}:
        return kin_en(value)
    if label == "受理者":
        return official_en(value)
    if label in {"出生地", "死亡地", "配偶者の国籍", "婚姻地", "本籍", "新本籍"}:
        return place_en(value)
    if label == "婚姻の方式":
        m = _FORM_RE.match(value)
        place = place_en(m.group("country")) if m else None
        return f"Under the law of {place}" if place else None
    if label in NAME_LABELS:
        return name_en(value, given_only=label == "名")
    if label == "更正事項":
        return LABELS_EN.get(value)
    if label in {"改製事由", "更正事由", "特記事項"}:
        return phrase_en(value)
    return None
