"""Re-score saved benchmark output with reading order applied.

The benchmark stores every line's bounding box, so the effect of sorting can be
measured without paying for another OCR pass. This produces the column that
actually matters: CER once the lines are in document order rather than in
whatever order the detector emitted them.

    ./venv/bin/python scripts/rescore.py out/bench/results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.bench import load_truth, token_file  # noqa: E402
from koseki.ocr.base import Line, reading_order  # noqa: E402
from koseki.score import load_tokens, score, token_recall  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / "data/truth"


def main(path: Path) -> None:
    records = json.loads(path.read_text(encoding="utf-8"))
    hdr = (f"{'page':13}{'engine':22}{'variant':11}{'secs':>7}{'lines':>7}"
           f"{'CERraw':>8}{'CERsort':>9}{'bagCER':>8}{'recall':>8}")
    rows = [hdr, "-" * len(hdr)]
    for r in records:
        page = r["page"]
        truth = load_truth(TRUTH, page)
        tokens = load_tokens(token_file(TRUTH, page))
        lines = [Line(b["text"], tuple(b["box"]), b.get("conf")) for b in r["boxes"]]
        sorted_text = "\n".join(l.text for l in reading_order(lines))
        s_sorted = score(truth, sorted_text) if truth else None
        rec = token_recall(tokens, r["text"])[0] if tokens else None
        def fmt(v, w, nd=3):
            return f"{v:.{nd}f}".rjust(w) if v is not None else "-".rjust(w)

        rows.append(
            f"{page:13}{r['engine']:22}{r['variant']:11}{r['seconds']:7.1f}{r['lines']:7d}"
            + fmt(r["cer"], 8)
            + fmt(s_sorted.cer if s_sorted else None, 9)
            + fmt(r["bag_cer"], 8)
            + fmt(rec, 8)
            + (f"  {r['error']}" if r.get("error") else "")
        )
    out = "\n".join(rows)
    print(out)
    (path.parent / (path.stem + "_sorted.txt")).write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out/bench/results.json"))
