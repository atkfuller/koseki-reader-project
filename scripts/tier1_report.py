"""Turn the Tier 1 benchmark into one HTML page a person can check by eye.

    ./venv/bin/python scripts/run_tier1.py      # OCR, ~30 min on CPU
    ./venv/bin/python scripts/tier1_report.py   # -> out/tier1/report.html

For every engine x variant it shows:

  * a scoreboard: character accuracy after reading-order sort, key-token
    recall, time;
  * every parsed field, side by side across engines, with its English and a
    tick when "【label】value" appears verbatim as a line of data/truth;
  * the raw read of each page against the reference, with the characters
    that differ highlighted.

The page contains the register's personal data, so it is written under out/
(gitignored) and is meant to be opened locally, not published.
"""
from __future__ import annotations

import difflib
import html
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki import tier1  # noqa: E402
from koseki.bench import load_truth, token_file  # noqa: E402
from koseki.ocr.base import Line, reading_order_horizontal  # noqa: E402
from koseki.score import load_tokens, normalize, score, token_recall  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / "data/truth"
RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/tier1/results.json"
DEST = RESULTS.with_name("report.html")

esc = html.escape


# --- data -------------------------------------------------------------------

def load_runs() -> dict[tuple[str, str], dict[int, list[Line]]]:
    """{(engine, variant): {page_no: lines}} from the benchmark's JSON."""
    runs: dict[tuple[str, str], dict[int, list[Line]]] = defaultdict(dict)
    for r in json.loads(RESULTS.read_text(encoding="utf-8")):
        page = int(r["page"].split("-")[1])
        runs[(r["engine"], r["variant"])][page] = [
            Line(b["text"], tuple(b["box"]), b["conf"]) for b in r["boxes"]]
    return runs


def ordered_text(lines: list[Line]) -> str:
    return "\n".join(l.text for l in reading_order_horizontal(lines))


def truth_lines(page: int) -> set[str]:
    t = load_truth(TRUTH, f"p-{page:02d}") or ""
    return {normalize(l) for l in t.splitlines() if l.strip()}


def field_rows(cert: tier1.Certificate):
    """(key, display-group, field) for every field, keyed so engines line up."""
    seen: dict[tuple, int] = defaultdict(int)

    def key(*k):
        seen[k] += 1
        return (*k, seen[k])

    for ev in cert.registry_events:
        for f in ev.fields:
            yield key("registry", ev.type, f.label), f"Registry · {ev.type or '?'}", f
            for c in f.children:
                yield key("registry", ev.type, f"{f.label}›{c.label}"), \
                    f"Registry · {ev.type or '?'}", c
    for i, p in enumerate(cert.persons):
        who = f"Person {i + 1}"
        for f in p.fields:
            yield key(who, "", f.label), who, f
        for ev in p.events:
            for f in ev.fields:
                yield key(who, ev.type, f.label), f"{who} · {ev.type_en or ev.type or '?'}", f


def correct(f: tier1.Field, truth: dict[int, set[str]]) -> bool:
    return normalize(f"【{f.label}】{f.value}") in truth.get(f.page, set())


# --- rendering ----------------------------------------------------------------

CSS = """
:root{--bg:#fbfbf9;--fg:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--card:#fff;
--ok:#1f7a3f;--okbg:#e3f3e8;--bad:#b3261e;--badbg:#fbe4e2;--add:#d6efdc;--del:#f7d4d1;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--mute:#9a998f;
--line:#34332f;--card:#1f1f1d;--ok:#7fd49a;--okbg:#17301f;--bad:#f2a49d;--badbg:#3a1a18;
--add:#1d4a2a;--del:#5a211d;--warn:#e6b760}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,
"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:1400px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:40px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
h3{font-size:15px;margin:24px 0 8px}
p.note{color:var(--mute);max-width:80ch;margin:4px 0 12px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--card)}
table{border-collapse:collapse;width:100%}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--card);font-weight:600;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.group td{background:var(--bg);font-weight:600;color:var(--mute)}
.best{font-weight:700}
.ok{color:var(--ok)}.bad{color:var(--bad)}
td.cell-ok{background:var(--okbg)}td.cell-bad{background:var(--badbg)}
.en{color:var(--mute);font-size:12px;display:block}
.flag{color:var(--warn);font-size:12px;display:block}
.label{white-space:nowrap;font-weight:600}
.missing{color:var(--mute);font-style:italic}
details{margin:8px 0;border:1px solid var(--line);border-radius:6px;background:var(--card)}
summary{cursor:pointer;padding:8px 12px;font-weight:600}
.diff{display:grid;grid-template-columns:1fr 1fr;font-family:ui-monospace,"Hiragino Sans",monospace;font-size:13px}
.diff div{padding:1px 10px;border-top:1px solid var(--line);white-space:pre-wrap;word-break:break-all}
.diff .hd{font-family:system-ui;font-weight:600;background:var(--bg)}
ins{background:var(--add);text-decoration:none}del{background:var(--del);text-decoration:none}
.eq{color:var(--mute)}
nav a{margin-right:16px}
"""


def char_diff(a: str, b: str) -> tuple[str, str]:
    """Reference and read of one line, differing characters wrapped."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    left, right = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            left.append(esc(a[i1:i2]))
            right.append(esc(b[j1:j2]))
        else:
            if i2 > i1:
                left.append(f"<del>{esc(a[i1:i2])}</del>")
            if j2 > j1:
                right.append(f"<ins>{esc(b[j1:j2])}</ins>")
    return "".join(left), "".join(right)


def page_diff(ref: str, hyp: str) -> str:
    """Two-column line-aligned diff of normalised reference vs read."""
    r = [normalize(l) for l in ref.splitlines() if normalize(l)]
    h = [normalize(l) for l in hyp.splitlines() if normalize(l)]
    out = ['<div class="diff"><div class="hd">Reference (data/truth)</div>'
           '<div class="hd">Engine read, in reading order</div>']
    sm = difflib.SequenceMatcher(None, r, h, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                out.append(f'<div class="eq">{esc(r[i1 + k])}</div><div class="eq">{esc(h[j1 + k])}</div>')
            continue
        a, b = r[i1:i2], h[j1:j2]
        for k in range(max(len(a), len(b))):
            x = a[k] if k < len(a) else ""
            y = b[k] if k < len(b) else ""
            lx, ry = char_diff(x, y)
            out.append(f"<div>{lx}</div><div>{ry}</div>")
    out.append("</div>")
    return "".join(out)


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.1%}"


def main() -> None:
    if not RESULTS.exists():
        raise SystemExit(f"no {RESULTS.relative_to(ROOT)}; run scripts/run_tier1.py first")
    runs = load_runs()
    pages = sorted({p for r in runs.values() for p in r})
    truth = {p: truth_lines(p) for p in pages}
    names = [f"{e} · {v}" for e, v in runs]

    # scoreboard
    board = []
    for (engine, variant), by_page in runs.items():
        per = []
        for p in pages:
            ref = load_truth(TRUTH, f"p-{p:02d}")
            txt = ordered_text(by_page.get(p, []))
            s = score(ref, txt) if ref else None
            rec, missed = token_recall(load_tokens(token_file(TRUTH, f"p-{p:02d}")), txt)
            per.append((s, rec, missed))
        certs = tier1.parse({p: ls for p, ls in by_page.items() if ls})
        fields = [f for c in certs for _, _, f in field_rows(c)]
        ok = sum(correct(f, truth) for f in fields)
        board.append(dict(name=f"{engine} · {variant}", per=per, certs=certs,
                          fields=len(fields), ok=ok, by_page=by_page))

    best_fields = max(b["ok"] for b in board)
    body = [f"<h1>Tier 1 OCR comparison</h1>",
            '<p class="note">Takagi register, pages '
            f'{", ".join(map(str, pages))} (全部事項証明). Every engine is scored on its lines '
            "after the same reading-order sort, with no OCR fix-ups, so the scoreboard compares "
            "engines. The field table shows the full pipeline: the parser, "
            "<code>lexicon.fix_ocr</code> (written for PaddleOCR's errors), dates and English.</p>",
            '<nav><a href="#board">Scoreboard</a><a href="#fields">Fields, all engines</a>'
            '<a href="#reads">Raw reads</a></nav>']

    # 1. scoreboard
    body.append('<h2 id="board">Scoreboard</h2>')
    body.append('<p class="note">Char accuracy = 1 − CER against the reference. Key tokens = '
                "names, dates and places found anywhere on the page. Fields correct = parsed "
                "【label】value exactly matching a reference line.</p>")
    hdr = "".join(f"<th>p{p} chars</th><th>p{p} tokens</th>" for p in pages)
    body.append(f'<div class="scroll"><table><tr><th>Engine · variant</th>{hdr}'
                "<th>Fields correct</th><th>Missed tokens</th></tr>")
    for b in sorted(board, key=lambda b: -b["ok"]):
        cells = "".join(
            f'<td class="num">{pct(s.accuracy if s else None)}</td><td class="num">{pct(rec)}</td>'
            for s, rec, _ in b["per"])
        missed = "; ".join(f"p{p}: {'、'.join(m)}" for p, (_, _, m) in zip(pages, b["per"]) if m)
        best = ' class="num best"' if b["ok"] == best_fields else ' class="num"'
        body.append(f"<tr><td>{esc(b['name'])}</td>{cells}"
                    f"<td{best}>{b['ok']}/{b['fields']}</td><td>{esc(missed) or '–'}</td></tr>")
    body.append("</table></div>")

    # 2. field matrix
    body.append('<h2 id="fields">Fields, all engines</h2>')
    body.append('<p class="note">Green: the parsed field matches the reference exactly. '
                "Red: it does not — compare the value against its neighbours. Grey text under "
                "a value is its English or Gregorian date; amber text is a review flag from "
                "<code>koseki/checks.py</code>. A blank cell means that engine's output produced "
                "no such field.</p>")
    table: dict[tuple, dict[str, tier1.Field]] = {}
    groups: dict[tuple, str] = {}
    order: list[tuple] = []
    for b in sorted(board, key=lambda b: -b["ok"]):
        for c in b["certs"]:
            for k, g, f in field_rows(c):
                if k not in table:
                    table[k], groups[k] = {}, g
                    order.append(k)
                table[k][b["name"]] = f
    ranked = [b["name"] for b in sorted(board, key=lambda b: -b["ok"])]
    body.append('<div class="scroll"><table><tr><th>Field</th>'
                + "".join(f"<th>{esc(n)}</th>" for n in ranked) + "</tr>")
    last_group = None
    for k in order:
        if groups[k] != last_group:
            last_group = groups[k]
            body.append(f'<tr class="group"><td colspan="{len(ranked) + 1}">{esc(last_group)}</td></tr>')
        label = k[2].replace("›", " › ")
        row = [f'<td class="label">【{esc(label)}】</td>']
        for n in ranked:
            f = table[k].get(n)
            if f is None:
                row.append('<td class="missing">—</td>')
                continue
            good = correct(f, truth)
            en = f.date or f.value_en or f.label_en or ""
            extra = f'<span class="en">{esc(en)}</span>' if en else ""
            if f.corrected_from:
                extra += f'<span class="en">OCR fixed from {esc(f.corrected_from)}</span>'
            extra += "".join(f'<span class="flag">⚑ {esc(r)}</span>' for r in f.review)
            mark = '<span class="ok">✓</span>' if good else '<span class="bad">✗</span>'
            row.append(f'<td class="{"cell-ok" if good else "cell-bad"}">{mark} '
                       f'{esc(f.value) or "<i>(empty)</i>"}{extra}</td>')
        body.append("<tr>" + "".join(row) + "</tr>")
    body.append("</table></div>")

    # 3. raw reads
    body.append('<h2 id="reads">Raw reads</h2>')
    body.append('<p class="note">Each engine\'s page text in reading order, next to the reference, '
                "whitespace and full-width forms normalised. <del>Red</del> is in the reference "
                "but not the read; <ins>green</ins> is in the read but not the reference.</p>")
    for p in pages:
        ref = load_truth(TRUTH, f"p-{p:02d}") or ""
        body.append(f"<h3>Page {p}</h3>")
        for b in sorted(board, key=lambda b: -b["ok"]):
            s, rec, _ = b["per"][pages.index(p)]
            body.append(f"<details><summary>{esc(b['name'])} — chars {pct(s.accuracy if s else None)}, "
                        f"tokens {pct(rec)}</summary>"
                        + page_diff(ref, ordered_text(b["by_page"].get(p, []))) + "</details>")

    DEST.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Tier 1 OCR Comparison</title><style>{CSS}</style></head>"
        f"<body><main>{''.join(body)}</main></body></html>", encoding="utf-8")
    print(f"{len(names)} runs -> {DEST}")


if __name__ == "__main__":
    main()
