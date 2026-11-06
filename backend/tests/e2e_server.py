"""TEST-ONLY dev server: real API + real core logic, but the LLM is a deterministic stub and the cache is
seeded from ground-truth fixtures. Used for curl/Playwright checks without a key. Never used in production.

    E2E_DIR=/tmp/e2e python -m backend.tests.e2e_server     (port E2E_PORT, default 8000)
"""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

E2E_DIR = Path(os.environ.get("E2E_DIR", "/tmp/spa-e2e"))
os.environ.setdefault("SPA_CACHE_DIR", str(E2E_DIR / "cache"))
os.environ.setdefault("SPA_UPLOAD_DIR", str(E2E_DIR / "uploads"))
os.environ["LLM_PROVIDER"] = "azure_openai"
os.environ["AZURE_OPENAI_DEPLOYMENT"] = "e2e-stub-model"
os.environ.setdefault("AZURE_OPENAI_API_KEY", "stub")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://stub.invalid/")

import uvicorn  # noqa: E402

from app import config, extract, llm  # noqa: E402
from app.extract import extract_contract, file_hash  # noqa: E402
from backend.api.main import app  # noqa: E402
from tests.fakes import FakeClient, oracle_input  # noqa: E402

SAMPLES = {file_hash(p.read_bytes()): p for p in sorted(config.SAMPLES_DIR.glob("*.pdf"))}
DELAY = float(os.environ.get("E2E_EXTRACT_DELAY", "1.2"))


class StubAdapter:
    """Deterministic stand-in for the model. Extraction returns ground-truth fixtures; chat picks a tool by
    keyword and phrases the real tool result (so numbers/quotes still come from the app's own logic)."""

    def complete(self, system, messages, tools, force_tool=None, max_tokens=1024):
        llm._count()
        if force_tool:                                   # extraction
            time.sleep(DELAY)
            pdf = messages[0]["pdf"]
            src = SAMPLES.get(file_hash(pdf))
            if not src:
                raise llm.LLMError("The stub model only knows the three sample contracts.")
            return llm.LLMReply(tool_calls=[llm.ToolCall("stub1", force_tool, oracle_input(src))])
        last = messages[-1]
        if last["role"] == "tool":                       # phrase the tool result
            res = json.loads(last["results"][0]["content"])
            return llm.LLMReply(text=self.phrase(res))
        q = last["content"].lower()
        if re.search(r"next|payment due|instal", q):
            return self.call("next_payment", {"as_of_date": date.today().isoformat()})
        if "handover" in q or "hand over" in q:
            return self.call("handover_date", {})
        if re.search(r"late|penalt|delay|compensat|grace", q):
            return self.call("late_fee_rule", {})
        if re.search(r"schedule|plan|milestone", q):
            return self.call("payment_schedule", {})
        return llm.LLMReply(text="This is not stated in the contract.")

    @staticmethod
    def call(name, args):
        return llm.LLMReply(tool_calls=[llm.ToolCall("c1", name, args)])

    @staticmethod
    def phrase(r: dict) -> str:
        if "next_payment" in r and r["next_payment"]:
            n = r["next_payment"]
            return (f"Your next payment is {n['milestone']}: AED {n['amount_aed']:,.2f} ({n['percent']:g}%) due "
                    f"{n['due_date']} (page {n['source_page']}: “{n['source_quote']}”).")
        if "next_payment" in r:
            return "No dated payment remains after today."
        if "grace_period_days" in r:
            g, rate, cap = r["grace_period_days"], r["delay_rate"], r["delay_cap_percent_of_price"]
            return (f"Delay compensation starts after a grace period of {g['value']} days (page {g['source_page']}: "
                    f"“{g['source_quote']}”). Rate: {rate['value']:g} ({r['delay_basis']['value']}). "
                    f"Cap: {cap['value'] if cap['value'] is not None else 'none stated'}.")
        if "milestones" in r:
            return f"The plan has {len(r['milestones'])} milestones; plan total {r['percent_sum']}%."
        if r.get("value"):
            return f"The handover date is {r['value']} (page {r['source_page']}: “{r['source_quote']}”)."
        return "This is not stated in the contract."


def seed():
    import shutil
    E2E_DIR.mkdir(parents=True, exist_ok=True)
    config.EVAL_RESULTS_PATH = E2E_DIR / "results.json"      # never touch the repo's real eval/results.json
    real = Path(__file__).resolve().parents[2] / "eval" / "results.json"
    if not config.EVAL_RESULTS_PATH.exists() and real.exists():
        shutil.copy(real, config.EVAL_RESULTS_PATH)
    for p in SAMPLES.values():
        if not extract.load_cached(p.read_bytes()):
            extract.extract_contract(p.read_bytes(), p.name, client=FakeClient(oracle_input(p)))


if __name__ == "__main__":
    extract.get_llm = lambda client=None: StubAdapter()
    import app.agent as agent
    agent.get_llm = lambda client=None: StubAdapter()
    seed()
    llm._calls = 0   # fixture seeding is not a "call" for the demo counter
    print(f"E2E stub server: cache={config.CACHE_DIR} model={config.model_tag()}", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("E2E_PORT", "8000")), log_level="warning")
