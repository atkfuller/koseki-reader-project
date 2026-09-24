"""Tier 1 parser tests.

The layout (box positions, the split 【名】/name boxes, the letter-spaced 除 籍,
a record running over a page break) is copied from what PaddleOCR returned on
the Takagi register. The names and places are invented, so this file carries
no personal data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.lexicon import fix_ocr, kin_en, official_en, place_en
from koseki.ocr.base import Line
from koseki.tier1 import looks_like_tier1, merge_label_values, parse

ISSUE = "00001111-20240101-00000001-東京都テスト市"


def L(text, x, y, w=300, h=50, conf=0.99):
    return Line(text, (x, y, w, h), conf)


PAGE1 = [
    L("-4", 26, 60, conf=0.55),                       # mascot corner, junk
    L("(2の1)", 1599, 248), L("全部事項証明", 1815, 222),
    L("本", 363, 336, 50), L("籍", 584, 334, 60),     # letter-spaced label
    L("東京都テスト市中央一丁目1番地", 845, 334, 900),
    L("氏名", 354, 417), L("山田一郎", 838, 425),
    L("戸籍事項", 227, 575), L("戸籍改製", 318, 624),
    L("【改製日】平成13年2月3日", 818, 626, 600),
    L("更正", 316, 718),
    L("【更正日】平成17年3月20日", 820, 728, 640),
    L("【更正事由】平成17年3月20日行政区画変更市となった上，土地の名称", 811, 794, 1500),
    L("変更", 880, 867, 100),
    L("【従前の記録】", 817, 915),
    L("【本籍】東京都旧郡中央村1番地", 907, 960, 1000),
    L("戸籍に記録されている者", 228, 1059, 500),
    L("【名】", 815, 1102, 106, 60), L("一郎", 921, 1065, 211, 100),
    L("【生年月日】明治32年3月15日", 819, 1206, 690),
    L("除", 274, 1300, 57, 56), L("籍", 499, 1301, 57, 56),
    L("【父】山田太助", 819, 1257), L("【続柄】長男", 820, 1352, 250),
    L("戸籍に記録されている者", 239, 2126, 500),
    # the name box sits higher than its label, so a row sort puts it first
    L("花子", 945, 2126, 187, 93), L("【名】", 820, 2163, 97, 58),
    L("【生年月日】昭和5年11月29日", 825, 2260, 680),
    L("身分事項", 240, 2501, 190), L("出生", 329, 2549, 190),
    L("【出生日】昭和5年11月29日", 825, 2541, 636),
    L("【出生地】プラジル国サンパウロ州ノロエステ線ビリグキ駅", 826, 2588, 1200),
    L("発行番号", 263, 2818, 187), L(ISSUE, 487, 2808, 911),
    L("以下次頁", 2157, 2811, 187),
    L("うきは市キャラクター“うきびー”", 2112, 3029),
]

PAGE2 = [
    L("(2の2)", 1373, 256), L("全部事項証明", 1584, 236),
    L("【届出人】父", 606, 326, 250),                  # continues 花子's birth
    L("身分事項", 54, 430, 177), L("生", 236, 482, 73),   # 出 of 出生 not detected
    L("【婚姻日】昭和33年9月20日", 609, 482, 600),
    L("【受理者】在サンパウロ総領事", 610, 585, 600),
    L("以下余白", 1946, 836, 189),
    L("発行番号" + ISSUE, 102, 2897, 1100),
    L("令和6年1月22日", 222, 3107, 390),
]


def test_classifies_tier1():
    assert looks_like_tier1(PAGE1)
    assert not looks_like_tier1([L("明治参拾弐年", 0, 0), L("全部事項証明", 0, 0)])


def test_merges_name_with_its_label():
    merged = merge_label_values([L("【名】", 815, 1102, 106, 60), L("一郎", 921, 1065, 211, 100)])
    assert [l.text for l in merged] == ["【名】一郎"]


def test_parse_certificate():
    (cert,) = parse({1: PAGE1, 2: PAGE2})
    assert cert.issue_no == "00001111-20240101-00000001"
    assert cert.pages == [1, 2]
    assert cert.honseki == "東京都テスト市中央一丁目1番地"
    assert cert.head_name == "山田一郎"
    assert cert.certified_on == "2024-01-22"
    assert "-4" in cert.dropped

    revision, correction = cert.registry_events
    assert revision.type == "戸籍改製" and revision.fields[0].date == "2001-02-03"
    reason = next(f for f in correction.fields if f.label == "更正事由")
    assert reason.value.endswith("土地の名称変更")    # wrapped line rejoined
    assert reason.date is None                       # a date in prose is not the field's date
    previous = next(f for f in correction.fields if f.label == "従前の記録")
    assert [(c.label, c.value) for c in previous.children] == [("本籍", "東京都旧郡中央村1番地")]

    ichiro, hanako = cert.persons
    assert (ichiro.surname, ichiro.given_name, ichiro.removed) == ("山田", "一郎", True)
    assert ichiro.get("続柄") == "長男"
    assert (hanako.given_name, hanako.removed) == ("花子", False)

    birth, marriage = hanako.events
    assert birth.type == "出生" and birth.type_source == "label"
    place = next(f for f in birth.fields if f.label == "出生地")
    assert place.value == "ブラジル国サンパウロ州ノロエステ線ビリグヰ駅"
    assert place.corrected_from is not None
    assert place.value_en == "Birigui Station, Noroeste Line, São Paulo State, Brazil"
    assert [f.label for f in birth.fields][-1] == "届出人"   # carried over the page break
    assert marriage.type == "婚姻" and marriage.type_source == "inferred"


def test_ocr_fixes_never_touch_names():
    assert fix_ocr("プラジル国", "出生地")[0] == "ブラジル国"
    assert fix_ocr("プラジル", "名") == ("プラジル", [])


def test_lexicon():
    assert place_en("ブラジル国サンパウロ州ノロエステ線ミランドポリス駅") == \
        "Mirandópolis Station, Noroeste Line, São Paulo State, Brazil"
    assert place_en("福岡県浮羽郡椿子村") is None     # all-or-nothing
    assert official_en("在バウルー領事") == "Consul at Bauru"
    assert kin_en("弐男") == "second son" and kin_en("長女") == "eldest daughter"
