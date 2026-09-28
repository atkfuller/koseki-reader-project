"""English rendering of a parsed Tier 1 certificate, page by page.

Every line of English comes from koseki/lexicon.py -- field labels, kin terms,
the gazetteer, name readings, fixed legal wording -- or from the date parser.
There is no machine translation, for the reason lexicon.py gives: names,
places and legal terms are what MT damages most. A value with no table entry
is left in Japanese and listed as untranslated, so a gap is visible and can be
closed by adding one table row.

The pages follow the printed order: the rows of each page are the rows the
parser attributed to it, with the left-column section labels (戸籍事項,
身分事項, 出生 ...) placed on the page of the field that follows them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .dates import DateParseError, parse_date
from .lexicon import EVENTS_EN, date_en, name_en, phrase_en, place_en
from .tier1 import Certificate, Event, Field

TITLE = ("全部事項証明", "Certificate of All Recorded Matters (full family register extract)")

SECTIONS_EN = {
    "本籍": "Registered domicile",
    "氏名": "Head of the registry",
    "戸籍事項": "Registry matters",
    "戸籍に記録されている者": "Person recorded in the registry",
    "身分事項": "Personal status matters",
    "除籍": "Removed from the registry",
    "発行番号": "Issue number",
    "以下次頁": "Continued on next page",
    "以下余白": "End of record",
}


@dataclass
class Row:
    ja: str
    en: str | None          # None: nothing in the tables for it
    kind: str = "field"     # "section" | "event" | "field" | "child" | "furniture"
    page: int | None = None
    review: list[str] | None = None   # the field's checks.py flags


def field_en(f: Field) -> str | None:
    if f.date:
        return date_en(f.date) + (f" ({f.date_note})" if f.date_note else "")
    if not f.value:
        return ""            # 【従前の記録】 heads its nested fields, holds no value
    return f.value_en


def _field_rows(f: Field, kind: str = "field") -> list[Row]:
    label_en = f.label_en or f.label
    value_en = field_en(f)
    rows = [Row(f"【{f.label}】{f.value}",
                None if value_en is None else f"{label_en}: {value_en}".rstrip(": "),
                kind, f.page, f.review or None)]
    for c in f.children:
        rows += _field_rows(c, "child")
    return rows


def _event_rows(ev: Event) -> list[Row]:
    rows = [Row(ev.type or "?", ev.type_en, "event")]
    for f in ev.fields:
        rows += _field_rows(f)
    return rows


def _footer_en(line: str) -> str | None:
    """The certification statement, its date, and the issuing mayor."""
    try:
        d = parse_date(line)
        return date_en((d if isinstance(d, date) else d.gregorian).isoformat())
    except (DateParseError, ValueError):
        return phrase_en(line) or name_en(line)


def page_rows(cert: Certificate) -> dict[int, list[Row]]:
    """The certificate as bilingual rows, grouped by the page they print on."""
    first, last = cert.pages[0], cert.pages[-1]
    rows: list[Row] = [
        Row("本籍", SECTIONS_EN["本籍"], "section", first),
        Row(cert.honseki or "", place_en(cert.honseki or ""), "field", first),
        Row("氏名", SECTIONS_EN["氏名"], "section", first),
        Row(cert.head_name or "", name_en(cert.head_name or ""), "field", first),
    ]
    if cert.registry_events:
        rows.append(Row("戸籍事項", SECTIONS_EN["戸籍事項"], "section"))
        for ev in cert.registry_events:
            rows += _event_rows(ev)
    for p in cert.persons:
        rows.append(Row("戸籍に記録されている者", SECTIONS_EN["戸籍に記録されている者"], "section"))
        if p.removed:
            rows.append(Row("除籍", SECTIONS_EN["除籍"], "section"))
        rows += [r for f in p.fields for r in _field_rows(f)]
        if p.events:
            rows.append(Row("身分事項", SECTIONS_EN["身分事項"], "section"))
            for ev in p.events:
                rows += _event_rows(ev)

    # A label row prints on the page of the field that follows it.
    nxt = last
    for r in reversed(rows):
        if r.page is None:
            r.page = nxt
        nxt = r.page

    out: dict[int, list[Row]] = {n: [] for n in cert.pages}
    for r in rows:
        out[r.page].append(r)  # type: ignore[index]
    for n in cert.pages:
        end = "以下余白" if n == last else "以下次頁"
        out[n].append(Row(end, SECTIONS_EN[end], "furniture", n))
        out[n].append(Row(f"発行番号 {cert.issue_no}-{cert.office or ''}",
                          f"Issue number {cert.issue_no} ({place_en(cert.office or '') or cert.office})",
                          "furniture", n))
    out[last] += [Row(t, _footer_en(t), "furniture", last) for t in cert.footer]
    return out


def untranslated(rows: list[Row]) -> list[str]:
    return [r.ja for r in rows if r.en is None]


def _cell(s: str) -> str:
    return s.replace("|", "\\|")


def render_page(cert: Certificate, page: int, rows: list[Row]) -> str:
    i = cert.pages.index(page) + 1
    out = [f"# Page {i} of {len(cert.pages)} — {TITLE[1]}", "",
           f"{TITLE[0]} ({len(cert.pages)}の{i})", "",
           "| Japanese | English |", "|---|---|"]
    for r in rows:
        ja, en = _cell(r.ja), _cell(r.en) if r.en is not None else "*(untranslated)*"
        if r.kind == "section":
            ja, en = f"**{ja}**", f"**{en}**"
        elif r.kind == "event":
            ja, en = f"*{ja}*", f"*{en}*"
        elif r.kind == "child":
            ja, en = f"↳ {ja}", f"↳ {en}"
        if r.review:
            en += " ⚠ " + _cell("; ".join(r.review))
        out.append(f"| {ja} | {en} |")
    if gaps := untranslated(rows):
        out += ["", "Left in Japanese (no table entry): " + "、".join(gaps)]
    return "\n".join(out) + "\n"
