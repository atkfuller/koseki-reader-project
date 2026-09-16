import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.score import normalize, score, token_recall


def test_nfkc_fold_full_width():
    """Koseki print uses full-width digits; engines are inconsistent. A correct
    read must not be punished for width."""
    assert score("３５２番地", "352番地").cer == 0.0


def test_cer_punishes_order_and_bag_cer_does_not():
    """The whole point of reporting both: this gap means 'sort the lines', not
    'get a better model'."""
    s = score("ABCDEF", "DEFABC")
    assert s.cer == 1.0
    assert s.bag_cer == 0.0


def test_token_recall():
    r, missed = token_recall(["高木清太", "ムメノ", "幸道"], "父高木清太 母ムメノ")
    assert r == pytest.approx(2 / 3)
    assert missed == ["幸道"]


def test_normalize_strips_whitespace():
    assert normalize("高木 清太\n") == "高木清太"
