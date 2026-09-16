"""OCR a single page and optionally draw the detected regions.

    ./venv/bin/python scripts/ocr_page.py data/pages/p-05.png
    ./venv/bin/python scripts/ocr_page.py data/pages/p-05.png --engine paddle --viz out/p05.png

The --viz output is the fastest way to tell a *detection* failure from a
*recognition* failure: if the boxes miss half the page, a better recogniser will
not help.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.dates import find_era_dates  # noqa: E402
from koseki.ocr.base import reading_order_vertical  # noqa: E402
from koseki.preprocess import prep  # noqa: E402


def build(name: str):
    if name == "paddle":
        from koseki.ocr.paddle_engine import PaddleEngine
        return PaddleEngine()
    if name == "ndl":
        from koseki.ocr.ndl_engine import NdlEngine
        return NdlEngine()
    if name == "ndl-tiled":
        from koseki.ocr.tiled import TiledNdlEngine
        return TiledNdlEngine()
    if name == "yomitoku":
        from koseki.ocr.yomitoku_engine import YomitokuEngine
        return YomitokuEngine()
    if name == "vlm":
        from koseki.ocr.vlm_engine import VlmEngine
        return VlmEngine()
    raise SystemExit(f"unknown engine {name!r}")


def draw(image_path: Path, lines, dest: Path) -> None:
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    for line in lines:
        x, y, w, h = line.box
        if w and h:
            # green where the recogniser was confident, red where it was not
            conf = line.conf if line.conf is not None else 0.5
            colour = (0, 200, 0) if conf >= 0.5 else (0, 0, 220)
            cv2.rectangle(img, (x, y), (x + w, y + h), colour, 3)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), img)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--engine", default="ndl-tiled",
                    choices=["paddle", "ndl", "ndl-tiled", "yomitoku", "vlm"])
    ap.add_argument("--variant", default="original",
                    choices=["original", "decolored", "binary", "deskewed"])
    ap.add_argument("--viz", type=Path, help="write an image with boxes drawn on it")
    args = ap.parse_args()

    src = args.image
    if args.variant != "original":
        out = Path("out/variants") / f"{src.stem}_{args.variant}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), getattr(prep(src), args.variant))
        src = out

    result = build(args.engine).run(str(src))
    if result.error:
        raise SystemExit(f"{result.engine}: {result.error}")

    ordered = reading_order_vertical(result.lines)
    for line in ordered:
        conf = f"{line.conf:.2f}" if line.conf is not None else "  - "
        print(f"{conf}  {line.text}")

    print(f"\n{result.engine}: {len(ordered)} lines, {result.chars} chars, "
          f"{result.seconds:.1f}s", file=sys.stderr)
    dates = find_era_dates(result.text)
    if dates:
        print("dates found:", file=sys.stderr)
        for d in dates:
            print(f"  {d}", file=sys.stderr)
    if args.viz:
        draw(args.image, result.lines, args.viz)
        print(f"boxes -> {args.viz}", file=sys.stderr)


if __name__ == "__main__":
    main()
