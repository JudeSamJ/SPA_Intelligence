from __future__ import annotations

import json
import threading

from fastapi import APIRouter

from app import config
from backend.api.deps import ApiError
from backend.api.schemas import EvalResults, EvalRunRequest, EvalRunStatus
from eval.run_eval import EvalNeedsLLM, run_eval, uncached_files

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
        todo = uncached_files(body.use_cache)
        if todo and not body.allow_llm:
            raise ApiError(409, "llm_confirmation_required",
                           f"{len(todo)} sample(s) are not cached; running would make up to {2 * len(todo)} LLM "
                           f"call(s). Repeat with allow_llm=true to confirm.")
        if todo and not config.llm_configured():
            raise ApiError(503, "llm_not_configured", config.setup_hint())
        _state = EvalRunStatus(state="running", done=0, total=len(json.loads(config.GROUND_TRUTH_PATH.read_text())))

    def progress(done, total):
        global _state
        _state = EvalRunStatus(state="running", done=done, total=total)

    def work():
        global _state
        try:
            run_eval(use_cache=body.use_cache, allow_llm=body.allow_llm, progress=progress, log=lambda *_: None)
            _state = EvalRunStatus(state="done", done=_state.total, total=_state.total)
        except EvalNeedsLLM as e:
            _state = EvalRunStatus(state="error", message=str(e))
        except Exception as e:  # noqa: BLE001
            _state = EvalRunStatus(state="error", message=f"{type(e).__name__}: {str(e)[:300]}")

    threading.Thread(target=work, daemon=True, name="eval-run").start()
    return _state
