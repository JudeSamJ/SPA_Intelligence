"""Live smoke test of the buyer agent with 6 questions (needs ANTHROPIC_API_KEY).

    python scripts/agent_smoke.py [samples/sample_a.pdf]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.agent import BuyerAgent  # noqa: E402
from app.extract import extract_file  # noqa: E402

QUESTIONS = [
    ("When is my next payment and how much is it?", "factual"),
    ("What is the late fee if the developer is late?", "factual"),
    ("What is the handover date?", "factual"),
    ("How much is the service charge per sq ft?", "outside"),   # not in the extracted contract
    ("Can I cancel and get a refund?", "refuse"),
    ("What is the grace period before compensation starts?", "factual"),
]

if not config.get_api_key():
    sys.exit("ANTHROPIC_API_KEY is not set (environment or .env).")
path = sys.argv[1] if len(sys.argv) > 1 else str(config.SAMPLES_DIR / "sample_a.pdf")
agent = BuyerAgent(extract_file(path))
for q, kind in QUESTIONS:
    r = agent.ask(q)
    print(f"\nQ [{kind}]: {q}\nA: {r.answer}\n   tools={r.tool_calls} refused={r.refused} citations={len(r.citations)}")
    if kind == "refuse":
        assert r.refused and "legal team" in r.answer
    if kind == "factual":
        assert r.citations, "factual answers must carry a citation"
