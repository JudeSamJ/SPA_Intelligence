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
os.environ.setdefault("SPA_REVIEW_DIR", str(E2E_DIR / "reviews"))
os.environ.setdefault("SPA_ALERTS_PATH", str(E2E_DIR / "alerts.json"))
os.environ.setdefault("SPA_EVAL_RUNS_DIR", str(E2E_DIR / "runs"))
os.environ.setdefault("SPA_AUDIT_DIR", str(E2E_DIR / "audit"))
os.environ.setdefault("SPA_RATES_DIR", str(Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "rates"))   # ILLUSTRATIVE rates
os.environ["SPA_STUB_MODEL"] = "1"                      # eval runs made here are labelled as stub runs
os.environ["LLM_PROVIDER"] = "azure_openai"
os.environ["AZURE_OPENAI_DEPLOYMENT"] = "e2e-stub-model"
os.environ.setdefault("AZURE_OPENAI_API_KEY", "stub")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://stub.invalid/")

import uvicorn  # noqa: E402

from app import config, extract, llm  # noqa: E402
from app.extract import extract_contract, file_hash  # noqa: E402
from backend.api.main import app  # noqa: E402
from tests.fakes import FakeClient, facts_tool_input, judgements_tool_input, oracle_input  # noqa: E402

SAMPLES = {file_hash(p.read_bytes()): p for p in sorted(config.SAMPLES_DIR.glob("*.pdf"))}
DELAY = float(os.environ.get("E2E_EXTRACT_DELAY", "1.2"))
CROSS = {}
for _d in sorted((config.ROOT / "samples" / "crossdoc").glob("set_*")):
    for _name, _which in (("brochure.pdf", "brochure"), ("filing.pdf", "filing")):
        CROSS[file_hash((_d / _name).read_bytes())] = (_d, _which)


class StubAdapter:
    """Deterministic stand-in for the model. Extraction returns ground-truth fixtures; chat picks a tool by
    keyword and phrases the real tool result (so numbers/quotes still come from the app's own logic)."""

    def complete(self, system, messages, tools, force_tool=None, max_tokens=1024):
        llm._count()
        if force_tool == "record_document_facts":        # cross-document facts (brochure / filing)
            time.sleep(0.4)
            d, which = CROSS[file_hash(messages[0]["pdf"])]
            return llm.LLMReply(tool_calls=[llm.ToolCall("stubf", force_tool, facts_tool_input(d, which))])
        if force_tool == "record_clause_judgements":     # playbook clause specialists
            time.sleep(0.4)
            return llm.LLMReply(tool_calls=[llm.ToolCall("stubj", force_tool, judgements_tool_input(messages[0]["pages"]))])
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


def seed_penalty_fixture():
    """Fixture for the headline hand-calculated case: price 1,000,000 / 6% / grace 30 -> 90 days = 9,863.01."""
    import pymupdf
    from datetime import date as _d
    from app.schema import ContractData, Sourced
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Penalty fixture contract: price 1,000,000; rate 6% per annum; grace 30 days.")
    data = doc.tobytes()
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    h = file_hash(data)
    (config.UPLOAD_DIR / f"{h}.pdf").write_bytes(data)
    (config.UPLOAD_DIR / f"{h}.meta.json").write_text(json.dumps({"name": "fixture_penalty_case.pdf"}))
    S = lambda v: Sourced(value=v, source_page=1, source_quote="Penalty fixture contract")  # noqa: E731
    plan = [{"name": "Only payment", "percent": 100.0, "due_date": _d(2027, 1, 1), "trigger": "On signing", "source_page": 1, "source_quote": "Penalty fixture contract"}]
    c = ContractData(buyer=S("Fixture Buyer"), unit_id=S("FX-1"), price=S(1000000.0), area_sqft=S(1000.0),
                     handover_date=S(_d(2027, 1, 1)), grace_period_days=S(30), delay_rate=S(6.0),
                     delay_basis=S("percent_per_annum"), delay_cap=Sourced(), payment_plan=plan,
                     cancellation_clause=Sourced(), model=config.model_tag(), file_hash=h, source_file="fixture_penalty_case.pdf",
                     payment_plan_percent_sum=100.0, extracted_at="fixture", grounded_version=1)
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (config.CACHE_DIR / f"{h}.json").write_text(c.model_dump_json())


def seed_review_fixture():
    """A contract whose price quote has a typo ('Prize'), so grounding marks it PARTIAL and it lands in the review queue."""
    import pymupdf
    from datetime import date as _d
    from app.schema import ContractData, Sourced
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "The Purchase Price is AED 1,250,000 payable in instalments. Handover on 1 January 2029.")
    data = doc.tobytes()
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    h = file_hash(data)
    (config.UPLOAD_DIR / f"{h}.pdf").write_bytes(data)
    (config.UPLOAD_DIR / f"{h}.meta.json").write_text(json.dumps({"name": "fixture_review_case.pdf"}))
    quote_ok = "The Purchase Price is AED 1,250,000"
    c = ContractData(buyer=Sourced(), unit_id=Sourced(),
                     price=Sourced(value=1250000.0, source_page=1, source_quote="The Purchase Prize is AED 1,250,000"),
                     area_sqft=Sourced(), handover_date=Sourced(value=_d(2029, 1, 1), source_page=1, source_quote="Handover on 1 January 2029"),
                     grace_period_days=Sourced(), delay_rate=Sourced(), delay_basis=Sourced(), delay_cap=Sourced(),
                     payment_plan=[], cancellation_clause=Sourced(), model=config.model_tag(), file_hash=h,
                     source_file="fixture_review_case.pdf", extracted_at="fixture")
    del quote_ok
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (config.CACHE_DIR / f"{h}.json").write_text(c.model_dump_json())


def seed():
    import shutil
    E2E_DIR.mkdir(parents=True, exist_ok=True)
    config.EVAL_RESULTS_PATH = E2E_DIR / "results.json"      # never touch the repo's real eval/results.json
    real = Path(__file__).resolve().parents[2] / "eval" / "results.json"
    if not config.EVAL_RESULTS_PATH.exists() and real.exists():
        shutil.copy(real, config.EVAL_RESULTS_PATH)
    skip = {x.strip() for x in os.environ.get("E2E_UNSEEDED", "").split(",") if x.strip()}
    for p in SAMPLES.values():
        if p.name in skip:
            continue
        if not extract.load_cached(p.read_bytes()):
            extract.extract_contract(p.read_bytes(), p.name, client=FakeClient(oracle_input(p)))


if __name__ == "__main__":
    extract.get_llm = lambda client=None: StubAdapter()
    llm.get_llm = lambda client=None: StubAdapter()     # crossdoc facts + playbook import it lazily
    import app.agent as agent
    agent.get_llm = lambda client=None: StubAdapter()
    seed()
    if os.environ.get("E2E_FIXTURE_CASE") == "1":
        seed_penalty_fixture()
        seed_review_fixture()
    llm._calls = 0   # fixture seeding is not a "call" for the demo counter
    print(f"E2E stub server: cache={config.CACHE_DIR} model={config.model_tag()}", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("E2E_PORT", "8000")), log_level="warning")
