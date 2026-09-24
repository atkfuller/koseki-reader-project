"""Read the Tier 1 (computerised 全部事項証明) pages of a koseki bundle to JSON.

    ./venv/bin/python scripts/read_tier1.py                      # data/pages/*.png
    ./venv/bin/python scripts/read_tier1.py data/raw/takagi.pdf  # renders first
    ./venv/bin/python scripts/read_tier1.py --no-cache

Handwritten pages are skipped by orientation before OCR, and anything that
turns out not to be a 全部事項証明 after OCR is reported and skipped too.
OCR output is cached per page under out/tier1/ocr/, because PaddleOCR takes
1-2 minutes a page on CPU and the parser is what you iterate on.

Where a page has a reference transcription in data/truth/, its accuracy is
printed, so this doubles as the Tier 1 check.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from koseki import tier1  # noqa: E402
from koseki.bench import load_truth, token_file  # noqa: E402
from koseki.lexicon import fix_ocr  # noqa: E402
from koseki.ocr.base import Line, reading_order_horizontal  # noqa: E402
from koseki.ocr.paddle_engine import PaddleEngine  # noqa: E402
from koseki.pdf import render_pdf  # noqa: E402
from koseki.score import load_tokens, score, token_recall  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out/tier1"
ENGINE = PaddleEngine(box_thresh=0.5)


def ocr_page(png: Path, use_cache: bool) -> list[Line]:
    cache = OUT / "ocr" / ENGINE.name.replace("/", "_") / f"{png.stem}.json"
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


def page_number(png: Path) -> int:
    return int(png.stem.split("-")[1])


def accuracy_report(png: Path, lines: list[Line]) -> str | None:
    """Score the cleaned, ordered, corrected page text against data/truth."""
    truth = load_truth(ROOT / "data/truth", png.stem)
    tf = token_file(ROOT / "data/truth", png.stem)
    if truth is None and not tf.exists():
        return None
    text = "\n".join(fix_ocr(l.text)[0] for l in reading_order_horizontal(lines))
    out = [f"  {png.stem}:"]
    if truth:
        s = score(truth, text)
        out.append(f"char accuracy {1 - s.cer:.1%} (CER {s.cer:.3f})")
    if tf.exists():
        rec, missed = token_recall(load_tokens(tf), text)
        out.append(f"key tokens {rec:.0%}" + (f", missed {missed}" if missed else ""))
    return "  ".join(out)


def summary(cert: tier1.Certificate) -> str:
    out = [f"Certificate {cert.issue_no} ({cert.office}), pages {cert.pages}, "
           f"certified {cert.certified_on}",
           f"  本籍 {cert.honseki}",
           f"  筆頭者 {cert.head_name}"]
    for ev in cert.registry_events:
        out.append(f"  [registry] {ev.type} / {ev.type_en}")
        for f in ev.fields:
            out.append(f"      {f.label}: {f.value}" + (f"  -> {f.date}" if f.date else ""))
            out += [f"        {c.label}: {c.value}" for c in f.children]
    for p in cert.persons:
        name = f"{p.surname or ''}{p.given_name or '?'}"
        out.append(f"  {name}{'  [除籍 removed]' if p.removed else ''}")
        for f in p.fields:
            extra = f.date or f.value_en
            out.append(f"      {f.label_en or f.label}: {f.value}" + (f"  -> {extra}" if extra else ""))
        for ev in p.events:
            src = "" if ev.type_source == "label" else " (type inferred)"
            out.append(f"    {ev.type_en or ev.type}{src}")
            for f in ev.fields:
                extra = f.date or f.value_en
                fix = f"  [OCR fixed from {f.corrected_from}]" if f.corrected_from else ""
                out.append(f"      {f.label_en or f.label}: {f.value}"
                           + (f"  -> {extra}" if extra else "") + fix)
    if cert.unparsed:
        out.append(f"  unparsed: {[u['text'] for u in cert.unparsed]}")
    if cert.dropped:
        out.append(f"  dropped as low-confidence: {cert.dropped}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default=str(ROOT / "data/pages"),
                    help="a PDF, or a directory of p-NN.png pages")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    src = Path(args.source)
    pngs = render_pdf(src, OUT / "pages") if src.suffix.lower() == ".pdf" \
        else sorted(src.glob("p-[0-9][0-9].png"))

    pages: dict[int, list[Line]] = {}
    reports = []
    for png in pngs:
        with Image.open(png) as im:
            if not tier1.is_portrait(*im.size):
                continue
        lines = ocr_page(png, use_cache=not args.no_cache)
        if not tier1.looks_like_tier1(lines):
            print(f"  {png.name}: portrait but not a 全部事項証明, skipped")
            continue
        pages[page_number(png)] = lines
        if r := accuracy_report(png, lines):
            reports.append(r)

    skipped = len(pngs) - len(pages)
    print(f"\nTier 1 pages: {sorted(pages)}  ({skipped} other pages left for the handwriting pipeline)")
    if reports:
        print("\nOCR accuracy against data/truth:")
        print("\n".join(reports))

    certs = tier1.parse(pages)
    OUT.mkdir(parents=True, exist_ok=True)
    for c in certs:
        dest = OUT / f"{c.issue_no or 'unknown'}.json"
        dest.write_text(json.dumps(c.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(summary(c))
        print(f"\n  -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
