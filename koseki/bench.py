"""Run every available OCR engine over every preprocessing variant and score it.

The output is a JSON record per (page, engine, variant) plus a summary table.
Nothing downstream -- translation, entity extraction, the review UI -- should be
built until this table says which combination is worth building on.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from .preprocess import prep
from .score import load_tokens, score as score_text, token_recall

VARIANTS = ("original", "decolored", "deskewed")


@dataclass
class Row:
    page: str
    engine: str
    variant: str
    seconds: float
    lines: int
    chars: int
    mean_conf: float | None
    cer: float | None
    bag_cer: float | None
    recall: float | None
    error: str | None


def make_variants(page_png: Path, cache: Path) -> dict[str, Path]:
    """Materialise preprocessing variants as files; engines all take a path."""
    cache.mkdir(parents=True, exist_ok=True)
    out = {"original": page_png}
    stem = page_png.stem
    p = prep(page_png)
    for name in ("decolored", "binary", "deskewed"):
        dest = cache / f"{stem}_{name}.png"
        if not dest.exists():
            cv2.imwrite(str(dest), getattr(p, name))
        out[name] = dest
    return out


def token_file(truth_dir: Path, page: str) -> Path:
    """Key-token list for `page`, falling back to the page it was cropped from.

    A crop needs its own list -- scoring a name panel against tokens that only
    appear in the columns above it counts a correct read as a miss.
    """
    exact = truth_dir / "tokens" / f"{page}.txt"
    if exact.exists():
        return exact
    return truth_dir / "tokens" / f"{page.split('-')[0]}-{page.split('-')[1]}.txt"


def load_truth(truth_dir: Path, page: str) -> str | None:
    f = truth_dir / f"{page}.txt"
    if not f.exists():
        return None
    return "\n".join(
        l for l in f.read_text(encoding="utf-8").splitlines() if not l.startswith("#")
    )


def run(engines, pages, truth_dir: Path, cache: Path, out_json: Path,
        variants=VARIANTS) -> list[Row]:
    rows: list[Row] = []
    records = []
    for page_png in pages:
        page = page_png.stem
        truth = load_truth(truth_dir, page)
        tokens = load_tokens(token_file(truth_dir, page))
        vs = make_variants(page_png, cache)
        for engine in engines:
            for variant in variants:
                if variant not in vs:
                    continue
                t = time.time()
                res = engine.run(str(vs[variant]))
                sc = score_text(truth, res.text) if truth else None
                rec, missed = token_recall(tokens, res.text) if tokens else (None, [])
                rows.append(Row(
                    page=page, engine=engine.name, variant=variant,
                    seconds=round(res.seconds or time.time() - t, 2),
                    lines=len(res.lines), chars=res.chars,
                    mean_conf=round(res.mean_conf, 4) if res.mean_conf else None,
                    cer=round(sc.cer, 4) if sc else None,
                    bag_cer=round(sc.bag_cer, 4) if sc else None,
                    recall=round(rec, 4) if rec is not None else None,
                    error=res.error,
                ))
                records.append({
                    **asdict(rows[-1]),
                    "missed_tokens": missed,
                    "text": res.text,
                    "boxes": [
                        {"text": l.text, "box": list(l.box), "conf": l.conf}
                        for l in res.lines
                    ],
                })
                print(f"  {page:6} {engine.name:12} {variant:10} "
                      f"{rows[-1].seconds:6.1f}s lines={rows[-1].lines:4d} "
                      f"chars={rows[-1].chars:5d} "
                      f"cer={rows[-1].cer if rows[-1].cer is not None else '-'} "
                      f"recall={rows[-1].recall if rows[-1].recall is not None else '-'} "
                      f"{rows[-1].error or ''}", flush=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def table(rows: list[Row]) -> str:
    hdr = f"{'page':7}{'engine':13}{'variant':11}{'secs':>7}{'lines':>7}{'chars':>7}{'conf':>8}{'CER':>8}{'bagCER':>8}{'recall':>8}"
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        out.append(
            f"{r.page:7}{r.engine:13}{r.variant:11}{r.seconds:7.1f}{r.lines:7d}{r.chars:7d}"
            f"{(f'{r.mean_conf:.3f}' if r.mean_conf else '-'):>8}"
            f"{(f'{r.cer:.3f}' if r.cer is not None else '-'):>8}"
            f"{(f'{r.bag_cer:.3f}' if r.bag_cer is not None else '-'):>8}"
            + f"{(f'{r.recall:.3f}' if r.recall is not None else '-'):>8}"
            + (f"  {r.error}" if r.error else "")
        )
    return "\n".join(out)
