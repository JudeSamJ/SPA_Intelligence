from __future__ import annotations

import json
import threading

from fastapi import APIRouter

from app import config
from backend.api.deps import ApiError
from backend.api.schemas import EvalResults, EvalRunRequest, EvalRunStatus
from app.engines import list_engines
from eval import run_eval as ev
from eval.run_eval import EvalNeedsLLM, load_golden, run_eval, uncached_files

router = APIRouter(prefix="/eval", tags=["eval"])
_state = EvalRunStatus(state="idle")
_lock = threading.Lock()


@router.get("/results", response_model=EvalResults)
def results():
    p = config.EVAL_RESULTS_PATH
    if not p.exists():
        raise ApiError(404, "no_results", "No evaluation results yet. Run the evaluation first.")
    return EvalResults.model_validate(json.loads(p.read_text()))


@router.get("/run/status", response_model=EvalRunStatus)
def run_status():
    return _state


@router.post("/run", response_model=EvalRunStatus, status_code=202)
def run(body: EvalRunRequest | None = None):
    global _state
    body = body or EvalRunRequest()
    with _lock:
        if _state.state == "running":
            return _state
        todo = uncached_files(body.use_cache) if body.engine == "claude_pdf" else []
        if todo and not body.allow_llm:
            raise ApiError(409, "llm_confirmation_required",
                           f"{len(todo)} sample(s) are not cached; running would make up to {2 * len(todo)} LLM "
                           f"call(s). Repeat with allow_llm=true to confirm.")
        if todo and not config.llm_configured():
            raise ApiError(503, "llm_not_configured", config.setup_hint())
        _state = EvalRunStatus(state="running", done=0, total=len(load_golden()))

    def progress(done, total):
        global _state
        _state = EvalRunStatus(state="running", done=done, total=total)

    def work():
        global _state
        try:
            run_eval(use_cache=body.use_cache, allow_llm=body.allow_llm, progress=progress, log=lambda *_: None,
                     engine=body.engine)
            _state = EvalRunStatus(state="done", done=_state.total, total=_state.total)
        except EvalNeedsLLM as e:
            _state = EvalRunStatus(state="error", message=str(e))
        except Exception as e:  # noqa: BLE001
            _state = EvalRunStatus(state="error", message=f"{type(e).__name__}: {str(e)[:300]}")

    threading.Thread(target=work, daemon=True, name="eval-run").start()
    return _state


def _summary(r: dict) -> dict:
    return {k: r.get(k) for k in ("run_id", "timestamp", "engine", "model", "git_commit", "stub", "golden", "overall",
                                  "table", "compared_to")} | {"regressions": len(r.get("regressions", []))}


@router.get("/runs")
def runs(engine: str | None = None):
    rs = [r for r in ev.list_runs() if engine in (None, r.get("engine"))]
    return {"runs": [_summary(r) for r in reversed(rs)]}


@router.get("/runs/{run_id}")
def run_detail(run_id: str):
    for r in ev.list_runs():
        if r.get("run_id") == run_id:
            return r
    raise ApiError(404, "not_found", "No such run.")


@router.get("/engines")
def engines():
    return {"engines": list_engines()}


@router.get("/bakeoff")
def bakeoff():
    """Latest run per engine on the same golden set, side by side. Engines without a run show their config status."""
    latest = {}
    for r in ev.list_runs():
        latest[r["engine"]] = r
    out = []
    for e in list_engines():
        r = latest.get(e["name"])
        row = {**e, "run": None}
        if r:
            ms = list(r.get("metrics", {}).values())
            cost = [m["cost_usd"] for m in ms if m.get("cost_usd") is not None]
            row["run"] = {**_summary(r), "fields": {k: v["f1"] for k, v in r["fields"].items()},
                          "avg_latency_s": round(sum(m.get("latency_s", 0) for m in ms) / len(ms), 3) if ms else None,
                          "input_tokens": sum(m.get("input_tokens", 0) for m in ms),
                          "output_tokens": sum(m.get("output_tokens", 0) for m in ms),
                          "cost_per_doc_usd": round(sum(cost) / len(cost), 6) if cost else None,
                          "cached_docs": sum(1 for m in ms if m.get("cached"))}
        out.append(row)
    g = load_golden()
    return {"engines": out, "golden_size": len(g), "golden_real": sum(not d["synthetic"] for d in g),
            "note": "Results apply only to our golden set and its size is shown. Synthetic documents are a smoke set."}
