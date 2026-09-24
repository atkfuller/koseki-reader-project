"""PaddleOCR (PP-OCRv5) adapter.

Paddle is here mainly for its detector: it is the only engine in the set that
hands back a clean quadrilateral per region, which the review UI needs. Its
Japanese recogniser is trained on modern print, so expect it to do well on the
computerised pages and poorly on the brush-written ones. That contrast is the
point of the benchmark.
"""
from __future__ import annotations

import time

from .base import Line, Result

_ocr = None


def _engine():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR

        _ocr = PaddleOCR(
            lang="japan",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,  # needed: vertical lines come in rotated
            device="cpu",
        )
    return _ocr


class PaddleEngine:
    """`box_thresh` is the detector's minimum mean score for a text box.

    Paddle's default of 0.6 silently drops whole lines on page 3 of the Takagi
    register -- a slightly tilted camera photo, where a long line's score map
    bleeds into its neighbours. 0.5 recovers the line and adds no noise on the
    other Tier 1 pages. None keeps Paddle's default (what the baseline ran).
    """

    def __init__(self, box_thresh: float | None = None):
        self.box_thresh = box_thresh

    @property
    def name(self) -> str:
        return "paddleocr" if self.box_thresh is None else f"paddleocr/box{self.box_thresh}"

    def run(self, image_path: str) -> Result:
        t = time.time()
        kw = {} if self.box_thresh is None else {"text_det_box_thresh": self.box_thresh}
        try:
            raw = _engine().predict(image_path, **kw)
        except Exception as e:  # noqa: BLE001 - a failed engine is a benchmark result
            return Result(self.name, [], time.time() - t, error=f"{type(e).__name__}: {e}")

        lines: list[Line] = []
        for page in raw:
            d = page.json.get("res", page.json) if hasattr(page, "json") else page
            texts = d.get("rec_texts", [])
            scores = d.get("rec_scores", [])
            polys = d.get("rec_polys", d.get("dt_polys", []))
            for i, txt in enumerate(texts):
                poly = polys[i] if i < len(polys) else None
                if poly is not None:
                    xs = [float(p[0]) for p in poly]
                    ys = [float(p[1]) for p in poly]
                    box = (int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))
                else:
                    box = (0, 0, 0, 0)
                lines.append(
                    Line(text=txt, box=box, conf=float(scores[i]) if i < len(scores) else None)
                )
        return Result(self.name, lines, time.time() - t)
