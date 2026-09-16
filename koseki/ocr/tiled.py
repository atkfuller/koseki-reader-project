"""Tile a high-resolution page so a fixed-input detector can actually see the text.

NDLkotenOCR-Lite's detector takes a 1024x1024 input. A 300dpi koseki spread is
~3500px wide, so the whole-page path downscales by ~3.4x and the ~45px brush
characters land at ~13px -- below what the detector will fire on. Measured on
page 12 of the Takagi register: 1 line found whole-page, 12 lines on a quarter
crop of the same image at native resolution.

So we cut the page into overlapping tiles at native scale, OCR each, map the
boxes back into page coordinates, and drop duplicates from the overlap regions.
All tiles for a page go through a single CLI invocation -- model load dominates
per-call cost, and amortising it across ~12 tiles is the difference between
~50s and ~5s per page.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from .base import Line, Result
from .ndl_engine import VENV_PY


def _axis(extent: int, size: int, overlap: float) -> list[int]:
    """Start offsets covering `extent` with windows of `size` overlapping by `overlap`.

    The final window is pulled back flush against the far edge rather than
    padded, so no window is mostly empty and nothing near the margin is cut.
    """
    if size >= extent:
        return [0]
    stride = max(1, int(size * (1 - overlap)))
    starts = list(range(0, extent - size + 1, stride))
    if starts[-1] + size < extent:
        starts.append(extent - size)
    return starts


def _tiles(w: int, h: int, tile_w: int, tile_h: int,
           overlap: float) -> list[tuple[int, int, int, int]]:
    """Cover (w, h) with tile_w x tile_h windows.

    Tiles are rectangular, not square, and that matters more than it sounds:
    a text line has to fit *entirely* inside one tile or the recogniser returns
    two fragments and the merge step has no way to know they were one line.
    Passing a full-width tile for horizontal text (or full-height for vertical)
    guarantees whole lines; see `layout_for`.
    """
    return [
        (x, y, min(tile_w, w - x), min(tile_h, h - y))
        for y in _axis(h, tile_h, overlap)
        for x in _axis(w, tile_w, overlap)
    ]


def layout_for(w: int, h: int, band: int, orientation: str) -> tuple[int, int]:
    """Pick tile dimensions: strips across the text direction, whole lines along it.

    "vertical"   -- Japanese columns run top-to-bottom, so tiles are full-height
                    and `band` wide: a column is never cut in half.
    "horizontal" -- the mirror image, for the modern computerised pages.
    "square"     -- the naive baseline, kept so the benchmark can show what the
                    line-splitting actually costs.
    """
    if orientation == "vertical":
        return band, h
    if orientation == "horizontal":
        return w, band
    return band, band


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def is_degenerate(line: Line, tile: int) -> bool:
    """Reject detections that are artefacts rather than text.

    On a tile that is mostly blank security-paper background, the detector will
    occasionally return a single box spanning the whole tile whose recognised
    text is one character repeated a few hundred times ("00000...", "ーーー...").
    Two cheap signals catch essentially all of it: a box that covers most of the
    tile, and text with almost no distinct characters in it.
    """
    _, _, w, h = line.box
    if w > tile * 0.9 and h > tile * 0.9:
        return True
    if w == 0 or h == 0:
        return True
    t = line.text
    return len(t) >= 12 and len(set(t)) <= 2


def dedupe(lines: list[Line], iou_thresh: float = 0.35) -> list[Line]:
    """Greedy NMS over line boxes, preferring longer text then higher confidence.

    Text length is the primary key on purpose: when a line straddles a tile seam
    both tiles see a fragment and one tile sees the whole thing, and the whole
    thing is what we want -- it is usually the *less* confident of the two.
    """
    kept: list[Line] = []
    for line in sorted(lines, key=lambda l: (len(l.text), l.conf or 0), reverse=True):
        if all(_iou(line.box, k.box) < iou_thresh for k in kept):
            kept.append(line)
    return kept


class TiledNdlEngine:

    def __init__(self, band: int = 1200, overlap: float = 0.3,
                 orientation: str = "auto", binary: Path = VENV_PY,
                 timeout: int = 1800):
        self.band, self.overlap, self.orientation = band, overlap, orientation
        self.binary, self.timeout = Path(binary), timeout

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"ndl-tiled/{self.orientation}/{self.band}"

    def run(self, image_path: str) -> Result:
        t = time.time()
        img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if img is None:
            return Result(self.name, [], 0.0, error=f"unreadable {image_path}")
        h, w = img.shape[:2]
        orientation = self.orientation
        if orientation == "auto":
            # Landscape scans in this corpus are register spreads (vertical text);
            # portrait ones are the modern computerised printout (horizontal).
            orientation = "vertical" if w > h else "horizontal"
        tile_w, tile_h = layout_for(w, h, self.band, orientation)
        boxes = _tiles(w, h, tile_w, tile_h, self.overlap)
        max_tile = max(tile_w, tile_h)

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "tiles"
            odir = Path(td) / "out"
            tdir.mkdir(parents=True)
            odir.mkdir(parents=True)
            index: dict[str, tuple[int, int]] = {}
            for i, (x, y, tw, th) in enumerate(boxes):
                stem = f"t{i:03d}"
                cv2.imwrite(str(tdir / f"{stem}.png"), img[y:y + th, x:x + tw])
                index[stem] = (x, y)
            try:
                subprocess.run(
                    [str(self.binary), "--sourcedir", str(tdir),
                     "--output", str(odir), "--json-only"],
                    check=True, capture_output=True, timeout=self.timeout,
                )
            except subprocess.CalledProcessError as e:
                return Result(self.name, [], time.time() - t,
                              error=f"exit {e.returncode}: {(e.stderr or b'').decode()[-300:]}")
            except subprocess.TimeoutExpired:
                return Result(self.name, [], time.time() - t, error="timeout")

            lines: list[Line] = []
            for jf in sorted(odir.rglob("*.json")):
                ox, oy = index.get(jf.stem, (0, 0))
                data = json.loads(jf.read_text(encoding="utf-8"))
                for page in data.get("contents", []):
                    for item in page:
                        text = item.get("text") or ""
                        if not text or item.get("isTextline") not in ("true", True):
                            continue
                        pts = item.get("boundingBox") or []
                        if not pts:
                            continue
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        line = Line(
                            text=text,
                            box=(int(min(xs)) + ox, int(min(ys)) + oy,
                                 int(max(xs) - min(xs)), int(max(ys) - min(ys))),
                            conf=item.get("confidence"),
                        )
                        if not is_degenerate(line, max_tile):
                            lines.append(line)
        return Result(self.name, dedupe(lines), time.time() - t)
