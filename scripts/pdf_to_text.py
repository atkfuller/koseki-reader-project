"""Turn the printed (Tier 1) pages of a koseki PDF into plain Japanese text.

    ./venv/bin/python scripts/pdf_to_text.py                        # data/raw/takagi.pdf
    ./venv/bin/python scripts/pdf_to_text.py path/to/other.pdf
    ./venv/bin/python scripts/pdf_to_text.py --no-cache

One text file per page, lines in reading order, one printed row per line, to
out/text/<pdf name>/p-NN.txt, plus all.txt with every page in order. No
parsing and no translation: this is the text a later step translates.

Steps, per page:
  render     pdftoppm at 300dpi
  route      portrait pages only -- on the Takagi bundle every computerised
             page is portrait and every handwritten spread is landscape
  OCR        PaddleOCR, box_thresh=0.5 (best on the Tier 1 benchmark: 74/75
             fields exact); cached, since a page takes 1-2 minutes on CPU
  confirm    the page has the 全部事項証明 header and some 【】 labels
  clean      drop boxes under 0.7 confidence (margin art, not text)
  order      rows top to bottom, boxes left to right within a row
  fix        the known OCR slips in koseki/lexicon.py (プラジル -> ブラジル)

Where data/truth/ has a reference for the page, its character accuracy is
printed, so each run doubles as a check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from koseki.lexicon import fix_ocr  # noqa: E402
from koseki.ocr.base import Line  # noqa: E402
from koseki.ocr.paddle_engine import PaddleEngine  # noqa: E402
from koseki.pdf import page_count, render_pdf  # noqa: E402
from koseki.score import score  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENGINE = PaddleEngine(box_thresh=0.5)
CACHE = ROOT / "out/text/ocr" / ENGINE.name.replace("/", "_")
# Below this a box is margin art ("-4", "C55"); every real line scored >= 0.84.
MIN_CONF = 0.7
ROW_TOL = 25   # px between vertical centres of boxes on one row
TOP_TOL = 10   # px between top edges, for boxes drawn taller than their text


_FIELD_RE = re.compile(r"^[【\[［](?P<label>[^】\]］]+)[】\]］]\s*(?P<value>.*)$")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def is_portrait(width: int, height: int) -> bool:
    """Cheap pre-OCR routing: on the Takagi bundle every computerised page is
    portrait and every handwritten register spread is landscape."""
    return height > width


def looks_like_tier1(lines: list[Line]) -> bool:
    """Post-OCR confirmation: the 全部事項証明 header plus a few 【】 labels."""
    text = "".join(_squash(l.text) for l in lines)
    labels = sum(1 for l in lines if _FIELD_RE.match(_squash(l.text)))
    return "全部事項証明" in text and labels >= 3


def merge_label_values(lines: list[Line]) -> list[Line]:
    """Join a bare 【label】 box to the value box printed beside it.

    【名】 is set in body type and the name after it in display type roughly
    twice the size, so the detector returns two boxes whose vertical centres
    differ -- enough that a row sort can put the name *before* its label.
    """
    out = list(lines)
    for lab in [l for l in lines if (m := _FIELD_RE.match(_squash(l.text))) and not m.group("value")]:
        lx, ly, lw, lh = lab.box
        best = None
        for v in out:
            if v is lab or _FIELD_RE.match(_squash(v.text)):
                continue
            vx, vy, vw, vh = v.box
            gap = vx - (lx + lw)
            overlap = min(ly + lh, vy + vh) - max(ly, vy)
            if -10 <= gap <= 200 and overlap > 0.3 * min(lh, vh):
                if best is None or gap < best[0]:
                    best = (gap, v)
        if best:
            v = best[1]
            x0 = min(lx, v.box[0])
            x1 = max(lx + lw, v.box[0] + v.box[2])
            confs = [c for c in (lab.conf, v.conf) if c is not None]
            # Keep the label's own y and height so the pair sorts where the label was.
            merged = Line(lab.text + v.text, (x0, ly, x1 - x0, lh), min(confs) if confs else None)
            out = [merged if l is lab else l for l in out if l is not v]
    return out


def load_truth(page: str) -> str | None:
    """The reference transcription for a page, comment lines dropped."""
    f = ROOT / "data/truth" / f"{page}.txt"
    if not f.exists():
        return None
    return "\n".join(l for l in f.read_text(encoding="utf-8").splitlines() if not l.startswith("#"))


def ocr_page(png: Path, use_cache: bool) -> list[Line]:
    cache = CACHE / f"{png.stem}.json"
    if use_cache and cache.exists():
        return [Line(d["text"], tuple(d["box"]), d["conf"]) for d in json.loads(cache.read_text())]
    res = ENGINE.run(str(png))
    if res.error:
        raise RuntimeError(f"{png.name}: {res.error}")
    print(f"  ocr {png.name}: {len(res.lines)} lines in {res.seconds:.0f}s", flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps([{"text": l.text, "box": l.box, "conf": l.conf} for l in res.lines],
                                ensure_ascii=False, indent=1), encoding="utf-8")
    return res.lines


def rows(lines: list[Line]) -> list[list[Line]]:
    """Group boxes into printed rows, top to bottom, each row left to right.

    A box joins the row when its vertical centre is within ROW_TOL of the
    row's first box, or its top edge is within TOP_TOL of it. The second test
    is for oversized boxes: on page 1 the detector draws 籍 of 本　籍 twice its
    real height, which puts its centre on the row below while its top stays
    level with 本. (Plain box overlap is too loose -- rows here are close
    enough that 【更正事項】 and 【更正事由】 would merge.)
    """
    out: list[list[Line]] = []
    for l in sorted(lines, key=lambda l: l.box[1] + l.box[3] / 2):
        if out:
            a = out[-1][0].box
            same_centre = abs((a[1] + a[3] / 2) - (l.box[1] + l.box[3] / 2)) <= ROW_TOL
            same_top = abs(a[1] - l.box[1]) <= TOP_TOL
            if same_centre or same_top:
                out[-1].append(l)
                continue
        out.append([l])
    return [sorted(r, key=lambda l: l.box[0]) for r in out]


def row_text(row: list[Line]) -> str:
    """Boxes on one row, two spaces apart -- except single glyphs the form
    letter-spaces (本　　籍), which the detector returns one box each."""
    text = ""
    for i, l in enumerate(row):
        t = l.text.strip()
        if i and not (len(t) == 1 and len(row[i - 1].text.strip()) == 1):
            text += "  "
        text += t
    return text


def page_text(lines: list[Line]) -> str:
    kept = [l for l in lines if l.conf is None or l.conf >= MIN_CONF]
    # 【名】 and the large-print name beside it come back as two boxes at
    # different heights; joined first, or the name can sort above its label.
    kept = merge_label_values(kept)
    return "\n".join(fix_ocr(row_text(r))[0] for r in rows(kept))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", default=str(ROOT / "data/raw/takagi.pdf"))
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    out = ROOT / "out/text" / pdf.stem
    # Rendering 18 pages at 300dpi takes minutes; do it once per PDF.
    pngs = sorted((out / "pages").glob("p-*.png"))
    if args.no_cache or len(pngs) != page_count(pdf):
        pngs = render_pdf(pdf, out / "pages")

    pages: list[tuple[Path, str]] = []
    for png in pngs:
        with Image.open(png) as im:
            if not is_portrait(*im.size):
                continue                 # handwritten spread; later pipeline
        lines = ocr_page(png, use_cache=not args.no_cache)
        if not looks_like_tier1(lines):
            print(f"  {png.stem}: portrait but not a 全部事項証明, skipped")
            continue
        pages.append((png, page_text(lines)))

    for png, text in pages:
        dest = out / f"{png.stem}.txt"
        dest.write_text(text + "\n", encoding="utf-8")
        report = ""
        if truth := load_truth(png.stem):
            report = f"  char accuracy {1 - score(truth, text).cer:.1%} vs data/truth"
        print(f"  {png.stem}: {text.count(chr(10)) + 1} lines -> {dest.relative_to(ROOT)}{report}")

    (out / "all.txt").write_text(
        "\n\n".join(f"=== {png.stem} ===\n{text}" for png, text in pages) + "\n", encoding="utf-8")
    print(f"\n{len(pages)} printed page(s) of {len(pngs)}; "
          f"{len(pngs) - len(pages)} left for the handwriting pipeline -> {(out / 'all.txt').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
