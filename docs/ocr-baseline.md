# OCR baseline — Takagi Koseki

Measured 2026-08-26 on the 18-page Takagi register, CPU-only, Apple Silicon.
Raw numbers: `out/bench/results_sorted.txt`. Reproduce with `make bench`.

## What the document actually is

18 pages, five certificate sets, all issued by うきは市 on 2024-01-22:

| Pages | 発行番号 | Type | Script |
|---|---|---|---|
| 1–3 | 00226304 | 全部事項証明 (current computerised koseki) | modern print, horizontal |
| 4–5 | 00156056 | 改製原戸籍 | brush, vertical, Shōwa |
| 6–9 | 00156057 | 除籍 | brush, vertical |
| 10–15 | 00156058 | 除籍 | brush, vertical, Meiji/Taishō, dense |
| 16–18 | 00156061 | 除籍 | brush, vertical |

Two things about this corpus differ from the assumptions in the handoff, and
both matter:

**It is not kuzushiji.** The handwriting is upright semi-formal brush script
with daiji numerals, not connected cursive. KuroNet and a fine-tuned TrOCR are
not what this document needs. The V2 plan should be re-scoped against real
pages before any kuzushiji work is budgeted.

**The scans are certified copies on security paper.** Every page carries a cyan
gradient, an orange city mascot, tiled pale "うきはし" text, and a grey
copy-evident ghost pattern. That background — not the handwriting — is the
first thing that breaks OCR. Adobe Acrobat's own text layer, already embedded
in the PDF, is unusable garbage.

Scans are ~200dpi in the PDF, rendered here at 300dpi.

## Headline results

Accuracy = 1 − CER, after lines are put in reading order. Token recall = share
of known-correct names/dates/places found anywhere in the output.

| Tier | Best engine | Result |
|---|---|---|
| p1 printed | PaddleOCR (PP-OCRv6) | **93.7%** char accuracy, 17/18 tokens |
| p1 printed | yomitoku | 84.6% char accuracy, **18/18 tokens** |
| p5 Shōwa brush | ndlocr-lite tiled, decolored | **73.7%** token recall |
| p12 Meiji brush | yomitoku, decolored | **76.5%** token recall |

PaddleOCR is excellent on print and collapses on brush (26–42% on p5). The
split-by-script ensemble in the handoff is the right architecture, and this is
the measurement that supports it.

## Three levers, measured

### 1. Reading order — the largest single win, and it is free

Every engine returns lines in detection order, which on a koseki is close to
meaningless. Sorting them into document order, using boxes the engines already
return:

| Engine (p1) | CER as returned | CER sorted |
|---|---|---|
| ndlocr-lite tiled | 0.815 | **0.095** |
| yomitoku | 0.933 | **0.154** |
| ndlocr-lite whole-page | 0.371 | **0.162** |
| PaddleOCR | 0.093 | 0.063 |

Same model, same characters, 8.6× the accuracy. This is why the harness reports
CER *and* an order-free bag-CER: for tiled ndlocr-lite the bag-CER was 0.101
throughout, correctly predicting that recognition was already fine.

Implemented in `koseki/ocr/base.py:reading_order`.

### 2. Tiling — the difference between working and not working

NDLkotenOCR-Lite's detector takes a fixed 1024×1024 input. A 300dpi register
spread is ~3500px wide, so whole-page inference shrinks ~45px brush characters
to ~13px and the detector stops firing.

| Page | Whole-page | Tiled | |
|---|---|---|---|
| p12 | 1 line, 6 chars, 0.000 recall | 30 lines, 612 chars, 0.588 recall | — |
| p5 | 9 lines, 0.263 recall | 37 lines, 0.737 recall | 2.8× |
| p1 | 35 lines, 0.833 recall | 51 lines, 0.889 recall | — |

Tiles must be *strips*, not squares: full-height for vertical text, full-width
for horizontal. A line that straddles a tile edge comes back as two fragments
with no way to rejoin them. Square tiles cost ~25% of the recovered characters.

Implemented in `koseki/ocr/tiled.py`.

### 3. Watermark removal — helps handwriting, mildly hurts print

The background is chromatic and the ink is not, so `max(B,G,R)` per pixel
erases the teal, the mascot and the gradient while leaving ink untouched. A
luminance conversion does not: it keeps the teal as mid-grey.

| Page | Original | Decolored |
|---|---|---|
| p12 yomitoku | 0.706 | **0.765** |
| p5 ndlocr-lite tiled/1200 | 0.632 | **0.737** |
| p1 PaddleOCR | **0.944** | 0.889 |

Apply it to the handwritten pages, not the printed ones.

## What did not work

**Binarisation hurts every engine.** Sauvola thresholding was tested as part of
the `deskewed` variant. Page 12's measured skew was 0.00°, so its deskewed runs
were binarisation-only — and every engine scored worse: ndlocr-lite tiled 0.588
→ 0.412, yomitoku 0.765 → 0.588. Modern detectors are trained on photographs,
not bitonal scans. Keep the greyscale.

**Cropping to a region hurts.** The page-5 name panel was cropped out on the
theory that isolating the names would help. Full page scored 0.737 token
recall; the crop of the same names scored 0.286. Run whole pages.

**ndlocr-lite's confidence is not calibrated.** On page 5 the four correctly
read given names (幸道, 恵美子, 美佐子, 道雄) all came back at 0.26–0.38 while
noise scored higher. Confidence tracks line length more than correctness, so it
cannot drive review triage as-is.

## The failure that matters most

On page 12, three engines were asked for six personal names.

| | 高木幸市 | 矢野平市 | 重太郎 | マサヲ | ミト | ムメノ |
|---|---|---|---|---|---|---|
| yomitoku | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| PaddleOCR | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| ndlocr-lite tiled | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ |

The kanji names are read. **The katakana names — which in a register of this
period are the women's names — are missed by every engine.** They are short,
visually simple, and use archaic kana (ヲ). Also consistently missed across
pages: 続柄, the birth-order field (長男 / 三女 / 二男), which is legally
significant for inheritance.

This is the "OCR hallucinating names" risk from the handoff, landing on a
specific, reproducible field. Any review UI must treat katakana names and
続柄 as mandatory-verify, not confidence-gated.

There are also systematic single-character substitutions worth a lexicon pass:
父 → 文/又 (every occurrence on page 5), 太 → 大, 五 → 丸.

## Recommended pipeline

```
render at 300dpi
  └─ decolor (max-channel) ......... handwritten pages only
      └─ orientation: landscape -> vertical, portrait -> horizontal
          ├─ printed  -> PaddleOCR (PP-OCRv6, lang=japan)
          └─ brush    -> ndlocr-lite, strip-tiled + yomitoku, then merge
              └─ reading_order()  <- do not skip
                  └─ daiji/era date parsing
```

No binarisation, no deskew below ~1°, no cropping.

Cost: 7–9s/page tiled ndlocr-lite, 55–60s/page yomitoku, 60–120s/page
PaddleOCR, all CPU-only on Apple Silicon.

## Not yet measured

**A vision model as the OCR engine.** While preparing ground truth for this
benchmark, Claude read names, birth orders and daiji dates off 1400px JPEGs of
pages 5 and 12 accurately enough to cross-validate against the printed koseki —
better than any engine here managed. The adapter is written
(`koseki/ocr/vlm_engine.py`, `run_bench.py --vlm`) but no API key was set, so
it has no row in the table. It returns no bounding boxes, so it cannot replace
the detector, and its errors are fluent rather than garbled, which makes the
name-hallucination risk worse rather than better. It should be measured before
any fine-tuning is budgeted.

**Everything downstream.** Translation, entity extraction, storage and the
review UI are unbuilt, deliberately.

## Caveats on these numbers

- Ground truth exists for pages 1 and 5 only. Page 1 is high-confidence modern
  print. Page 5's name panel cross-validates against page 1's printed restatement
  of the same four birth dates.
- Page 12 has no full transcription — its ~700 characters of dense Meiji brush
  under four 除籍 stamps need an expert. It is scored on token recall only, and
  that list mixes hard names with easy structural tokens (明治, 除籍), so 0.765
  overstates how well the page is actually read.
- Three of eighteen pages were scored. The other fifteen are unmeasured.
