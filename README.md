# koseki-reader

OCR and translation for Japanese family registers (戸籍), starting with the
Takagi register: 18 scanned pages spanning Meiji to Reiwa, part computerised
print and part brush handwriting.

This repository is currently at the **measurement** stage. The OCR baseline
exists and is scored; nothing downstream of it has been built yet, on purpose.

## Setup

Requires Homebrew, pyenv, and Python 3.11.9 built with compression support.

```bash
brew install poppler xz zlib bzip2 openssl@3 readline sqlite

# pyenv's default build silently omits _lzma, which yomitoku needs at import.
export LDFLAGS="-L/opt/homebrew/opt/xz/lib -L/opt/homebrew/opt/zlib/lib -L/opt/homebrew/opt/bzip2/lib -L/opt/homebrew/opt/openssl@3/lib -L/opt/homebrew/opt/readline/lib -L/opt/homebrew/opt/sqlite/lib"
export CPPFLAGS="-I/opt/homebrew/opt/xz/include -I/opt/homebrew/opt/zlib/include -I/opt/homebrew/opt/bzip2/include -I/opt/homebrew/opt/openssl@3/include -I/opt/homebrew/opt/readline/include -I/opt/homebrew/opt/sqlite/include"
pyenv install --force 3.11.9

make setup     # builds venv/ plus venvs/ndl and venvs/yomitoku
make pages     # renders the PDF to data/pages/*.png at 300dpi
```

### Why three virtualenvs

`ndlocr-lite` hard-pins (`==`) numpy, opencv, PyYAML and networkx to versions
that PaddleOCR and yomitoku will not accept. Rather than fight the resolver,
each engine gets its own environment and the adapters shell out to it. One
process spawn per page is cheap next to the OCR itself, and the alternative is
an install that breaks whenever any of the three is upgraded.

    venv/            orchestration, preprocessing, PaddleOCR
    venvs/ndl/       ndlocr-lite  (NDLkotenOCR-Lite)
    venvs/yomitoku/  yomitoku

## Usage

```bash
# OCR one page, print it in reading order, draw the detected regions
./venv/bin/python scripts/ocr_page.py data/pages/p-05.png --viz out/p05_boxes.png

# the full engine x preprocessing benchmark
./venv/bin/python scripts/run_bench.py          # add --vlm to include the vision model

make test
```

`--viz` is the quickest way to tell a detection failure from a recognition
failure. If the boxes miss half the page, a better recogniser will not help.

## Layout

    koseki/preprocess.py   watermark removal, binarisation, deskew
    koseki/ocr/            one adapter per engine, common Line/Result shape
    koseki/ocr/tiled.py    tiling, without which the NDL detector sees nothing
    koseki/score.py        CER, order-free bag-CER, and key-token recall
    koseki/dates.py        era + daiji numerals -> Gregorian
    koseki/bench.py        the harness
    data/truth/            reference transcriptions and key-token lists
    docs/ocr-baseline.md   what the numbers came out as, and what they mean

## Ground truth

`data/truth/` holds the references the benchmark scores against. Each file
records how confident its transcription is and how it was checked. The useful
accident of this document is that pages 1-3 are a modern computerised koseki
restating the same people and dates that pages 4-18 record in brush and daiji
numerals, so much of the handwritten ground truth cross-validates against
printed text in the same PDF.

Page 12 deliberately has **no** full transcription -- see the note in
`data/truth/tokens/p-12.txt`.

## Status

Done: environment, preprocessing, four engine adapters, scoring, the baseline
benchmark, era/daiji date parsing.

Not started, and blocked on the baseline: translation, entity extraction,
storage, review UI.
