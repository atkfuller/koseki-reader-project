"""Lexicon tests: OCR fix-ups, the toponym gazetteer, kin terms."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.lexicon import fix_ocr, kin_en, official_en, place_en


def test_ocr_fixes_never_touch_names():
    assert fix_ocr("プラジル国", "出生地")[0] == "ブラジル国"
    assert fix_ocr("プラジル", "名") == ("プラジル", [])


def test_lexicon():
    assert place_en("ブラジル国サンパウロ州ノロエステ線ミランドポリス駅") == \
        "Mirandópolis Station, Noroeste Line, São Paulo State, Brazil"
    assert place_en("福岡県浮羽郡椿子村") is None     # all-or-nothing
    assert official_en("在バウルー領事") == "Consul at Bauru"
    assert kin_en("弐男") == "second son" and kin_en("長女") == "eldest daughter"
