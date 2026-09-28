"""pdf_to_text layout tests. Box positions are copied from PaddleOCR on the
Takagi register; the text is invented, so this file carries no personal data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from koseki.ocr.base import Line
from pdf_to_text import page_text


def L(text, x, y, w=300, h=50, conf=0.99):
    return Line(text, (x, y, w, h), conf)


def test_rows_and_letter_spaced_labels():
    lines = [
        L("本", 363, 336, 50, 50),
        L("籍", 584, 334, 61, 118),       # drawn twice its height: centre on the next row
        L("東京都テスト市1番地", 845, 334, 953, 51),
        L("氏名", 354, 417, 295, 78), L("山田一郎", 838, 425, 268, 62),
        L("【更正事項】本籍", 811, 745, 400),
        L("【更正事由】土地の名称変更", 811, 794, 1500),
        L("C55", 26, 900, conf=0.4),       # margin art
    ]
    assert page_text(lines).splitlines() == [
        "本籍  東京都テスト市1番地",
        "氏名  山田一郎",
        "【更正事項】本籍",
        "【更正事由】土地の名称変更",
    ]


def test_name_joins_its_label_and_known_slips_are_fixed():
    lines = [L("花子", 945, 2126, 187, 93), L("【名】", 820, 2163, 97, 58),
             L("【出生地】プラジル国", 826, 2260, 600)]
    assert page_text(lines).splitlines() == ["【名】花子", "【出生地】ブラジル国"]
