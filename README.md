# SPA Intelligence

Streamlit demo that analyses property Sale and Purchase Agreements (SPAs): upload a PDF and get key terms
(each with page number and exact source quote), a deterministic delay-penalty simulator, a cash-flow view,
a buyer Q&A assistant that answers only from the extracted contract, and an accuracy table.

> **Decision support, not legal advice.** This banner appears on every page of the app.

## Design rules

1. The LLM only extracts and phrases. All arithmetic (penalties, cash-flow, percentage sums) is plain, unit-tested Python.
2. Every extracted value has `source_page` and `source_quote`; `null` when the document does not state it. Quotes are verified against the PDF text after extraction and a warning is raised if one is not found.
3. No fake data in the UI: every number is extracted or computed. With no API key and no cache, the app shows an error instead.
4. Jurisdiction rules live in `rules/uae.yaml` (day-count, scenarios, the "at risk" keyword definition, the legal-advice refusal patterns).
5. The buyer agent reads only the loaded contract's extracted JSON through four tools, cites the clause, and refuses legal-advice questions with "please contact the legal team".

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your ANTHROPIC_API_KEY in .env (or export it)
python scripts/generate_samples.py   # regenerates samples/*.pdf and ground_truth.json
```

## Run

```bash
streamlit run app/main.py        # the app
pytest                           # unit tests (penalty, cash-flow, schema, agent, eval, UI smoke)
python eval/run_eval.py          # extraction accuracy vs ground_truth.json -> eval/results.json (needs API key)
python scripts/agent_smoke.py    # 6 live buyer-agent questions (needs API key)
```

Change the model in one place: `MODEL` in `app/config.py`. Extractions are cached in `data/cache/<sha256>.json`
(a cache entry is ignored when the model differs; set `SPA_CACHE_DIR` to relocate the cache).

## Architecture

```
PDF --(Claude document block + forced tool call)--> ExtractionOutput (pydantic, retry once on invalid)
    --> postprocess (Python): quote check/page fix, % sum, missing-clause warnings --> ContractData --> cache
ContractData --> penalty.py (pure) --> cashflow.py (pure) --> agent.py (tools over the JSON) --> main.py (Streamlit)
rules/uae.yaml feeds penalty, cashflow and agent.   eval/run_eval.py scores extraction vs ground_truth.json
```

| File | Role |
|---|---|
| `app/schema.py` | `Sourced`, `Milestone`, `ContractData`; a non-null value must carry page and quote |
| `app/extract.py` | PDF to `ContractData`, caching, deterministic checks and warnings |
| `app/penalty.py` | `delay_penalty`, `delay_penalty_fixed_per_sqft`, `simulate` (rates and caps in percent; accrual only after grace; half-up rounding to 2 dp) |
| `app/cashflow.py` | period schedule, "at risk" definition (see its docstring and `rules/uae.yaml`), next payment |
| `app/agent.py` | tool-calling buyer agent, deterministic legal-advice gate, prompt-injection defences |
| `scripts/generate_samples.py` | builds the 3 synthetic SPAs and `ground_truth.json` from one dict |

Samples: **A** five 20% milestones, 6% p.a., 60-day grace, 10% cap. **B** seven construction-linked milestones, AED 7.00 per sq ft per year, 90-day grace, no cap. **C** plan sums to 95% (deliberate error) and has no cancellation clause.

## Limitations

- English only; synthetic, cleanly formatted PDFs. Scanned or messy real-world SPAs are untested.
- Delay compensation is modelled on the purchase price (percent basis) or saleable area (fixed basis), as the samples state it. Real contracts often compute it on amounts paid; `basis = other` is flagged as not simulatable rather than guessed.
- "At risk" is keyword-based on milestone name/trigger text and is a heuristic. Penalty exposure is compensation the buyer could be owed; it is summed with linked amounts per the product definition, but both parts are always shown separately.
- Milestones with no stated date are listed, not placed on the timeline; no dates are invented.
- The legal-advice gate is regex plus prompt based: it can over-refuse (any question containing "cancel") and may miss novel phrasings.
- Quote verification is a substring check on PyMuPDF text; it proves the text exists in the PDF, not that it supports the value.
- No auth, database or multi-user state.

## Roadmap

Document Intelligence / Docling swap behind `extract.py` (same `ContractData` interface) · cross-document check (SPA vs. offer letter / payment receipts) · Arabic-English bilingual check · rulebook check against `rules/*.yaml` (RERA-style) · WhatsApp channel for the buyer assistant · a real, larger evaluation set with labelled real contracts.
