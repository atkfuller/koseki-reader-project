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

Every name is also read a second time by yomitoku, and a name the two engines
disagree on is flagged for review (koseki/crosscheck.py). That adds ~30-90s a
page on first run, cached like the rest; --no-second-read skips it.

Each page is then written out in English, Japanese alongside, to
out/tier1/en/<issue number>/p-NN.md (koseki/translate.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from koseki import checks, crosscheck, tier1, translate  # noqa: E402
from koseki.bench import load_truth, token_file  # noqa: E402
from koseki.lexicon import fix_ocr  # noqa: E402
from koseki.ocr.base import Line, reading_order_horizontal  # noqa: E402
from koseki.ocr.paddle_engine import PaddleEngine  # noqa: E402
from koseki.ocr.yomitoku_engine import YomitokuEngine  # noqa: E402
from koseki.pdf import render_pdf  # noqa: E402
from koseki.score import load_tokens, score, token_recall  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out/tier1"
ENGINE = PaddleEngine(box_thresh=0.5)
# Second opinion on names only. Its reading_order mode has no effect on the
# line-level output the adapter returns; see the Tier 1 benchmark.
SECOND = YomitokuEngine(reading_order="auto")


def ocr_page(png: Path, use_cache: bool, engine=ENGINE) -> list[Line]:
    cache = OUT / "ocr" / engine.name.replace("/", "_") / f"{png.stem}.json"
    if use_cache and cache.exists():
        return [Line(d["text"], tuple(d["box"]), d["conf"]) for d in json.loads(cache.read_text())]
    res = engine.run(str(png))
    if res.error:
        raise RuntimeError(f"{png.name} ({engine.name}): {res.error}")
    print(f"  ocr {png.name} ({engine.name}): {len(res.lines)} lines in {res.seconds:.0f}s", flush=True)
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
    if cert.relationships:
        out.append("  family links:")
        for r in cert.relationships:
            child, parent = cert.persons[r["child"]], cert.persons[r["parent"]]
            out.append(f"      {checks.full_name(child)} -> {r['role']} {checks.full_name(parent)}")
    flagged = checks.needs_review(cert)
    out.append(f"  needs review: {len(flagged)} field(s)")
    for f in flagged:
        out += [f"      p{f.page} 【{f.label}】{f.value}: {why}" for why in f.review]
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
    ap.add_argument("--no-second-read", action="store_true",
                    help="skip the yomitoku cross-check of names")
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

    if not args.no_second_read:
        if not SECOND.binary.exists():
            print(f"\nsecond read skipped: {SECOND.binary} not installed (make setup)")
        else:
            second: dict[int, list[Line]] = {}
            for png in pngs:
                if page_number(png) not in pages:
                    continue
                try:
                    second[page_number(png)] = ocr_page(png, not args.no_cache, SECOND)
                except RuntimeError as e:   # a failed second read costs a check, not the run
                    print(f"  second read failed, names on this page unchecked: {e}")
            for c in certs:
                crosscheck.cross_check(c, second, SECOND.name)
            print(f"\nNames cross-checked with {SECOND.name} on pages {sorted(second)}")
    OUT.mkdir(parents=True, exist_ok=True)
    for c in certs:
        dest = OUT / f"{c.issue_no or 'unknown'}.json"
        dest.write_text(json.dumps(c.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(summary(c))
        print(f"\n  -> {dest.relative_to(ROOT)}")

        en_dir = OUT / "en" / (c.issue_no or "unknown")
        en_dir.mkdir(parents=True, exist_ok=True)
        print("\n  English:")
        for page, rows in translate.page_rows(c).items():
            dest = en_dir / f"p-{page:02d}.md"
            dest.write_text(translate.render_page(c, page, rows), encoding="utf-8")
            gaps = translate.untranslated(rows)
            print(f"    -> {dest.relative_to(ROOT)}  {len(rows) - len(gaps)}/{len(rows)} lines in English"
                  + (f", left in Japanese: {'、'.join(gaps)}" if gaps else ""))


if __name__ == "__main__":
    main()
