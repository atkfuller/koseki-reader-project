"""Review flags and in-certificate cross-checks for a parsed Tier 1 certificate.

OCR confidence cannot be the only review signal. On page 2 of the Takagi
register PaddleOCR read the printed name 恵美子 as 惠美子 at 0.996 confidence --
more confident than most lines it read correctly. The errors that matter most
on a koseki are a character swapped for its old or variant form, and those are
exactly the ones a recogniser is sure about. So besides a confidence floor,
this module flags on what the text is, and on whether the certificate agrees
with itself:

  variant     a name containing a kanji with a common old/variant form --
              once per character per certificate, on its first occurrence,
              naming every name it appears in (高 in 高木 would otherwise be
              flagged on every parent field on every page)
  low-conf    OCR confidence below REVIEW_CONF
  parent      a 父/母 value that is one character off someone listed here who
              could be that parent, or that names someone who could not be
  birth-date  生年月日 disagreeing with the birth event's 出生日

Nothing here changes a value. Flags go on `Field.review`, and the parent links
it finds go on `Certificate.relationships`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .lexicon import NAME_LABELS, NAME_VARIANTS
from .score import levenshtein

if TYPE_CHECKING:
    from .tier1 import Certificate, Field, Person

# Every correctly read record line on the Takagi Tier 1 pages scored >= 0.938.
REVIEW_CONF = 0.9

_VARIANT_PAIRS = {**NAME_VARIANTS, **{new: old for old, new in NAME_VARIANTS.items()}}


def _flag(f: Field, reason: str) -> None:
    if reason not in f.review:
        f.review.append(reason)


def _all_fields(cert: Certificate):
    for ev in cert.registry_events:
        for f in ev.fields:
            yield f
            yield from f.children
    for p in cert.persons:
        yield from p.fields
        for ev in p.events:
            yield from ev.fields


def full_name(p: Person) -> str | None:
    if not p.given_name:
        return None
    return f"{p.surname or ''}{p.given_name}"


def check_variants(cert: Certificate) -> None:
    first: dict[str, Field] = {}
    names: dict[str, list[str]] = {}
    for f in _all_fields(cert):
        if f.label not in NAME_LABELS:
            continue
        for ch in dict.fromkeys(f.value):
            if ch in _VARIANT_PAIRS:
                first.setdefault(ch, f)
                if f.value not in names.setdefault(ch, []):
                    names[ch].append(f.value)
    for ch, f in first.items():
        _flag(f, f"variant: {ch} is easily confused with {_VARIANT_PAIRS[ch]}; confirm "
                 f"which the registry prints in {', '.join(names[ch])}")


def check_confidence(f: Field) -> None:
    if f.conf is not None and f.conf < REVIEW_CONF:
        _flag(f, f"low-conf: OCR confidence {f.conf:.2f}")


# Youngest plausible age of a parent at a child's birth.
MIN_PARENT_AGE = 12


def plausible_parent(parent: Person, child: Person, role: str) -> bool:
    """Could `parent` be `child`'s father/mother, on what the record says?

    Unknowns pass: this rules people out, it never rules them in.
    """
    kin = parent.get("続柄") or ""
    if kin.endswith("男" if role == "mother" else "女"):
        return False
    py, cy = (_birth_year(p) for p in (parent, child))
    return py is None or cy is None or cy - py >= MIN_PARENT_AGE


def _birth_year(p: Person) -> int | None:
    iso = next((f.date for f in p.fields if f.label == "生年月日"), None)
    return int(iso[:4]) if iso else None


def link_parents(cert: Certificate) -> None:
    """Link each 父/母 to the person in this certificate it names.

    An exact match to a plausible parent becomes a relationship; an exact match
    to an implausible one (born after the child, a daughter named as 父) is
    flagged instead. A value one character off a plausible parent is a likely
    misread of one name or the other, so both fields are flagged and no link
    is made until a reviewer decides.

    Plausibility is not optional. Families reuse a kanji across generations:
    on the Takagi register 清太's father is 高木幸市 and his son is 高木幸道,
    one character apart, and only the birth dates say they are not a misread.
    """
    names = {i: full_name(p) for i, p in enumerate(cert.persons)}
    for i, child in enumerate(cert.persons):
        for f in child.fields:
            if f.label not in {"父", "母"}:
                continue
            role = "father" if f.label == "父" else "mother"
            exact = [j for j, n in names.items() if n == f.value and j != i]
            if exact:
                j = exact[0]
                if plausible_parent(cert.persons[j], child, role):
                    cert.relationships.append({"child": i, "parent": j, "role": role})
                else:
                    _flag(f, f"parent: {f.value} is listed here but cannot be "
                             f"{child.given_name}'s {role} (birth date or 続柄)")
                continue
            for j, n in names.items():
                if j == i or not n or len(n) != len(f.value) or levenshtein(n, f.value) != 1:
                    continue
                if not plausible_parent(cert.persons[j], child, role):
                    continue
                _flag(f, f"parent: {f.value} differs by one character from {n} "
                         f"listed in this registry; one of them is misread")
                name_field = next((g for g in cert.persons[j].fields if g.label == "名"), None)
                if name_field:
                    _flag(name_field, f"parent: {child.given_name}'s {role} is recorded as "
                                      f"{f.value}; one of them is misread")


def check_birth_dates(p: Person) -> None:
    dob = next((f for f in p.fields if f.label == "生年月日"), None)
    if dob is None or dob.date is None:
        return
    for ev in p.events:
        for f in ev.fields:
            if f.label == "出生日" and f.date and f.date != dob.date:
                reason = f"birth-date: 生年月日 {dob.date} but 出生日 {f.date}"
                _flag(dob, reason)
                _flag(f, reason)


def review(cert: Certificate) -> None:
    check_variants(cert)
    for f in _all_fields(cert):
        check_confidence(f)
    link_parents(cert)
    for p in cert.persons:
        check_birth_dates(p)


def needs_review(cert: Certificate) -> list[Field]:
    return [f for f in _all_fields(cert) if f.review]
