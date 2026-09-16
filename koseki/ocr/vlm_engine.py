"""Vision-model OCR, as a fourth engine in the benchmark.

Why this is in here at all: the architecture in the handoff predates treating a
general vision model as an OCR engine, and on this corpus that assumption is
worth re-testing rather than inheriting. While preparing the ground truth for
this benchmark, Claude read names, birth orders and daiji dates off a 1400px
JPEG of pages 5 and 12 correctly enough that the readings cross-validated
against the modern printed koseki on pages 1-3. That is a stronger result than
any of the three traditional engines managed on the same pages.

Two caveats that decide how it may be used, not whether:

  * It returns no bounding boxes. The review UI needs boxes to highlight a
    region on the scan, so a VLM cannot replace the detector -- pair it with
    ndlocr-lite's boxes, or ask for a per-region crop at a time.
  * It can produce fluent, plausible, wrong names. That is the "OCR
    hallucinating names" risk in the handoff, and it is worse for a VLM than
    for a CTC recogniser, because a VLM's errors are grammatical. Never accept
    a name from this engine without human review.

UNMEASURED: no ANTHROPIC_API_KEY was set when the baseline was run, so this
engine has no row in the results table. Set the key and re-run to fill it in.
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from .base import Line, Result

PROMPT = """This is a scan of a Japanese koseki (戸籍), a family register.

Transcribe every character you can read, exactly as written. Rules:
- Preserve the original orthography: kyujitai (舊字體), daiji numerals
  (壱弐参拾), and historical kana. Do not modernise or simplify anything.
- Vertical text reads top-to-bottom, columns right-to-left. Output in that
  reading order, one line of output per column or per field.
- Ignore the decorative security-paper background and the city mascot.
- Where a character is obscured by a seal, damage or a 除籍 stamp and you
  cannot read it, write ▲ for that character. Never guess a character, and
  never guess a personal name -- a wrong name here is worse than a gap.
- Output only the transcription. No commentary, no translation.
"""

MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp"}


class VlmEngine:
    """OCR via the Claude Messages API. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-opus-5", max_tokens: int = 8000,
                 max_edge: int = 1568):
        self.model, self.max_tokens, self.max_edge = model, max_tokens, max_edge

    @property
    def name(self) -> str:
        return f"vlm/{self.model}"

    def _encode(self, image_path: str) -> tuple[str, str]:
        """Downscale to the API's long-edge limit and return (media_type, b64).

        Above ~1568px the API downsamples anyway, so sending a 3500px page just
        costs upload time and gives back the same pixels.
        """
        import cv2

        img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(image_path)
        h, w = img.shape[:2]
        scale = min(1.0, self.max_edge / max(h, w))
        if scale < 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise RuntimeError(f"could not encode {image_path}")
        return "image/png", base64.standard_b64encode(buf.tobytes()).decode()

    def run(self, image_path: str) -> Result:
        t = time.time()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return Result(self.name, [], 0.0, error="ANTHROPIC_API_KEY not set")
        try:
            import anthropic
        except ImportError:
            return Result(self.name, [], 0.0, error="pip install anthropic")

        try:
            media_type, data = self._encode(image_path)
            msg = anthropic.Anthropic().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": PROMPT},
                ]}],
            )
        except Exception as e:  # noqa: BLE001 - a failed engine is a benchmark result
            return Result(self.name, [], time.time() - t, error=f"{type(e).__name__}: {e}")

        text = "".join(b.text for b in msg.content if b.type == "text")
        # No boxes: the model returns text only. Lines carry a zero box, and the
        # review UI must source geometry from a detector instead.
        lines = [Line(text=l, box=(0, 0, 0, 0)) for l in text.splitlines() if l.strip()]
        return Result(self.name, lines, time.time() - t)
