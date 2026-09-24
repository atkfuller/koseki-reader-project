"""Tier 1: the computerised 全部事項証明 (full-record certificate).

This is machine print in a rigid two-column form -- section labels on the left,
【field】value lines on the right -- so once the OCR lines are in order, parsing
is bookkeeping, not NLP. The steps:

  classify    portrait page + 【】 labels + 全部事項証明 header
  clean       drop page furniture (page counter, mascot, footer), keep what
              it says (issue number, certification date)
  merge       【名】 and the large-print name beside it are separate OCR boxes
  columns     split left labels from right values by x position
  parse       a small state machine over the ordered lines, across pages, so a
              person whose record continues onto the next page stays one person

Every field keeps its page, box and confidence -- the review UI needs to point
at the pixels a value came from.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date

from .dates import DateParseError, parse_date
from .lexicon import (EVENT_BY_FIRST_FIELD, EVENTS_EN, LABELS_EN, fix_ocr,
                      value_en)
from .ocr.base import Line, reading_order_horizontal

# Below this, a line is junk from the page margin ("-4", "C55": corners of the
# mascot art). Every real line on the Takagi Tier 1 pages scored >= 0.84.
MIN_CONF = 0.7

_FIELD_RE = re.compile(r"^[【\[［](?P<label>[^】\]］]+)[】\]］]\s*(?P<value>.*)$")
_PAGE_NO_RE = re.compile(r"^[(（]?\s*(?P<n>\d+)\s*の\s*(?P<i>\d+)\s*[)）]?$")
_ISSUE_RE = re.compile(r"(?P<no>\d{8}-\d{8}-\d{8})-?(?P<office>.*)$")

SECTION_REGISTRY = "戸籍事項"
SECTION_PERSON = "戸籍に記録されている者"
SECTION_EVENTS = "身分事項"
REMOVED = "除籍"


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def is_portrait(width: int, height: int) -> bool:
    """Cheap pre-OCR routing. On the Takagi bundle every computerised page is
    portrait and every handwritten register page is a landscape spread, so this
    decides which pages get the (slow) print pipeline at all."""
    return height > width


def looks_like_tier1(lines: list[Line]) -> bool:
    """Post-OCR confirmation: the header plus a handful of 【】 field labels."""
    text = "".join(_squash(l.text) for l in lines)
    labels = sum(1 for l in lines if _FIELD_RE.match(_squash(l.text)))
    return "全部事項証明" in text and labels >= 3


# --- per-page cleaning ------------------------------------------------------

@dataclass
class PageInfo:
    page: int
    page_of: tuple[int, int] | None = None     # (3の1) -> (1, 3)
    issue_no: str | None = None
    office: str | None = None
    continues: bool = False                     # 以下次頁
    ends: bool = False                          # 以下余白
    footer: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def clean_page(lines: list[Line], page: int) -> tuple[list[Line], PageInfo]:
    """Separate record content from page furniture."""
    info = PageInfo(page)
    keep: list[Line] = []
    issue_y = None
    for l in lines:
        if m := _ISSUE_RE.search(_squash(l.text)):
            info.issue_no, info.office = m.group("no"), m.group("office") or None
            issue_y = l.box[1]
    for l in lines:
        t = _squash(l.text)
        if l.conf is not None and l.conf < MIN_CONF:
            info.dropped.append(l.text)
        elif m := _PAGE_NO_RE.match(t):
            info.page_of = (int(m.group("i")), int(m.group("n")))
        elif t in {"全部事項証明", "発行番号"} or "キャラクター" in t or "うきび" in t:
            pass
        elif t == "以下次頁":
            info.continues = True
        elif t == "以下余白":
            info.ends = True
        elif _ISSUE_RE.search(t):
            pass
        elif issue_y is not None and l.box[1] > issue_y + 20:
            info.footer.append(t)  # certification statement, date, issuing mayor
        else:
            keep.append(l)
    return keep, info


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
            x0, y0 = min(lx, v.box[0]), min(ly, v.box[1])
            x1 = max(lx + lw, v.box[0] + v.box[2])
            y1 = max(ly + lh, v.box[1] + v.box[3])
            merged = Line(text=lab.text + v.text, box=(x0, ly, x1 - x0, lh),
                          conf=min(c for c in (lab.conf, v.conf) if c is not None)
                          if lab.conf is not None or v.conf is not None else None)
            # Keep the label's own y so the merged line sorts where the label was.
            merged.full_box = (x0, y0, x1 - x0, y1 - y0)  # type: ignore[attr-defined]
            out = [merged if l is lab else l for l in out if l is not v]
    return out


# --- parsing ----------------------------------------------------------------

@dataclass
class Field:
    label: str
    value: str
    page: int
    box: tuple[int, int, int, int]
    conf: float | None
    label_en: str | None = None
    value_en: str | None = None
    date: str | None = None
    date_note: str | None = None
    corrected_from: str | None = None
    children: list["Field"] = field(default_factory=list)


@dataclass
class Event:
    type: str | None
    fields: list[Field] = field(default_factory=list)
    type_en: str | None = None
    type_source: str = "label"   # "label" | "inferred"


@dataclass
class Person:
    given_name: str | None = None
    surname: str | None = None
    removed: bool = False        # 除籍 box: no longer in this registry
    fields: list[Field] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    def get(self, label: str) -> str | None:
        return next((f.value for f in self.fields if f.label == label), None)


@dataclass
class Certificate:
    issue_no: str | None
    office: str | None
    pages: list[int]
    honseki: str | None = None
    head_name: str | None = None
    registry_events: list[Event] = field(default_factory=list)
    persons: list[Person] = field(default_factory=list)
    certified_on: str | None = None
    footer: list[str] = field(default_factory=list)
    unparsed: list[dict] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _make_field(label: str, value: str, line: Line, page: int) -> Field:
    value, fixes = fix_ocr(value, label)
    f = Field(label=label, value=value, page=page, box=getattr(line, "full_box", line.box),
              conf=line.conf, label_en=LABELS_EN.get(label))
    if fixes:
        f.corrected_from = line.text
    try:
        d = parse_date(value)
        # Only a value that *is* a date gets one; 更正事由 quotes a date inside
        # a sentence, and that is not the field's date.
        if _squash(d.source if not isinstance(d, date) else value) != _squash(value):
            raise DateParseError("date is embedded in prose")
        if isinstance(d, date):
            f.date = d.isoformat()
        else:
            f.date = d.gregorian.isoformat()
            if d.lunisolar:
                f.date_note = "lunisolar calendar: only the year is exact"
    except (DateParseError, ValueError):
        f.value_en = value_en(label, value)
    return f


def split_columns(lines: list[Line]) -> float:
    """x that separates the left label column from the right value column.

    Taken from the leftmost 【 line on the page. Labels are indented under
    their parent (【従前の記録】 then 【本籍】), so the minimum is the column edge.
    """
    xs = [l.box[0] for l in lines if _FIELD_RE.match(_squash(l.text))]
    return (min(xs) - 40) if xs else float("inf")


def _join_left_rows(lines: list[Line], split: float, tol: int = 30) -> list[Line]:
    """Rejoin left-column labels the form letter-spaces: 除　　籍, 本　　籍, 出　生.

    The detector sees the gap as a word break and returns one box per glyph.
    Right-column lines are left alone -- there, a second box on the row is a
    separate value.
    """
    out: list[Line] = []
    for l in lines:
        prev = out[-1] if out else None
        if (prev is not None and l.box[0] + l.box[2] / 2 < split
                and prev.box[0] + prev.box[2] / 2 < split
                and abs((prev.box[1] + prev.box[3] / 2) - (l.box[1] + l.box[3] / 2)) <= tol):
            x0, y0 = min(prev.box[0], l.box[0]), min(prev.box[1], l.box[1])
            x1 = max(prev.box[0] + prev.box[2], l.box[0] + l.box[2])
            y1 = max(prev.box[1] + prev.box[3], l.box[1] + l.box[3])
            confs = [c for c in (prev.conf, l.conf) if c is not None]
            out[-1] = Line(prev.text + l.text, (x0, y0, x1 - x0, y1 - y0),
                           min(confs) if confs else None)
        else:
            out.append(l)
    return out


def parse(pages: dict[int, list[Line]]) -> list[Certificate]:
    """Parse OCR'd Tier 1 pages into certificates, one per 発行番号."""
    stream: list[tuple[int, str, Line]] = []   # (page, "L"|"R", line)
    infos: list[PageInfo] = []
    for page in sorted(pages):
        kept, info = clean_page(pages[page], page)
        kept = merge_label_values(kept)
        split = split_columns(kept)
        infos.append(info)
        for l in _join_left_rows(reading_order_horizontal(kept), split):
            side = "L" if l.box[0] + l.box[2] / 2 < split else "R"
            stream.append((page, side, l))

    # Group pages by issue number; a page with none joins the previous one.
    groups: list[tuple[PageInfo, list[int]]] = []
    for info in infos:
        if groups and (info.issue_no is None or info.issue_no == groups[-1][0].issue_no):
            groups[-1][1].append(info.page)
        else:
            groups.append((info, [info.page]))

    certs = []
    for head, page_nums in groups:
        cert = Certificate(issue_no=head.issue_no, office=head.office, pages=page_nums)
        for info in infos:
            if info.page in page_nums:
                cert.footer += info.footer
                cert.dropped += info.dropped
        for t in cert.footer:
            try:
                cert.certified_on = parse_date(t).gregorian.isoformat()  # type: ignore[union-attr]
                break
            except (DateParseError, ValueError, AttributeError):
                continue
        _parse_stream(cert, [s for s in stream if s[0] in page_nums])
        certs.append(cert)
    return certs


def _parse_stream(cert: Certificate, stream: list[tuple[int, str, Line]]) -> None:
    section = "header"
    header_values: list[str] = []
    person: Person | None = None
    event: Event | None = None
    pending_type: str | None = None   # left-hand event label waiting for its first field
    last: Field | None = None
    parent: tuple[Field, int] | None = None   # (【従前の記録】, its x) while nesting

    def new_event(target: list[Event], first_label: str) -> Event:
        nonlocal pending_type
        if pending_type:
            ev = Event(type=pending_type, type_en=EVENTS_EN.get(pending_type))
        else:
            t = EVENT_BY_FIRST_FIELD.get(first_label)
            ev = Event(type=t, type_en=EVENTS_EN.get(t or ""), type_source="inferred")
        pending_type = None
        target.append(ev)
        return ev

    for page, side, line in stream:
        text = _squash(line.text)
        if side == "L":
            if text == SECTION_REGISTRY:
                section, event, pending_type = "registry", None, None
            elif text == SECTION_PERSON:
                person = Person()
                cert.persons.append(person)
                section, event, pending_type = "person", None, None
            elif text == SECTION_EVENTS and person:
                section, event, pending_type = "events", None, None
            elif text == REMOVED and person:
                person.removed = True
            elif text in EVENTS_EN and section in {"registry", "events"}:
                pending_type, event = text, None
            elif section != "header":
                # Fragments ("生" of a split 出 生) -- the event type is recovered
                # from the first field instead.
                cert.unparsed.append({"page": page, "text": line.text, "where": "left column"})
            continue

        m = _FIELD_RE.match(text)
        if not m:
            if section == "header":
                header_values.append(text)
            elif last is not None:
                last.value += text          # wrapped value, e.g. 更正事由 ... 変更
                last.value_en = value_en(last.label, last.value)
            else:
                cert.unparsed.append({"page": page, "text": line.text, "where": "right column"})
            continue

        label, value = m.group("label"), m.group("value")
        f = _make_field(label, value, line, page)
        last = f

        if parent and line.box[0] > parent[1] + 30:
            parent[0].children.append(f)
            continue
        parent = (f, line.box[0]) if not value else None

        if section in {"header", "registry"}:
            section = "registry"
            if event is None or pending_type or (label in EVENT_BY_FIRST_FIELD and any(
                    x.label == label for x in event.fields)):
                event = new_event(cert.registry_events, label)
            event.fields.append(f)
        elif section == "person" and person:
            person.fields.append(f)
            if label == "名":
                person.given_name = value
        elif section == "events" and person:
            if event is None or pending_type or (label in EVENT_BY_FIRST_FIELD and any(
                    x.label == label for x in event.fields)):
                event = new_event(person.events, label)
            event.fields.append(f)

    # Header: the right-hand column above 戸籍事項 is 本籍 then 氏名.
    if header_values:
        cert.honseki = header_values[0]
    if len(header_values) > 1:
        cert.head_name = header_values[1]

    # The surname is printed once, in the header, as part of the head's name;
    # OCR loses the space in 山田　一郎. The first person listed is the head, so
    # the surname is whatever precedes their given name.
    first = cert.persons[0].given_name if cert.persons else None
    if cert.head_name and first and cert.head_name.endswith(first):
        surname = cert.head_name[: -len(first)] or None
        for p in cert.persons:
            p.surname = surname
