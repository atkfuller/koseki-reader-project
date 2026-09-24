"""Fixed vocabulary: OCR fix-ups, the emigration toponym gazetteer, and English
labels for the computerised koseki's 【field】 names.

None of this goes through machine translation, on purpose. Names, places and
legal terms are the parts MT damages most, and the parts a genealogist or a
lawyer most needs to be exact. What is not in these tables stays Japanese.
"""
from __future__ import annotations

import re

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
}
_TOPO_KEYS = sorted(TOPONYMS, key=len, reverse=True)


def place_en(value: str) -> str | None:
    """English for a place, most specific first, or None if any part is unknown.

    All-or-nothing: a half-romanised address is worse than the Japanese, because
    it looks finished.
    """
    parts, i = [], 0
    while i < len(value):
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


def value_en(label: str, value: str) -> str | None:
    """English for a field value, where it comes from a table, not a translator."""
    if label in {"続柄", "届出人"}:
        return kin_en(value)
    if label == "受理者":
        return official_en(value)
    if label in {"出生地", "死亡地", "配偶者の国籍", "婚姻地"}:
        return place_en(value)
    if label == "婚姻の方式":
        m = _FORM_RE.match(value)
        place = place_en(m.group("country")) if m else None
        return f"Under the law of {place}" if place else None
    return None
