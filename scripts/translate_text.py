"""Translate the per-page Japanese text from pdf_to_text.py into English with an OpenAI model.

    ./venv/bin/python scripts/translate_text.py                  # out/text/takagi/
    ./venv/bin/python scripts/translate_text.py out/text/other
    ./venv/bin/python scripts/translate_text.py --dry-run        # show the prompt, no API call
    ./venv/bin/python scripts/translate_text.py --force          # redo pages already translated
    ./venv/bin/python scripts/translate_text.py --model gpt-6-sol

Needs an OpenAI API key: OPENAI_API_KEY=... in .env at the repo root, or exported
in the shell. The model defaults to $OPENAI_MODEL, else MODEL below.

One request per page. The model returns every input line paired with its
English, so the output lines up with the Japanese one for one, plus notes on
anything it could not be sure of (a name reading, a character that looks like
an OCR slip). Writes, next to each p-NN.txt:

    p-NN.en.txt   the English, one line per Japanese line
    p-NN.en.md    Japanese and English side by side, then the notes

A page that already has p-NN.en.txt is skipped unless --force, since each
call costs money.

Privacy: the page text -- names, birth dates, addresses -- is sent to the
OpenAI API.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from koseki.lexicon import EVENTS_EN, LABELS_EN, TOPONYMS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Variables already set in the shell win over .env.
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-astra")

# The fixed vocabulary, so every page uses the same English for the same term.
GLOSSARY = "\n".join(
    [f"【{ja}】 = {en}" for ja, en in LABELS_EN.items()]
    + [f"{ja} = {en}" for ja, en in EVENTS_EN.items()]
    + [f"{ja} = {en}" for ja, en in TOPONYMS.items()]
)

SYSTEM = f"""You translate Japanese family registers (戸籍, koseki) into English \
for a family researching its history. The text you get is one page of a \
computerised full-record certificate (全部事項証明), read by OCR, one printed \
row per line.

Rules:
- Translate every input line into exactly one output line, in the same order. \
Copy the Japanese line unchanged into "ja". Never merge, split, drop or reorder lines.
- A line can hold several items side by side, separated by two spaces \
(a section label, then a 【field】). Keep that shape in the English.
- Write 【label】 fields as "Label: value".
- Convert every Japanese era date to the Western calendar, written like \
"29 November 1930". 西暦 dates are already Western.
- Names: write katakana names in Hepburn romanisation (タカギ -> Takagi). \
The registry does not record how kanji names are read, so for a kanji name \
give the most likely reading followed by the kanji in brackets, e.g. \
"Takagi Emiko (高木恵美子)", and add a note that the reading is unconfirmed. \
Keep family name first, as the register does.
- Places: use the glossary for Brazilian places. Romanise Japanese places \
(福岡県 -> Fukuoka Prefecture) and keep lot numbers (352番地2 -> 352-2).
- Keep the legal meaning exact. Where a standard phrase has an established \
English rendering, use it; do not paraphrase.
- The text comes from OCR and may contain misread characters. Translate what \
is written, but if a character looks misread (for example an old kanji form \
in a name, or a word that does not exist), add a note naming the line and \
what it probably should be. Do not silently correct names.
- Page furniture (page counter, issue number, 以下次頁, the city mascot \
caption) is translated like any other line.

Glossary (use these renderings):
{GLOSSARY}
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"ja": {"type": "string"}, "en": {"type": "string"}},
                "required": ["ja", "en"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["lines", "notes"],
    "additionalProperties": False,
}


def translate_page(client, text: str, model: str = MODEL) -> dict:
    response = client.responses.create(
        model=model,
        max_output_tokens=16000,
        instructions=SYSTEM,
        input=text,
        text={"format": {"type": "json_schema", "name": "translation", "schema": SCHEMA, "strict": True}},
    )
    if response.status == "incomplete":
        reason = getattr(response.incomplete_details, "reason", "unknown")
        raise RuntimeError(f"the reply was cut off ({reason}) (request {response._request_id})")
    content = [c for item in response.output if item.type == "message" for c in item.content]
    if any(c.type == "refusal" for c in content):
        raise RuntimeError(f"the model declined this page (request {response._request_id})")
    return json.loads(response.output_text)


def render_md(name: str, result: dict) -> str:
    out = [f"# {name}", "", "| Japanese | English |", "|---|---|"]
    for l in result["lines"]:
        ja, en = (l[k].replace("|", "\\|") for k in ("ja", "en"))
        out.append(f"| {ja} | {en} |")
    if result["notes"]:
        out += ["", "## Notes", ""] + [f"- {n}" for n in result["notes"]]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "out/text/takagi"),
                    help="a folder of p-NN.txt files from pdf_to_text.py")
    ap.add_argument("--force", action="store_true", help="translate pages that already have English")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt for the first page and stop")
    ap.add_argument("--model", default=MODEL, help=f"OpenAI model id (default {MODEL})")
    args = ap.parse_args()

    pages = sorted(p for p in Path(args.folder).glob("p-[0-9][0-9].txt"))
    if not pages:
        sys.exit(f"no p-NN.txt files in {args.folder}; run scripts/pdf_to_text.py first")

    if args.dry_run:
        print(f"model: {args.model}\n\n--- system ---\n{SYSTEM}\n--- user ({pages[0].name}) ---")
        print(pages[0].read_text(encoding="utf-8"))
        return

    import openai

    try:
        client = openai.OpenAI()
    except openai.OpenAIError:
        sys.exit("No API key. Put OPENAI_API_KEY=... in .env (or export it) and try again.")
    for page in pages:
        en_txt = page.with_suffix(".en.txt")
        if en_txt.exists() and not args.force:
            print(f"  {page.stem}: already translated, skipped (--force to redo)")
            continue
        text = page.read_text(encoding="utf-8").strip()
        try:
            result = translate_page(client, text, args.model)
        except openai.AuthenticationError:
            sys.exit("The API key was rejected. Check OPENAI_API_KEY and try again.")
        except openai.NotFoundError:
            sys.exit(f"Model {args.model!r} not found; pass --model or set OPENAI_MODEL.")
        except (openai.APIConnectionError, openai.RateLimitError, openai.APIStatusError,
                RuntimeError, json.JSONDecodeError) as e:
            print(f"  {page.stem}: failed, {e}")
            continue

        expected = text.splitlines()
        if [l["ja"] for l in result["lines"]] != expected:
            print(f"  {page.stem}: warning, the reply's lines do not match the input one for one "
                  f"({len(result['lines'])} vs {len(expected)}); check the side-by-side file")
        en_txt.write_text("\n".join(l["en"] for l in result["lines"]) + "\n", encoding="utf-8")
        md = page.with_suffix(".en.md")
        md.write_text(render_md(page.stem, result), encoding="utf-8")
        print(f"  {page.stem}: {len(result['lines'])} lines, {len(result['notes'])} note(s) -> {md.name}")


if __name__ == "__main__":
    main()
