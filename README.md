# koseki-reader

Reads Japanese family registers (戸籍) into text, starting with the Takagi
register: 18 scanned pages spanning Meiji to Reiwa. Pages 1-3 are a modern
computerised certificate (全部事項証明, "Tier 1"); pages 4-18 are brush
handwriting.

This branch starts simple: the printed pages become plain Japanese text, one
file per page, ready to be translated later. The handwritten pages are skipped
for now.

## Setup

Requires Homebrew (for poppler, which renders the PDF) and Python 3.11.9.

```bash
brew install poppler
pyenv install 3.11.9
make setup     # builds venv/ with PaddleOCR
```

## Usage

```bash
make text      # data/raw/takagi.pdf -> out/text/takagi/p-01.txt ... and all.txt
./venv/bin/python scripts/pdf_to_text.py path/to/other.pdf
make test
```

OCR is PaddleOCR with `box_thresh=0.5`, the best setting on the Tier 1
benchmark (74 of 75 fields exact). A page takes 1-2 minutes on CPU the first
time; results are cached in `out/text/ocr/`, so later runs take a second.
`out/` is gitignored: it holds personal data.

Each run prints the character accuracy of every page that has a reference
transcription in `data/truth/`. Currently: page 1 95.4%, page 2 97.1%,
page 3 95.3%.

Known errors in the output: 恵美子 is read as the old form 惠美子 on page 2, and
the 出 of 出生 is missed on page 3.

## Layout

    scripts/pdf_to_text.py   PDF -> per-page Japanese text
    koseki/ocr/              PaddleOCR adapter and the common Line/Result shape
    koseki/pdf.py            PDF -> 300dpi page images (pdftoppm)
    koseki/score.py          character accuracy against a reference
    koseki/lexicon.py        known OCR slips (プラジル -> ブラジル), toponyms, kin terms
    koseki/dates.py          era + daiji numerals -> Gregorian, for translation later
    data/truth/              reference transcriptions
    docs/ocr-baseline.md     the engine benchmark that chose PaddleOCR
    PROJECT_HANDOFF.md       the original design document

The earlier pipeline (field parser, review flags, a second OCR engine
cross-checking names, the engine benchmark) is on the `tier1-pipeline` branch.
