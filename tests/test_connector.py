"""The curated connector definitions must never drift from the real API."""
import json
from pathlib import Path

import pytest

from backend.api.main import app

ROOT = Path(__file__).resolve().parent.parent
FILES = ["integrations/power-platform/spa-intelligence.swagger.json", "integrations/copilot-studio/buyer-chat.swagger.json"]
API = app.openapi()["paths"]


@pytest.mark.parametrize("f", FILES)
def test_every_operation_exists_in_the_api_with_unique_ids(f):
    spec = json.loads((ROOT / f).read_text())
    ids = []
    for path, ops in spec["paths"].items():
        for method, d in ops.items():
            assert method in API.get("/api" + path, {}), f"{method.upper()} {path} not in the FastAPI app"
            ids.append(d["operationId"])
    assert len(ids) == len(set(ids)) and ids


@pytest.mark.parametrize("f", FILES)
def test_entra_oauth_and_disclaimer_present(f):
    spec = json.loads((ROOT / f).read_text())
    assert spec["swagger"] == "2.0" and spec["schemes"] == ["https"]
    assert "login.microsoftonline.com" in spec["securityDefinitions"]["oauth2"]["tokenUrl"]
    assert "not legal advice" in spec["info"]["description"]
    assert "client_secret" not in json.dumps(spec).lower()


def test_buyer_definition_exposes_only_buyer_chat_and_staff_one_excludes_internal_routes():
    buyer = json.loads((ROOT / FILES[1]).read_text())
    assert list(buyer["paths"]) == ["/buyer/chat"]
    staff = json.dumps(json.loads((ROOT / FILES[0]).read_text())["paths"])
    for internal in ("playbook", "buyer/chat", "golden-export", "eval/run", "jurisdiction"):
        assert internal not in staff
