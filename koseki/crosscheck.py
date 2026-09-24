"""Second-engine check on names: flag a name where two OCR engines disagree.

PaddleOCR is the Tier 1 engine because it reads the page best overall, but its
errors are confident ones: 惠美子 for the printed 恵美子 at 0.996. yomitoku is
weaker overall -- it floods a page with background noise -- yet it read that
name correctly. Two engines trained on different data rarely make the same
mistake on the same glyph, so disagreement is a strong review signal and
agreement is real (if not conclusive) evidence.

Both engines run on the same whole-page image, so their boxes share pixel
coordinates. For each name field we take the second engine's lines that fall
inside the field's box and compare text. Crops are deliberately not used: the
baseline measured that OCR on a cropped region reads worse than the full page
(docs/ocr-baseline.md). Junk the second engine finds elsewhere on the page
never lands in a name box, so it does no harm here.

Only names are cross-checked. They are what a reviewer must never get wrong,
and what `lexicon.fix_ocr` is forbidden to touch.
"""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from .lexicon import NAME_LABELS
from .ocr.base import Line

if TYPE_CHECKING:
    from .tier1 import Certificate, Field

# A second-engine line belongs to a field when at least this much of it lies
# inside the field's box. The two engines' boxes for the same text differ by a
# few pixels; a neighbouring line overlaps by far less than half.
MIN_INSIDE = 0.5

_LABEL_PREFIX = re.compile(r"^.*?[】\]］]")
# Punctuation and spacing that engines render differently without the name
# being different: タカギ，クミコ vs タカギ クミコ.
_IGNORABLE = re.compile(r"[\s,，、・.．]")


def comparable(s: str) -> str:
    return _IGNORABLE.sub("", unicodedata.normalize("NFKC", s))


def _inside(line: Line, box: tuple[int, int, int, int]) -> float:
    lx, ly, lw, lh = line.box
    bx, by, bw, bh = box
    ix = max(0, min(lx + lw, bx + bw) - max(lx, bx))
    iy = max(0, min(ly + lh, by + bh) - max(ly, by))
    area = lw * lh
    return ix * iy / area if area else 0.0


def second_read(f: Field, lines: list[Line]) -> str | None:
    """What the second engine read inside `f`'s box, label stripped, or None."""
    hits = sorted((l for l in lines if _inside(l, f.box) >= MIN_INSIDE), key=lambda l: l.box[0])
    text = "".join(l.text for l in hits)
    text = _LABEL_PREFIX.sub("", unicodedata.normalize("NFKC", text), count=1).strip()
    return text or None


def _name_fields(cert: Certificate):
    for p in cert.persons:
        yield from (f for f in p.fields if f.label in NAME_LABELS)
        for ev in p.events:
            yield from (f for f in ev.fields if f.label in NAME_LABELS)


def cross_check(cert: Certificate, second: dict[int, list[Line]], engine: str) -> list[Field]:
    """Flag name fields that `engine`'s read of the same page disagrees with.

    `second` is {page: lines} from the second engine. A name the second engine
    found nothing for is left alone: no reading is not a disagreement. Returns
    the fields flagged.
    """
    flagged = []
    for f in _name_fields(cert):
        if f.page not in second:
            continue
        other = second_read(f, second[f.page])
        if other is None or comparable(other) == comparable(f.value):
            continue
        reason = (f"second-read: {engine} reads {other} where the primary read is "
                  f"{f.value}; check the scan")
        if reason not in f.review:
            f.review.append(reason)
        flagged.append(f)
    return flagged
