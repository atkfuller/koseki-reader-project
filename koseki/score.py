"""Accuracy metrics for OCR output against a reference transcription.

Two numbers, deliberately, because they fail independently:

  CER      -- Levenshtein distance over the concatenated text, divided by the
              reference length. Punishes recognition errors AND ordering errors.
  bag-CER  -- the same edit distance computed over *multisets* of characters,
              so line order is irrelevant.

An engine that reads every glyph correctly but returns the columns left-to-right
scores terribly on CER and near-perfectly on bag-CER. That gap tells you the fix
is a sort, not a better model -- which is the single most common failure mode on
vertical Japanese.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_WS = re.compile(r"\s+")


def normalize(s: str) -> str:
    """NFKC-fold and strip whitespace.

    NFKC matters here: koseki print uses full-width digits and latin (３５２),
    while OCR engines are inconsistent about which width they emit. Without the
    fold, a correct read of ３５２ against a reference of 352 counts as three
    errors.
    """
    return _WS.sub("", unicodedata.normalize("NFKC", s))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def bag_distance(a: str, b: str) -> int:
    """Order-free edit distance: total surplus + total shortfall of characters."""
    ca, cb = Counter(a), Counter(b)
    return sum(((ca - cb) + (cb - ca)).values())


@dataclass
class Score:
    ref_chars: int
    hyp_chars: int
    cer: float
    bag_cer: float

    @property
    def accuracy(self) -> float:
        return max(0.0, 1.0 - self.cer)

    @property
    def bag_accuracy(self) -> float:
        return max(0.0, 1.0 - self.bag_cer)


def score(reference: str, hypothesis: str) -> Score:
    ref, hyp = normalize(reference), normalize(hypothesis)
    n = max(len(ref), 1)
    return Score(
        ref_chars=len(ref),
        hyp_chars=len(hyp),
        cer=levenshtein(ref, hyp) / n,
        bag_cer=bag_distance(ref, hyp) / n,
    )


def token_recall(tokens: list[str], hypothesis: str) -> tuple[float, list[str]]:
    """Fraction of known-correct strings that appear anywhere in the output.

    This is the metric that survives having no full-page reference. Dense Meiji
    brush pages cannot be transcribed end-to-end without an expert, but the
    names, eras and place names on them are recoverable -- often because the
    same people are restated in modern print elsewhere in the same file. Recall
    over that set answers the question the project actually cares about ("did we
    get the names?") and is immune to both reading-order and coverage gaps.

    Returns (recall, missed).
    """
    hyp = normalize(hypothesis)
    wanted = [normalize(t) for t in tokens if normalize(t)]
    if not wanted:
        return 0.0, []
    missed = [t for t, n in zip(tokens, wanted) if n not in hyp]
    return 1.0 - len(missed) / len(wanted), missed


def load_tokens(path) -> list[str]:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return []
    return [
        l.strip() for l in p.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
