"""Baseline OCR benchmark over the Takagi koseki.

Nothing downstream should be built before this table exists: the whole point is
to find out which engine, at which preprocessing stage, is worth wiring into a
pipeline -- and, just as importantly, how far short of usable the best one is on
the handwritten pages.

    ./venv/bin/python scripts/run_bench.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.bench import run, table  # noqa: E402
from koseki.ocr.ndl_engine import NdlEngine  # noqa: E402
from koseki.ocr.paddle_engine import PaddleEngine  # noqa: E402
from koseki.ocr.tiled import TiledNdlEngine  # noqa: E402
from koseki.ocr.vlm_engine import VlmEngine  # noqa: E402
from koseki.ocr.yomitoku_engine import YomitokuEngine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

ENGINES = [
    PaddleEngine(),
    NdlEngine(),                      # whole-page, to show what tiling buys
    TiledNdlEngine(band=900),
    TiledNdlEngine(band=1200),
    YomitokuEngine(reading_order="right2left"),
]

# Costs money and needs ANTHROPIC_API_KEY, so it is opt-in:
#     ./venv/bin/python scripts/run_bench.py --vlm
if "--vlm" in sys.argv:
    ENGINES.append(VlmEngine())

# One page per difficulty tier, plus the cropped panel that carries the names.
PAGES = [
    ROOT / "data/pages/p-01.png",        # modern computerised print
    ROOT / "data/pages/p-05.png",        # Showa brush transcript
    ROOT / "data/pages/p-05-names.png",  # its name panel, full ground truth
    ROOT / "data/pages/p-12.png",        # Meiji/Taisho brush, stamps, dense
]

if __name__ == "__main__":
    rows = run(
        ENGINES, PAGES,
        truth_dir=ROOT / "data/truth",
        cache=ROOT / "out/variants",
        out_json=ROOT / "out/bench/results.json",
    )
    print()
    print(table(rows))
    (ROOT / "out/bench/table.txt").write_text(table(rows), encoding="utf-8")
