# Project Handoff: Japanese Koseki OCR & Translation System

**Revision 2** — rewritten after analysis of a real koseki bundle. Revision 1 contained significant incorrect assumptions; see Section 2.

**Purpose:** Bring a new AI agent or developer fully up to speed on this project's goal, the actual nature of the documents, decisions made, and next steps. Read Section 2 before proposing anything.

---

## 1. Project Goal

Build a software application that reads, translates, and structures Japanese **koseki (戸籍)** — family registry records — from scanned certified copies issued by Japanese municipal governments.

### Target users

Genealogists, immigration attorneys, estate/inheritance lawyers, and family-history researchers. A particularly strong use case: **descendants of Japanese emigrants** (Brazil, Peru, Hawaii, US mainland) tracing lineage back to Japan. The sample document analyzed for this project is exactly that case — a Fukuoka family that emigrated to São Paulo State, Brazil in the 1920s–30s.

### Desired outcome

Given a scanned koseki bundle, produce:
1. Accurate Japanese transcription
2. English translation preserving names, dates, places, and legal terminology
3. Structured data: persons, dates, relationships, addresses, registry events
4. Human review interface for correction
5. Export: annotated PDF, JSON, GEDCOM

---

## 2. CRITICAL CORRECTIONS TO REVISION 1

Revision 1 of this plan was written before seeing a real document. It was wrong in several consequential ways. **Do not carry forward assumptions from any earlier version of this plan.**

| Revision 1 assumed | Reality |
|---|---|
| The documents are kuzushiji (くずし字) — Edo-period literary cursive | **There is no kuzushiji.** The handwriting is Meiji–Shōwa *clerical brush hand* (楷書/行書) — regular to semi-cursive, written legibly by government clerks in ruled grids because these are legal instruments |
| Fine-tune on KMNIST / CODH / KuroNet | **Wrong training data.** Those are pre-modern woodblock and literary manuscript corpora. Correct targets are modern handwritten Japanese corpora (ETL Character Database, Kondate, NDL handwritten sets) and synthetic vertical-text generation |
| Primary challenge is character shape | **Primary challenge is a modern anti-forgery security watermark** printed under the text on certified copies, plus halftone/moiré from photocopy-of-photocopy reproduction |
| One document type | **Three distinct document tiers** with wildly different difficulty — one of which is trivially easy |
| Era range: Meiji (1868) onward | **Late Edo appears.** The sample contains 天保九年 (Tenpō 9 = 1838) and 慶応三年 (Keiō 3 = 1867). Era tables must cover Edo periods |
| Arabic/standard kanji numerals | **Daiji (大字) formal numerals throughout**: 壱弐参 and 拾, plus 廿 for 20. `明治参拾弐年` = Meiji 32 |
| Cross-document linking is a V3 feature | **It is core to the use case.** A single request returns a bundle of 3–6 linked registries spanning generations, cross-referencing each other |
| Kyūjitai normalization is a major workstream | Minor. Present (髙 vs 高, 舊字 in a few places) but not a bottleneck |

### The most important single finding

**The modern computerized koseki in the bundle contains the same people, dates, and relationships as the handwritten ones — in clean machine-printed form.** This is free ground truth. See Section 8.

---

## 3. Document Taxonomy (learn this before anything else)

A koseki request to a Japanese municipality returns a **bundle** of several document types. The sample bundle (Fukuoka-ken Ukiha-shi, issued 令和6年1月22日 / 2024-01-22) contained 18 pages across four types:

### Tier 1 — 全部事項証明 (zenbu jikō shōmei) — "Full Record Certification"
**Difficulty: TRIVIAL. This is machine-printed digital output.**

- Post-computerization format (the sample registry was computerized 平成13年2月3日 / 2001)
- Horizontal machine print, modern typeface
- **Explicit field labels in 【brackets】**: 【名】【生年月日】【父】【母】【続柄】【出生日】【出生地】【届出日】【届出人】
- Essentially a structured form. Once OCR'd, parsing is regex, not NLP
- Empirical proof: the uploaded PDF's own embedded text layer extracted these pages nearly perfectly, while producing pure noise on every handwritten page

### Tier 2 — 改製原戸籍 (kaisei genkoseki) — "Pre-revision Original Registry"
**Difficulty: MODERATE.**

- The paper registry that existed before computerization
- Vertical brush handwriting in a pre-printed ruled grid
- Shōwa-era clerical hand — regular script for names, semi-cursive for annotation columns
- Names sit in dedicated boxes at the bottom of each column (highly regular position — grid-based segmentation is very viable)
- Annotation text runs top-to-bottom in narrow columns

### Tier 3 — 除籍謄本 (jokoseki tōhon) — "Removed/Closed Registry"
**Difficulty: MODERATE to HARD.**

- Registries closed when all members died or transferred out
- Taishō and Meiji-era handwriting — denser, more cursive annotation columns
- Heavy use of red 除籍 stamps and diagonal ✗ strike-throughs over names
- More archaic bureaucratic phrasing

### Tier 4 — Oldest Meiji registries
**Difficulty: HARD.**

- The sample's oldest page lists a 戸主 born 天保九年 (1838)
- Noticeably more cursive brush hand
- Faintest reproduction quality
- Still not kuzushiji — but the gap between this and Tier 1 is enormous

**Architectural implication:** document type classification must be step one of the pipeline, and the tiers should be routed to different OCR strategies. Building for Tier 1 alone delivers real product value immediately.

---

## 4. Actual Technical Challenges Observed

### 4.1 Security watermark — the #1 preprocessing problem

Modern certified copies are printed on anti-forgery stock. The sample shows:
- A cyan/teal background pattern of repeated micro-text (the municipality name, うきは, tiled across the entire page)
- Municipal mascot graphics in orange in the corners
- Large ghosted kanji watermarks
- Halftone dot screen from the reproduction process

This background destroys naive OCR. It is, however, **chromatically separable** — the watermark is cyan/teal, the ink is black. HSV or LAB color-space separation plus a frequency-domain notch filter for the halftone screen should recover clean text. This is the single highest-leverage preprocessing work in the project.

### 4.2 Daiji (大字) formal numerals

Legal documents use anti-tampering numerals. Any naive date parser will fail.

| Daiji | Value | | Daiji | Value |
|---|---|---|---|---|
| 壱 | 1 | | 七 | 7 |
| 弐 / 貳 | 2 | | 八 | 8 |
| 参 / 參 | 3 | | 九 | 9 |
| 四 | 4 | | 拾 | 10 |
| 五 | 5 | | 廿 | 20 |
| 六 | 6 | | 卅 | 30 |

Composition: `参拾弐` = 32, `拾九` = 19, `弐拾五` = 25, `四拾九` = 49. Also `元年` = year 1.

Observed examples: `明治参拾弐年三月拾五日`, `昭和参拾参年五月拾九日`, `慶応三年十月廿日`, `大正拾四年四月`.

### 4.3 Era conversion — must include Edo

```python
ERA_OFFSETS = {
    # Edo — required, the sample contains these
    "天保": 1829,  # Tenpō  1830–1844
    "弘化": 1843,  # Kōka   1844–1848
    "嘉永": 1847,  # Kaei   1848–1854
    "安政": 1853,  # Ansei  1854–1860
    "万延": 1859,  # Man'en 1860–1861
    "文久": 1860,  # Bunkyū 1861–1864
    "元治": 1863,  # Genji  1864–1865
    "慶応": 1864,  # Keiō   1865–1868
    # Modern
    "明治": 1867,  # Meiji  1868–1912
    "大正": 1911,  # Taishō 1912–1926
    "昭和": 1925,  # Shōwa  1926–1989
    "平成": 1988,  # Heisei 1989–2019
    "令和": 2018,  # Reiwa  2019–
}
```

**Gotcha:** transition years overlap. 明治45年 and 大正元年 are both 1912; 昭和64年 and 平成元年 are both 1989. Validate month against the transition date.

### 4.4 Japanese-Brazilian emigration vocabulary

The sample family emigrated to São Paulo State. This introduces a whole domain of place names that no general translator handles:

**Kanji abbreviations for foreign countries/regions** — these are genuine traps:
- `伯国` = Brazil (伯 abbreviates 伯剌西爾)
- `聖州` = São Paulo State (聖 abbreviates サンパウロ / São = "saint")
- `ブラジル国` also appears — same thing, different orthography, in the same bundle

**Katakana transliterations of Brazilian toponyms** observed:
- `サンパウロ州ノロエステ線` = Noroeste Line, São Paulo State (a railway line along which Japanese colonies were settled)
- `ビリグイ駅` = Birigui
- `バルパライゾ駅` = Valparaíso
- `ミランドポリス駅` = Mirandópolis
- `アラサツバ` = Araçatuba
- `ロンドリーナ市` = Londrina
- `在バウルー領事` = Consul at Bauru
- `在サンパウロ総領事` = Consul General, São Paulo

A Brazilian-Japanese toponym gazetteer is a required build. Machine translation will mangle all of these. The Noroeste railway station names in particular are the backbone of Japanese-Brazilian settlement geography and are highly diagnostic for genealogical research.

### 4.5 Name orthography

- **Women's given names are written in katakana** in older registries: ムメノ, マサヲ, タケ, ミト, フタミ, ミヨコ, タケ. Men's names are in kanji.
- **Historical kana orthography**: `マサヲ` not `マサオ` — the ヲ/ヱ forms appear in given names and must not be "corrected" during normalization, because the registry spelling is the legal spelling
- Surname variant: `髙木` (extended form) vs `高木` appear in the same bundle for the same family

### 4.6 Structural markers

- **Diagonal ✗ through a name box** = person removed from this registry (death, marriage out, transfer). Visually unmistakable, easily detected, semantically critical
- **Red 除籍 stamps** — angled rectangular stamps overlapping annotation text
- **Red clerk seals** (田中, municipal 市長印) overlapping text at column tops
- **`以下余白`** = "remainder blank" — end-of-record marker
- **`以下次頁`** = "continued on next page"
- **Page notation `(3の1)`** = page 1 of 3

### 4.7 Address normalization across time

The same physical location appears under different administrative names as municipalities merged:
- `福岡県浮羽郡椿子村大字朝田` (Meiji)
- `福岡県浮羽郡浮羽町大字西隈上352番地2` (mid-century)
- `福岡県うきは市浮羽町西隈上352番地2` (modern, post-2005 merger)

The registry itself documents these transitions (`【更正事由】平成17年3月20日行政区画変更市となった上、土地の名称変更`). A place-name resolution layer keyed to administrative reorganization history is needed for cross-document person matching.

### 4.8 Registry event vocabulary

Observed in the sample — this is the working vocabulary list:

| Term | Meaning |
|---|---|
| 戸主 / 前戸主 | Head of household / previous head |
| 出生 | Birth |
| 婚姻 | Marriage |
| 死亡 | Death |
| 入籍 / 除籍 | Entry into / removal from registry |
| 転籍 | Transfer of registry to new location |
| 改製 | Registry revision (format change by law) |
| 消除 | Cancellation |
| 届出 / 届出人 | Filing / filer |
| 受附 (受付) | Received by authority |
| 送付を受けた日 | Date forwarded document received |
| 証書提出 | Certificate submission (used for foreign marriages) |
| 特記事項 | Special notes |
| 縁組 | Adoption |

Relationship terms (続柄) observed: 長男, 二男/弐男, 三男, 四男, 五男, 六男, 七男, 長女, 二女, 三女, 四女, 五女, 妻, 母, 父, 孫, 婦, 姪, 弟妻.

Note `二男` and `弐男` both appear — same meaning, different orthography.

---

## 5. Revised Architecture

```
Upload (PDF/image bundle)
   ↓
[1] Page splitting + document type classification
      → Tier 1 (machine print) | Tier 2/3/4 (handwritten)
   ↓
[2] Preprocessing (Tier-dependent)
      Tier 1: deskew, light denoise
      Tier 2-4: WATERMARK REMOVAL (color separation + halftone notch filter),
                deskew, seal/stamp isolation, contrast normalization
   ↓
[3] Layout analysis
      Tier 1: field-label detection 【...】
      Tier 2-4: grid/column detection, name-box localization,
                ✗-strike detection, stamp region masking
   ↓
[4] OCR (Tier-dependent)
      Tier 1: PaddleOCR v5 / Google Vision → near-perfect
      Tier 2-4: name boxes → handwriting model (high confidence, small vocab)
                annotation columns → handwriting model + LLM vision assist
   ↓
[5] Normalization
      Daiji → integers | Era → Gregorian | Address canonicalization
      Kyūjitai → shinjitai (preserving registry spelling in a separate field)
   ↓
[6] Entity extraction → persons, events, relationships, places
   ↓
[7] Cross-document reconciliation (bundle-level)
      Match same person across Tier 1 ↔ Tier 2/3/4
   ↓
[8] Translation (two-stage + gazetteer protection)
   ↓
[9] Human review (confidence-routed)
   ↓
[10] Output: annotated PDF / JSON / GEDCOM
```

---

## 6. Revised OCR Strategy

### Tier 1 (machine print)
PaddleOCR v5 or Google Vision. Expect >97%. **PaddleOCR v5 offers the best accuracy/latency tradeoff among open-source options** and supports Japanese. No fine-tuning needed. This tier is essentially solved.

### Tier 2–4 (handwritten)
Two separate sub-problems with very different characteristics:

**(a) Name boxes** — small, fixed-position, constrained vocabulary (surnames, given names, katakana). High value, high tractability. Grid position is known from layout analysis. This is where to focus first.

**(b) Annotation columns** — long vertical runs of semi-cursive bureaucratic prose. Harder, but **highly formulaic** — the same phrase templates recur (`昭和X年X月X日 ... 届出同年X月X日受附入籍`). Template-constrained decoding should substantially outperform free recognition.

**Model candidates for handwriting:**
- TrOCR fine-tuned on modern Japanese handwriting (ETL Character Database from AIST; Kondate on-line handwriting database)
- Synthetic vertical-text generation for augmentation — the llm-jp `eval_vertical_ja` work released synthetic vertical Japanese OCR data and showed that training on it improves models that previously could not handle vertical writing
- Vision LLMs as an assist, with a caveat: current MLLMs perform measurably worse on vertically written Japanese than horizontal, and their accuracy degrades below roughly 150 ppi while matching conventional OCR at 300 ppi. **Scan at 300+ DPI and consider rotating vertical columns to horizontal before feeding a VLM.**

### Do NOT use
KMNIST, KuroNet, CODH classical-books datasets. These target pre-modern literary cursive from woodblock books — a different script register entirely. Using them would be actively counterproductive.

---

## 7. Translation Strategy (revised)

The two-stage approach (classical→modern→English) still holds for Tier 3/4 annotation prose, but is **unnecessary for Tier 1**, which is already modern Japanese.

Revised flow:
1. **Protect entities before translation**: names, daiji dates, katakana toponyms, registry numbers → placeholder tokens
2. **Tier 1**: direct modern JA→EN (DeepL)
3. **Tier 2–4**: LLM normalization of archaic bureaucratic phrasing → DeepL
4. **Restore entities** using the gazetteer (Brazilian toponyms → Latin-script originals, not phonetic re-transliteration)
5. **Apply translation memory** for the fixed legal vocabulary in Section 4.8

Critical: `ビリグイ駅` must resolve to "Birigui Station", not "Biligui" or "Birigui Eki". Round-tripping katakana through MT loses the original Portuguese spelling.

---

## 8. Self-Bootstrapping Training Data — the key strategic insight

**The bundle contains its own ground truth.**

The Tier 1 computerized record lists the same individuals, birth dates, parents, and relationships as the Tier 2/3 handwritten records — because the computerized record was transcribed *from* them by a municipal clerk.

This enables:
- **Weak supervision**: OCR Tier 1 (easy, reliable) → use those names/dates as the candidate label set when recognizing the corresponding handwritten name boxes
- **Constrained decoding**: when reading a handwritten name box, restrict the output space to names already known from Tier 1
- **Automatic training pair generation**: (handwritten name box image crop, known correct text) — no manual annotation required
- **Validation signal**: disagreement between tiers flags either an OCR error or a genuine clerical discrepancy, both worth surfacing to the reviewer

Every koseki bundle a user uploads generates free labeled training data. This substantially de-risks the "no public koseki dataset exists" problem identified in Revision 1.

---

## 9. Revised Roadmap

### MVP (Months 1–3) — Tier 1 only
Ship a genuinely useful product on the easy document type.
- Upload, page split, document type classification
- PaddleOCR v5 on 全部事項証明 pages
- 【field】 parsing (regex — the format is rigid)
- Era + daiji date conversion
- Entity extraction: persons, dates, relationships, places
- Translation with entity protection + legal TM
- Review UI
- PDF + JSON export

Real users need modern koseki translated for immigration and inheritance filings today. This is shippable value, not a toy.
**Difficulty: Low–Medium.** Mostly integration and careful parsing.

### V2 (Months 4–8) — Tier 2 handwritten, name boxes
- Watermark removal pipeline (highest-leverage single piece of work)
- Grid/column layout detection, name-box localization
- ✗-strike and stamp detection
- Handwriting model for name boxes, bootstrapped from Tier 1 labels
- Cross-document person reconciliation within a bundle
- Brazilian/emigration toponym gazetteer
- Confidence-routed review with active learning
**Difficulty: Hard.**

### V3 (Months 9–15) — Tier 3/4 annotation prose, full lineage
- Template-constrained recognition of annotation columns
- Meiji/Edo-era handwriting
- Address resolution across administrative reorganizations
- Full family graph reconstruction across the bundle
- GEDCOM export, public API
**Difficulty: Very Hard.**

---

## 10. Risk Assessment (revised)

| Risk | Severity | Note |
|---|---|---|
| Watermark removal proves harder than expected | **High** | This gates all of V2. Prototype it before committing to the V2 timeline |
| Annotation-column prose accuracy plateaus | Medium | Mitigated by template constraints; V3 problem |
| Name hallucination | **Critical** | Mitigated substantially by Tier 1 constrained decoding. Never let the model free-generate a name |
| Toponym mistranslation | Medium | Gazetteer required; affects genealogical usefulness directly |
| Scan resolution below 150 DPI | Medium | Degrades both conventional OCR and VLM assist. Enforce a minimum on upload and warn users |
| **PII handling** | **High** | Koseki contain full names, birth dates, parentage, addresses for living people. Japanese PIPA and GDPR both apply. The sample document in this project contains real family data — handle accordingly, do not commit it to a public repo |
| Legal liability | High | Used for immigration and inheritance. Disclaim prominently: output requires expert human review for legal use |

---

## 11. Environment & Stack

**Machine:** Mac, Apple Silicon, no NVIDIA GPU, CPU inference locally. Shell is **bash** (`~/.bash_profile`). Homebrew at `/opt/homebrew`. Miniconda installed and initialized — decision made to use pyenv + venv and leave Conda untouched.

**Developer:** Experienced software developer, not an OCR/ML specialist. Explain ML concepts from first principles. Provide explicit copy-pasteable commands.

**Stack:**
- Python 3.11 (not 3.12 — PaddlePaddle compatibility)
- FastAPI + Celery + Redis
- PostgreSQL 16
- React + TypeScript + Vite, PDF.js, Konva.js
- PaddleOCR 3.x (PP-OCRv5), OpenCV, Pillow, pdf2image (+ `brew install poppler`)
- DeepL API, OpenAI/Anthropic API

```bash
# ~/.bash_profile
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

pyenv install 3.11.9 && pyenv global 3.11.9
mkdir koseki-ocr && cd koseki-ocr
python -m venv venv && source venv/bin/activate
pip install --upgrade pip
pip install paddlepaddle paddleocr opencv-python pillow pdf2image
brew install poppler
```

---

## 12. Immediate Next Steps

1. **Finish environment setup** (PaddleOCR importing successfully)
2. **Run PaddleOCR on the Tier 1 pages of the sample bundle** — establish that the easy path works end to end
3. **Build the 【field】 parser** — the modern format is rigid enough that this is mostly regex
4. **Build daiji + era date conversion with tests** — small, self-contained, high value, and needed by every tier
5. **Prototype watermark removal** on a Tier 2 page — HSV/LAB color separation first, then a frequency-domain notch filter for the halftone screen. Do this early: it determines whether the V2 timeline is realistic
6. **Walking skeleton**: single script, image → OCR → parse → translate → JSON
7. Only then: FastAPI/Celery wrapping, then review UI

---

## 13. Resources

**Tools**
- PaddleOCR: `https://github.com/PaddlePaddle/PaddleOCR`
- ndlocr-lite (CPU, ONNX): `https://github.com/ndl-lab/ndlocr-lite`
- yomitoku (Japanese document AI): `https://github.com/kotaro-kinoshita/yomitoku`
- kyujitai normalization: `https://github.com/marmooo/kyujitai`

**Datasets (correct ones for this problem)**
- ETL Character Database (AIST) — handwritten Japanese characters, collected 1973–1984
- Kondate — on-line handwritten Japanese mixed-object database
- llm-jp vertical Japanese OCR data + code: `https://github.com/llm-jp/eval_vertical_ja`
- CODH Modern Magazine dataset (Meiji printed, CC BY 4.0): `https://codh.rois.ac.jp/modern-magazine/dataset/`

**Papers**
- "Evaluating Multimodal Large Language Models on Vertically Written Japanese Text" — `https://arxiv.org/abs/2511.15059`
- "Context-Independent OCR with Multimodal LLMs: Effects of Image Resolution and Visual Complexity" — `https://arxiv.org/abs/2503.23667`
- TrOCR — `https://arxiv.org/abs/2109.10282`
- LayoutLMv3 — `https://arxiv.org/abs/2204.08387`

**Annotation tooling**
- eScriptorium: `https://escriptorium.inria.fr`

---

## 14. Guidance for the Receiving Agent

- **Do not propose kuzushiji models or datasets.** This is not kuzushiji. See Section 2.
- **Do not treat this as one OCR problem.** Tier 1 is solved; Tiers 2–4 are research. Conflating them produces bad plans.
- **Do not skip watermark removal.** It is the gating technical risk, not a preprocessing footnote.
- **Do not build a generic date parser.** Daiji numerals and Edo-era names are mandatory, not edge cases.
- **Do not let MT touch names, dates, or Brazilian toponyms** without placeholder protection.
- **Exploit the self-bootstrapping property** (Section 8) before proposing any manual annotation effort.
- **Explain ML concepts from first principles.** Strong developer, new to OCR/ML.
- **Apple Silicon, CPU-only.** No GPU assumptions for local work.
- **This sample contains real personal data.** Treat it as PII in any workflow, repo, or example.

---

*Revision 2 — prepared following analysis of a real 18-page koseki bundle (Fukuoka-ken Ukiha-shi, issued 2024).*
