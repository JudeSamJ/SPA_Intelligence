import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = sorted((ROOT / "integrations/power-automate").glob("adaptive-card-*.json"))


def test_adaptive_cards_are_valid_and_carry_the_disclaimer_or_warning():
    assert len(CARDS) == 3
    for f in CARDS:
        c = json.loads(f.read_text())
        assert c["type"] == "AdaptiveCard" and c["version"] == "1.4" and c["body"] and c["actions"]
        assert all(a["type"] == "Action.Submit" for a in c["actions"])
        text = json.dumps(c)
        assert "not legal advice" in text or "unreviewed legal logic" in text


def test_buyer_agent_instructions_forbid_general_knowledge():
    t = (ROOT / "integrations/copilot-studio/agent-instructions.md").read_text()
    for needle in ("Never answer from your own knowledge", "refused = true", "own contract", "Decision support, not legal advice"):
        assert needle in t
    assert (ROOT / "integrations/copilot-studio/test-conversations.md").read_text().count("\n| ") >= 12


def test_flow_doc_names_only_operations_that_exist():
    import re
    spec = json.loads((ROOT / "integrations/power-platform/spa-intelligence.swagger.json").read_text())
    ops = {d["operationId"] for p in spec["paths"].values() for d in p.values()}
    doc = (ROOT / "integrations/power-automate/README.md").read_text()
    used = set(re.findall(r"`([A-Z][A-Za-z]+)`", doc)) & {"ReviewField", "GetStatuteGap", "PreviewErpExport", "PushToErp", "ListAlerts", "AcknowledgeAlert", "GetContract", "GetExtractionStatus"}
    assert used and used <= ops
