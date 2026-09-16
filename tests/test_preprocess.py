import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.ocr.tiled import _axis, _tiles, dedupe, is_degenerate, layout_for
from koseki.ocr.base import Line, reading_order_vertical
from koseki.preprocess import decolor, sauvola


def test_decolor_removes_cyan_watermark_keeps_ink():
    """The security-paper background is chromatic and the ink is not; max-channel
    separates them where a luminance conversion does not."""
    cyan = np.full((4, 4, 3), (255, 220, 120), np.uint8)   # BGR: light teal
    orange = np.full((4, 4, 3), (60, 160, 245), np.uint8)  # BGR: mascot orange
    ink = np.full((4, 4, 3), 30, np.uint8)
    assert decolor(cyan).min() == 255
    assert decolor(orange).min() >= 240
    assert decolor(ink).max() == 30


def test_sauvola_is_binary():
    img = np.random.randint(0, 255, (64, 64), dtype=np.uint8)
    out = sauvola(img, window=15)
    assert set(np.unique(out)).issubset({0, 255})


def test_axis_covers_full_extent():
    starts = _axis(3513, 1200, 0.3)
    assert starts[0] == 0
    assert starts[-1] + 1200 >= 3513   # nothing past the last tile is missed


def test_layout_keeps_whole_lines():
    """Vertical text -> full-height tiles, so a column is never cut in half."""
    assert layout_for(3513, 2263, 1200, "vertical") == (1200, 2263)
    assert layout_for(2480, 3400, 1200, "horizontal") == (2480, 1200)


def test_tiles_cover_page():
    tiles = _tiles(3513, 2263, 1200, 2263, 0.3)
    assert all(y == 0 and h == 2263 for _, y, _, h in tiles)
    assert max(x + w for x, _, w, _ in tiles) == 3513


def test_is_degenerate_catches_blank_tile_artefacts():
    assert is_degenerate(Line("0" * 200, (0, 0, 1190, 1190)), 1200)
    assert is_degenerate(Line("ーーーーーーーーーーーー", (5, 5, 100, 40)), 1200)
    assert not is_degenerate(Line("高木清太", (5, 5, 100, 40)), 1200)


def test_dedupe_prefers_the_unfragmented_line():
    """At a tile seam one tile sees the whole line and another sees a fragment;
    the whole line wins even when it is the less confident read."""
    whole = Line("【本籍】福岡県浮羽郡浮羽町大字西隈上352番地2", (100, 100, 900, 40), conf=0.6)
    frag = Line("籍】福岡県浮羽郡", (100, 100, 880, 40), conf=0.95)
    assert dedupe([frag, whole]) == [whole]


def test_reading_order_right_to_left():
    right = Line("first", (900, 10, 50, 400))
    middle = Line("second", (500, 10, 50, 400))
    left = Line("third", (100, 10, 50, 400))
    assert [l.text for l in reading_order_vertical([left, middle, right])] == [
        "first", "second", "third"
    ]


def test_reading_order_infers_vertical_from_box_shape():
    """Tall narrow boxes mean columns of Japanese; wide ones mean horizontal rows."""
    from koseki.ocr.base import reading_order

    columns = [Line("b", (100, 10, 50, 400)), Line("a", (900, 10, 50, 400))]
    assert [l.text for l in reading_order(columns)] == ["a", "b"]

    rows = [Line("b", (10, 900, 400, 50)), Line("a", (10, 100, 400, 50))]
    assert [l.text for l in reading_order(rows)] == ["a", "b"]


def test_reading_order_horizontal_keeps_label_and_value_together():
    """Label and value sit side by side and rarely share an exact y; without row
    grouping a naive (y, x) sort interleaves the two columns."""
    from koseki.ocr.base import reading_order_horizontal

    lines = [
        Line("value1", (800, 102, 400, 40)),
        Line("label1", (100, 100, 200, 40)),
        Line("value2", (800, 203, 400, 40)),
        Line("label2", (100, 200, 200, 40)),
    ]
    assert [l.text for l in reading_order_horizontal(lines)] == [
        "label1", "value1", "label2", "value2"
    ]
