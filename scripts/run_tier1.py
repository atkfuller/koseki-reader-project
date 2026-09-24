"""Tier 1 benchmark: the computerised 全部事項証明 pages (p-01..p-03).

The baseline in docs/ocr-baseline.md picked PaddleOCR for Tier 1 on the
strength of page 1 alone, and ran yomitoku only in `right2left` -- the
*vertical* reading-order mode -- on a page that is horizontal print. This
re-runs the tier properly: all three Tier 1 pages, and yomitoku in the modes
that actually apply to horizontal text.

    ./venv/bin/python scripts/run_tier1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.bench import run, table  # noqa: E402
from koseki.ocr.paddle_engine import PaddleEngine  # noqa: E402
from koseki.ocr.yomitoku_engine import YomitokuEngine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

ENGINES = [
    PaddleEngine(),
    YomitokuEngine(reading_order="auto"),
    YomitokuEngine(reading_order="top2bottom"),
    YomitokuEngine(reading_order="right2left"),  # baseline's setting, kept for comparison
]

PAGES = [ROOT / f"data/pages/p-0{n}.png" for n in (1, 2, 3)]

# Tier 1 is printed, not brush: the baseline found decolouring mildly *hurts*
# print. Both are run so that holds up across all three pages, not just page 1.
VARIANTS = ("original", "decolored")

if __name__ == "__main__":
    rows = run(
        ENGINES, PAGES,
        truth_dir=ROOT / "data/truth",
        cache=ROOT / "out/variants",
        out_json=ROOT / "out/tier1/results.json",
        variants=VARIANTS,
    )
    print()
    print(table(rows))
    (ROOT / "out/tier1/table.txt").write_text(table(rows), encoding="utf-8")
