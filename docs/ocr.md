# Scanned PDFs (OCR)

Links: Docling https://docling-project.github.io/docling/ · Qwen models https://huggingface.co/Qwen ·
Alibaba Cloud Model Studio (hosted Qwen, OpenAI-compatible) https://www.alibabacloud.com/help/en/model-studio/

## What it does

A scanned contract is a picture of pages, with no text for the app to read. The app now:

1. finds the pages that hold an image but almost no text (a mixed document only pays for its scanned pages),
2. reads those pages with OCR,
3. adds the recognised text back into the PDF as an **invisible layer** at the right positions, and
4. runs the normal pipeline on it: extraction, quote grounding, evidence highlights, review queue, calculators.

The picture is untouched, and the original upload is kept under `uploads/originals/`. The contract keeps the id of the file you
uploaded. Nothing downstream needed to change, which is why a scan behaves like any other contract once it is read.

## Two readers, and why

| Engine | What it is | Where it runs |
|---|---|---|
| **Docling** | Open-source parser with its own layout and OCR. Good line positions | Needs PyTorch and downloaded models (several GB). Use your own machine or a large server, **not** a 512 MB host |
| **Qwen** (vision-language model) | Reads the page image through an OpenAI-compatible API | Anywhere: it is just an HTTPS call |

With **both** configured, every OCR'd page is read twice and compared:

- a page whose two readings are very different (similarity under 80 percent) sends **all** its values to review, and
- a **number** that one reader found and the other did not (6 vs 8, `2027` vs `2O27`) sends the values that quote it to review.
  Numbers are compared separately because one wrong digit barely changes a page score, and it is the most dangerous error.

With **one** engine there is nothing to compare, so every value read from a scan is marked for review (set
`OCR_REVIEW_UNVERIFIED=0` to switch that off). That is deliberate: grounding checks the quote against the OCR text, so a misread
digit in the OCR text would still "ground". Only a second reading, or a person, can catch it.

Every OCR'd page is named in the contract's warnings, and a review reason says why a value was flagged.

## Settings (server environment)

| Variable | Default | Meaning |
|---|---|---|
| `OCR_ENGINE` | `auto` | `auto` (Docling if installed, else Qwen), `docling`, `qwen`, or `none` |
| `OCR_VERIFY` | `1` | Use the other engine as a second reader when it is available |
| `QWEN_API_KEY` | | The provider's key (secret) |
| `QWEN_MODEL` | | A Qwen **vision** model name from your provider's model list |
| `QWEN_BASE_URL` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Any OpenAI-compatible endpoint (a local vLLM or Ollama on `http://localhost` also works) |
| `QWEN_BBOX_MODE` | `auto` | How the model reports line positions: `pixels` or `relative1000`. Set it once you know your model |
| `OCR_MAX_PAGES` | `40` | Scanned pages per document (cost and time cap) |
| `OCR_MAX_CALLS` | `300` | Qwen calls per server process (protects the key) |
| `OCR_DPI` | `200` | Resolution of the page image sent to the model |
| `OCR_AGREEMENT_MIN` | `0.80` | Similarity below which a page goes to review |
| `OCR_REVIEW_UNVERIFIED` | `1` | Send single-reader values to review |

## Set up on Render (Qwen)

1. Get a key for a hosted Qwen vision model (for example from Model Studio), and note the exact model name it lists.
2. In Render **Environment** add `QWEN_API_KEY`, `QWEN_MODEL`, and (only if you use a different provider) `QWEN_BASE_URL`.
3. Redeploy. `/api/health` should show `"ocr": {"enabled": true, "engine": "qwen", "verified": false}`.
4. Upload a scanned PDF. The status chip reads **Reading scanned pages…**, then **Extracted**.

## Set up Docling (your machine or a large server)

```bash
pip install -r requirements-ocr.txt
```

Docling downloads its models on first use, so the host needs internet access to Hugging Face. With both Docling and Qwen set up,
`OCR_ENGINE=auto` reads with Docling and uses Qwen as the second reader.

## Check your setup

```bash
python scripts/check_ocr.py            # builds a scan from a bundled sample, reads it, and reports
python scripts/check_ocr.py --pages 1  # cheaper
```

It prints PASS or FAIL for: an engine is available, the pages were read, the words were recovered, positions are usable, and (with
two readers) that they agree on the text and on every number. It never prints keys or page text.

## What is and is not verified

Verified by automated tests: page detection, the invisible text layer (pixels identical to the scan; highlight boxes land on the real
words), Qwen reply parsing and coordinate scaling, retries and key handling, the two-reader comparison including single-digit
errors, the upload to extraction flow, and **real OCR** (Tesseract behind a stand-in Qwen endpoint) over HTTP: on the bundled sample
6 pages were read in about 5 seconds, 14 of 15 values grounded and one partial, with correct highlights.
Docling's geometry conversion is tested against Docling's own classes.

**Not verified:** a run against a real Qwen model (no key or network here) and a full Docling OCR run (its models could not be
downloaded in the test environment). `scripts/check_ocr.py` is how you confirm those on your side.

## Limits

- English contracts. Arabic text in a scan needs a different font for the invisible layer and has not been built.
- Handwriting, stamps over text, skewed or very low-resolution scans reduce accuracy. Review flags exist for this reason.
- A model reply that gives no usable positions still makes the text searchable, but highlights on that page are approximate
  (named in the warnings).
- Cost: one Qwen call per scanned page (and a second reader doubles the reading effort). `OCR_MAX_PAGES` and `OCR_MAX_CALLS` cap it.
- Page images are sent to the OCR provider. For confidential contracts use a provider you are permitted to send them to, or a
  self-hosted Qwen.
