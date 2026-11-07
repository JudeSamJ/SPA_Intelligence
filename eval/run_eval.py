"""Run extraction on all samples and score against ground_truth.json.

Scoring: exact match for numbers/dates/enums, normalised-string match for names/ids, and a
check that every quote appears verbatim (whitespace/case-normalised) in the PDF text.
Cached extractions are reused (free). Uncached files cost 1 LLM call each (2 on a retry), so the
script refuses to call the API unless you pass --yes.

    python eval/run_eval.py [--yes] [--no-cache] [--model NAME] [--engine NAME]

Documents come from eval/golden/<doc_id>/{doc.pdf,labels.json} (see eval/golden/README.md). Every run is saved to
eval/runs/<timestamp>.json with the model name and git commit, and compared with the previous run of the same engine.
"""
from __future__ import annotations

import json
import re
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.llm import LLMError  # noqa: E402
from app.extract import ExtractionError, extract_contract, load_cached, normalize_text, pdf_pages, quote_key  # noqa: E402

SCALAR_FIELDS = ["buyer", "unit_id", "price", "area_sqft", "handover_date", "grace_period_days",
                 "delay_rate", "delay_basis", "delay_cap"]
STRING_FIELDS = {"buyer", "unit_id"}


def _eq(field: str, got, want) -> bool:
    if want is None or got is None:
        return want is None and got is None
    if field in STRING_FIELDS:
        return normalize_text(str(got)) == normalize_text(str(want))
    if field == "handover_date":
        return str(got) == str(want)
    if field == "delay_basis":
        return got == want
    return float(got) == float(want)


def _quote_ok(pages_norm: list[str], quote: str | None) -> bool | None:
    """True/False if a quote exists; None if no quote to check."""
    if not quote:
        return None
    q = quote_key(quote)
    return any(q in p for p in pages_norm)


def compare(contract, truth: dict, pdf_bytes: bytes) -> dict:
    """Return {check_name: {"correct": bool, "quote_ok": bool|None}} for one contract."""
    pages_norm = [quote_key(p) for p in pdf_pages(pdf_bytes)]
    res: dict[str, dict] = {}
    for f in SCALAR_FIELDS:
        item = getattr(contract, f)
        res[f] = {"correct": _eq(f, item.value, truth[f]), "quote_ok": _quote_ok(pages_norm, item.source_quote)}

    plan, tplan = contract.payment_plan, truth["payment_plan"]
    plan_quotes = [_quote_ok(pages_norm, m.source_quote) for m in plan]
    qok = None if not plan_quotes else all(plan_quotes)
    res["payment_plan.count"] = {"correct": len(plan) == len(tplan), "quote_ok": qok}
    res["payment_plan.percents"] = {
        "correct": [m.percent for m in plan] == [m["percent"] for m in tplan], "quote_ok": None}
    res["payment_plan.dates"] = {
        "correct": [str(m.due_date) if m.due_date else None for m in plan] == [m["due_date"] for m in tplan],
        "quote_ok": None}
    res["payment_plan.triggers"] = {
        "correct": len(plan) == len(tplan) and all(
            normalize_text(m.trigger or "") == normalize_text(t["trigger"]) for m, t in zip(plan, tplan)),
        "quote_ok": None}

    want_cancel = truth["has_cancellation_clause"]
    cc = contract.cancellation_clause
    res["cancellation_clause.present"] = {
        "correct": (cc.value is not None) == want_cancel, "quote_ok": _quote_ok(pages_norm, cc.source_quote)}

    # Deterministic warnings must fire exactly when the truth warrants them.
    want_sum_warn = abs(sum(m["percent"] for m in tplan) - 100) > 0.01
    got_sum_warn = any("sum to" in w for w in contract.warnings)
    res["warning.percent_sum"] = {"correct": want_sum_warn == got_sum_warn, "quote_ok": None}
    got_cancel_warn = any("No cancellation clause" in w for w in contract.warnings)
    res["warning.missing_cancellation"] = {"correct": got_cancel_warn == (not want_cancel), "quote_ok": None}
    return res


def penalty_test_pass_rate() -> dict:
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/test_penalty.py", "-q", "--tb=no", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    passed = sum(int(x) for x in re.findall(r"(\d+) passed", p.stdout))
    failed = sum(int(x) for x in re.findall(r"(\d+) (?:failed|error)", p.stdout))
    total = passed + failed
    return {"passed": passed, "failed": failed, "total": total,
            "pass_rate": round(passed / total, 4) if total else None}


def aggregate(per_file: dict[str, dict]) -> dict:
    fields: dict[str, dict] = {}
    for checks in per_file.values():
        for name, r in checks.items():
            a = fields.setdefault(name, {"correct": 0, "total": 0, "quote_valid": 0, "quote_total": 0})
            a["total"] += 1
            a["correct"] += bool(r["correct"])
            if r["quote_ok"] is not None:
                a["quote_total"] += 1
                a["quote_valid"] += bool(r["quote_ok"])
    for a in fields.values():
        a["accuracy"] = round(a["correct"] / a["total"], 4)
        a["quote_accuracy"] = round(a["quote_valid"] / a["quote_total"], 4) if a["quote_total"] else None
    tc = sum(a["correct"] for a in fields.values()); tt = sum(a["total"] for a in fields.values())
    qv = sum(a["quote_valid"] for a in fields.values()); qt = sum(a["quote_total"] for a in fields.values())
    return {"fields": fields,
            "overall": {"value_accuracy": round(tc / tt, 4) if tt else None, "checks": tt,
                        "quote_accuracy": round(qv / qt, 4) if qt else None, "quotes_checked": qt}}


def print_table(agg: dict, penalty: dict) -> None:
    print(f"\n{'Field':<34}{'Value acc.':>14}{'Quote in PDF':>16}")
    print("-" * 64)
    for name, a in agg["fields"].items():
        q = f"{a['quote_valid']}/{a['quote_total']}" if a["quote_total"] else "-"
        print(f"{name:<34}{f'{a['correct']}/{a['total']} ({a['accuracy']:.0%})':>14}{q:>16}")
    o = agg["overall"]
    print("-" * 64)
    print(f"{'OVERALL':<34}{f'{o['value_accuracy']:.1%}':>14}{f'{o['quote_accuracy']:.1%}' if o['quote_accuracy'] is not None else '-':>16}")
    print(f"\nPenalty simulator tests: {penalty['passed']}/{penalty['total']} passed "
          f"({(penalty['pass_rate'] or 0):.0%})")


class EvalNeedsLLM(RuntimeError):
    """Some golden document is not cached and the caller did not allow LLM calls."""

    def __init__(self, files: list[str]):
        super().__init__(f"{len(files)} file(s) not cached: {', '.join(files)}")
        self.files = files


# ------------------------------------------------------------------ golden set
GOLDEN_DIR = ROOT / "eval" / "golden"
RUNS_DIR = Path(os.environ.get("SPA_EVAL_RUNS_DIR") or ROOT / "eval" / "runs")
SCALARS = ["buyer", "unit_id", "price", "area_sqft", "handover_date", "grace_period_days", "delay_rate",
           "delay_basis", "delay_cap", "cancellation_clause"]


def load_golden(golden_dir: Path | None = None) -> list[dict]:
    """[{doc_id, pdf: Path, labels: dict, synthetic: bool}] for every folder with doc.pdf + labels.json."""
    out = []
    for d in sorted((golden_dir or GOLDEN_DIR).glob("*/")):
        if (d / "doc.pdf").exists() and (d / "labels.json").exists():
            labels = json.loads((d / "labels.json").read_text())
            out.append({"doc_id": d.name, "pdf": d / "doc.pdf", "labels": labels,
                        "synthetic": bool(labels.get("synthetic", labels.get("kind") == "synthetic"))})
    return out


def labels_to_truth(labels: dict) -> dict:
    t = {f: labels[f]["value"] for f in SCALARS if f != "cancellation_clause"}
    t["has_cancellation_clause"] = labels["cancellation_clause"]["value"] is not None
    t["payment_plan"] = [{k: m.get(k) for k in ("name", "percent", "due_date", "trigger")} for m in labels["payment_plan"]]
    return t


def uncached_files(use_cache: bool = True, golden: list[dict] | None = None) -> list[str]:
    return [g["doc_id"] for g in (golden if golden is not None else load_golden())
            if not (use_cache and load_cached(g["pdf"].read_bytes()))]


# ------------------------------------------------------------------ precision / recall / F1
def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p is not None and r is not None and p + r else (0.0 if (p is not None or r is not None) else None)
    return {"precision": None if p is None else round(p, 4), "recall": None if r is None else round(r, 4),
            "f1": None if f1 is None else round(f1, 4)}


def _row_key(m) -> tuple:
    d = m.get("due_date") if isinstance(m, dict) else m.due_date
    pc = m.get("percent") if isinstance(m, dict) else m.percent
    return (round(float(pc), 4), str(d) if d else None)


def score_doc(contract, labels: dict) -> dict:
    """Per-field outcomes for one document. Value comparison: exact for numbers/dates, normalised for text."""
    fields: dict[str, dict] = {}
    claims = grounded = hallucinations = nulls = 0
    for f in SCALARS:
        item = getattr(contract, f)
        want = labels[f]["value"]
        got = item.value
        if f == "cancellation_clause":
            ok = (got is not None) == (want is not None)
            tp = int(got is not None and want is not None); fp = int(got is not None and want is None)
            fn = int(got is None and want is not None); tn = int(got is None and want is None)
        else:
            match = got is not None and want is not None and _eq(f, got, want)
            tp = int(match); fp = int(got is not None and not match)
            fn = int(want is not None and not match); tn = int(got is None and want is None)
            ok = match or (got is None and want is None)
        fields[f] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "correct": bool(ok)}
        g = item.grounding
        if g is not None and g.status != "not_stated":
            claims += 1
            if g.status in ("grounded", "partial"):
                grounded += 1
            else:
                hallucinations += 1
        nulls += got is None
    want_rows = [_row_key(m) for m in labels["payment_plan"]]
    got_rows = [_row_key(m) for m in contract.payment_plan]
    pool, tp = list(want_rows), 0
    for k in got_rows:
        if k in pool:
            pool.remove(k); tp += 1
    fields["payment_plan_rows"] = {"tp": tp, "fp": len(got_rows) - tp, "fn": len(want_rows) - tp, "tn": 0,
                                   "correct": sorted(got_rows) == sorted(want_rows)}
    want_sum = round(sum(r[0] for r in want_rows), 4)
    sum_ok = contract.payment_plan_percent_sum is not None and abs(contract.payment_plan_percent_sum - want_sum) < 0.01
    for m in contract.payment_plan:
        claims += 1
        grounded += m.grounding is not None and m.grounding.status in ("grounded", "partial")
    claims += len(contract.ungrounded_rows); hallucinations += len(contract.ungrounded_rows)
    return {"fields": fields, "claims": claims, "grounded": grounded, "hallucinations": hallucinations,
            "abstained": int(nulls), "scalar_fields": len(SCALARS), "plan_sum_ok": bool(sum_ok)}


def aggregate_prf(per_doc: dict[str, dict]) -> dict:
    fields: dict[str, dict] = {}
    for d in per_doc.values():
        for name, r in d["fields"].items():
            a = fields.setdefault(name, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
            for k in ("tp", "fp", "fn", "tn"):
                a[k] += r[k]
    for a in fields.values():
        a.update(_prf(a["tp"], a["fp"], a["fn"]))
    tp = sum(a["tp"] for a in fields.values()); fp = sum(a["fp"] for a in fields.values())
    fn = sum(a["fn"] for a in fields.values())
    claims = sum(d["claims"] for d in per_doc.values())
    sf = sum(d["scalar_fields"] for d in per_doc.values())
    overall = {**_prf(tp, fp, fn), "tp": tp, "fp": fp, "fn": fn,
               "grounding_pass_rate": round(sum(d["grounded"] for d in per_doc.values()) / claims, 4) if claims else None,
               "claims": claims, "hallucinations": sum(d["hallucinations"] for d in per_doc.values()),
               "abstention_rate": round(sum(d["abstained"] for d in per_doc.values()) / sf, 4) if sf else None,
               "plan_sum_correct": sum(d["plan_sum_ok"] for d in per_doc.values()), "docs": len(per_doc)}
    tbl = fields.get("payment_plan_rows", {})
    table = {"row_precision": tbl.get("precision"), "row_recall": tbl.get("recall"), "row_f1": tbl.get("f1"),
             "sum_correct": overall["plan_sum_correct"], "docs": len(per_doc)}
    return {"fields": fields, "overall": overall, "table": table}


# ------------------------------------------------------------------ run history
def git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def list_runs() -> list[dict]:
    out = []
    for p in sorted(RUNS_DIR.glob("*.json")) if RUNS_DIR.exists() else []:
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            continue
    return out


def compare_runs(prev: dict | None, cur: dict) -> dict:
    """Regressions vs the previous run of the same engine. A drop in any field F1, a rise in hallucinations, or a
    drop in grounding pass rate is a regression."""
    if prev is None:
        return {"compared_to": None, "regressions": [], "improvements": []}
    reg, imp = [], []
    for name, a in cur["fields"].items():
        b = prev["fields"].get(name)
        if not b or a["f1"] is None or b["f1"] is None:
            continue
        if a["f1"] < b["f1"] - 1e-9:
            reg.append({"metric": f"{name}.f1", "before": b["f1"], "after": a["f1"]})
        elif a["f1"] > b["f1"] + 1e-9:
            imp.append({"metric": f"{name}.f1", "before": b["f1"], "after": a["f1"]})
    po, co = prev["overall"], cur["overall"]
    if co["hallucinations"] > po["hallucinations"]:
        reg.append({"metric": "hallucinations", "before": po["hallucinations"], "after": co["hallucinations"]})
    if (co["grounding_pass_rate"] or 0) < (po["grounding_pass_rate"] or 0) - 1e-9:
        reg.append({"metric": "grounding_pass_rate", "before": po["grounding_pass_rate"], "after": co["grounding_pass_rate"]})
    note = None if prev["golden"]["size"] == cur["golden"]["size"] else "golden set size changed since the previous run"
    return {"compared_to": prev["run_id"], "regressions": reg, "improvements": imp, "note": note}


def run_eval(use_cache: bool = True, allow_llm: bool = False, progress=None, log=print, engine: str = "claude_pdf",
             golden: list[dict] | None = None, save: bool = True) -> dict:
    """Score every golden document with `engine`. LLM calls only if allow_llm. Returns (and saves) the run record
    plus, for the Accuracy page, the legacy results.json shape."""
    golden = golden if golden is not None else load_golden()
    if not golden:
        raise FileNotFoundError("eval/golden has no documents (see eval/golden/README.md)")
    from app.engines import get_engine
    eng = get_engine(engine)
    todo = uncached_files(use_cache, golden) if eng.uses_llm_cache else []
    if todo and not allow_llm:
        raise EvalNeedsLLM(todo)
    per_doc, legacy, latency, usage = {}, {}, {}, {}
    for i, g in enumerate(golden):
        pdf = g["pdf"].read_bytes()
        res = eng.extract(g["pdf"], use_cache=use_cache, source_name=g["doc_id"] + ".pdf")
        contract = res.contract
        per_doc[g["doc_id"]] = score_doc(contract, g["labels"])
        latency[g["doc_id"]] = res.metrics
        legacy[g["doc_id"]] = compare(contract, labels_to_truth(g["labels"]), pdf)
        ok = sum(r["correct"] for r in per_doc[g["doc_id"]]["fields"].values())
        log(f"[{g['doc_id']}] {ok}/{len(per_doc[g['doc_id']]['fields'])} fields correct (engine={engine})")
        if progress:
            progress(i + 1, len(golden))
    agg = aggregate_prf(per_doc)
    now = datetime.now(timezone.utc)
    run = {"run_id": now.strftime("%Y%m%dT%H%M%S"), "timestamp": now.isoformat(timespec="seconds"),
           "engine": engine, "model": config.model_tag(), "git_commit": git_commit(),
           "stub": os.environ.get("SPA_STUB_MODEL") == "1",
           "golden": {"size": len(golden), "synthetic": sum(g["synthetic"] for g in golden),
                      "real": sum(not g["synthetic"] for g in golden), "docs": [g["doc_id"] for g in golden]},
           **agg, "per_doc": per_doc, "metrics": latency}
    runs = [r for r in list_runs() if r.get("engine") == engine]
    run.update(compare_runs(runs[-1] if runs else None, run))
    if save:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        (RUNS_DIR / f"{run['run_id']}.json").write_text(json.dumps(run, indent=2))
        legacy_agg = aggregate(legacy)
        penalty = penalty_test_pass_rate()
        out = {"generated_at": run["timestamp"], "model": config.model_tag(), "files": list(per_doc), **legacy_agg,
               "penalty_tests": penalty,
               "per_file": {f: {k: bool(v["correct"]) for k, v in c.items()} for f, c in legacy.items()}}
        config.EVAL_RESULTS_PATH.write_text(json.dumps(out, indent=2))
    return run


def print_run(run: dict) -> None:
    g = run["golden"]
    print(f"\nRun {run['run_id']}  engine={run['engine']}  model={run['model']}  commit={run['git_commit']}")
    print(f"Golden set: {g['size']} documents ({g['synthetic']} synthetic, {g['real']} real)")
    print(f"\n{'Field':<22}{'P':>7}{'R':>7}{'F1':>7}")
    print("-" * 43)
    for n, a in run["fields"].items():
        f = lambda v: "  -  " if v is None else f"{v:>6.2f}"
        print(f"{n:<22}{f(a['precision'])}{f(a['recall'])}{f(a['f1'])}")
    o = run["overall"]
    print("-" * 43)
    print(f"micro P/R/F1: {o['precision']}/{o['recall']}/{o['f1']}   grounding pass: {o['grounding_pass_rate']}   "
          f"abstention: {o['abstention_rate']}   hallucinations: {o['hallucinations']}")
    if g["real"] == 0:
        print("NOTE: no real documents in the golden set yet: these numbers say nothing about real-contract accuracy.")
    if run["regressions"]:
        print("REGRESSIONS vs", run["compared_to"], ":", run["regressions"])
    elif run["compared_to"]:
        print("No regressions vs", run["compared_to"])


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Evaluate extraction on eval/golden")
    ap.add_argument("--yes", action="store_true", help="allow LLM calls for uncached documents")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--model", help="model/deployment name for this run (one-command model swap)")
    ap.add_argument("--engine", default="claude_pdf")
    a = ap.parse_args(argv)
    if a.model:
        config.MODEL = a.model
        if config.PROVIDER == "azure_openai":
            os.environ["AZURE_OPENAI_DEPLOYMENT"] = a.model
        else:
            os.environ["ANTHROPIC_MODEL"] = a.model
    use_cache = not a.no_cache
    golden = load_golden()
    todo = uncached_files(use_cache, golden)
    if todo:
        if not config.llm_configured():
            print(f"ERROR: {config.setup_hint()}", file=sys.stderr)
            return 2
        if not a.yes:
            print(f"{len(todo)} document(s) are not cached: {', '.join(todo)}.\n"
                  f"This will make {len(todo)} LLM call(s) (up to {2 * len(todo)} with retries) on "
                  f"{config.model_tag()}.\nRe-run with --yes to proceed.", file=sys.stderr)
            return 3
    try:
        run = run_eval(use_cache=use_cache, allow_llm=True, engine=a.engine, golden=golden)
    except LLMError as e:
        print(f"extraction failed: {e}", file=sys.stderr)
        return 1
    print_run(run)
    print(f"\nSaved eval/runs/{run['run_id']}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
