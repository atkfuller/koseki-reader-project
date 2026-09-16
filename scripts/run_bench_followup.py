"""Follow-up runs that the first baseline pointed at.

Two questions came out of the main table:

  1. yomitoku scored 100% key-token recall on page 1 and a CER of 0.93. A gap
     that wide is not a recognition problem, it is a reading-order problem --
     `right2left` is correct for the vertical registers and wrong for the
     horizontal computerised pages. So: re-run page 1 with the other modes.

  2. The "deskewed" variant is Sauvola binarisation *and* a rotation, which
     confounds the two. Page 12's measured skew was 0.00 degrees, so its
     deskewed run was really a binarisation-only run -- and every engine did
     worse on it. Re-run the `binary` variant explicitly to confirm that it is
     the binarisation, not the rotation, that costs accuracy.

    ./venv/bin/python scripts/run_bench_followup.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.bench import run, table  # noqa: E402
from koseki.ocr.paddle_engine import PaddleEngine  # noqa: E402
from koseki.ocr.tiled import TiledNdlEngine  # noqa: E402
from koseki.ocr.yomitoku_engine import YomitokuEngine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRUTH, CACHE = ROOT / "data/truth", ROOT / "out/variants"

if __name__ == "__main__":
    order_rows = run(
        [YomitokuEngine(reading_order=o) for o in ("auto", "left2right", "top2bottom")],
        [ROOT / "data/pages/p-01.png"],
        truth_dir=TRUTH, cache=CACHE,
        out_json=ROOT / "out/bench/followup_order.json",
        variants=("original",),
    )
    binary_rows = run(
        [PaddleEngine(), TiledNdlEngine(band=900), YomitokuEngine(reading_order="right2left")],
        [ROOT / "data/pages/p-01.png", ROOT / "data/pages/p-05-names.png"],
        truth_dir=TRUTH, cache=CACHE,
        out_json=ROOT / "out/bench/followup_binary.json",
        variants=("binary",),
    )
    out = "READING ORDER (page 1, original)\n" + table(order_rows) + \
          "\n\nBINARISATION ALONE\n" + table(binary_rows)
    print("\n" + out)
    (ROOT / "out/bench/followup.txt").write_text(out, encoding="utf-8")
