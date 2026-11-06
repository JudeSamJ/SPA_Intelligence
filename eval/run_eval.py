"""Run extraction on all samples and score against ground_truth.json.

Scoring: exact match for numbers/dates/enums, normalised-string match for names/ids, and a
check that every quote appears verbatim (whitespace/case-normalised) in the PDF text.
Cached extractions are reused (free). Uncached files cost 1 LLM call each (2 on a retry), so the
script refuses to call the API unless you pass --yes.

    python eval/run_eval.py [--yes] [--no-cache]
"""
from __future__ import annotations

import json
import re
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
    """Some sample is not cached and the caller did not allow LLM calls."""

    def __init__(self, files: list[str]):
        super().__init__(f"{len(files)} file(s) not cached: {', '.join(files)}")
        self.files = files


def uncached_files(use_cache: bool = True) -> list[str]:
    truth = json.loads(config.GROUND_TRUTH_PATH.read_text())
    return [f for f in truth if not (use_cache and load_cached((config.SAMPLES_DIR / f).read_bytes()))]


def run_eval(use_cache: bool = True, allow_llm: bool = False, progress=None, log=print) -> dict:
    """Score all samples; returns (and saves) the results dict. LLM is only used if allow_llm."""
    truth = json.loads(config.GROUND_TRUTH_PATH.read_text())
    todo = uncached_files(use_cache)
    if todo and not allow_llm:
        raise EvalNeedsLLM(todo)
    per_file: dict[str, dict] = {}
    for i, (fname, t) in enumerate(truth.items()):
        pdf = (config.SAMPLES_DIR / fname).read_bytes()
        contract = extract_contract(pdf, fname, use_cache=use_cache)
        per_file[fname] = compare(contract, t, pdf)
        ok = sum(r["correct"] for r in per_file[fname].values())
        log(f"[{fname}] {ok}/{len(per_file[fname])} checks correct (model={contract.model})")
        if progress:
            progress(i + 1, len(truth))
    agg = aggregate(per_file)
    penalty = penalty_test_pass_rate()
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": config.model_tag(),
           "files": list(per_file), **agg, "penalty_tests": penalty,
           "per_file": {f: {k: bool(v["correct"]) for k, v in c.items()} for f, c in per_file.items()}}
    config.EVAL_RESULTS_PATH.write_text(json.dumps(out, indent=2))
    return out


def main(argv: list[str]) -> int:
    use_cache = "--no-cache" not in argv
    todo = uncached_files(use_cache)
    if todo:
        if not config.llm_configured():
            print(f"ERROR: {config.setup_hint()}", file=sys.stderr)
            return 2
        if "--yes" not in argv:
            print(f"{len(todo)} file(s) are not cached: {', '.join(todo)}.\n"
                  f"This will make {len(todo)} LLM call(s) (up to {2 * len(todo)} with retries) on "
                  f"{config.model_tag()}.\nRe-run with --yes to proceed.", file=sys.stderr)
            return 3
    try:
        out = run_eval(use_cache=use_cache, allow_llm=True)
    except LLMError as e:
        print(f"extraction failed: {e}", file=sys.stderr)
        return 1
    print_table({"fields": out["fields"], "overall": out["overall"]}, out["penalty_tests"])
    print(f"\nSaved {config.EVAL_RESULTS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
