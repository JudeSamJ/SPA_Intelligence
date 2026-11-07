"""The curated connector definitions must never drift from the real API."""
import json
from pathlib import Path

import pytest

from backend.api.main import app

ROOT = Path(__file__).resolve().parent.parent
FILES = ["integrations/power-platform/spa-intelligence.swagger.json", "integrations/copilot-studio/buyer-chat.swagger.json"]
APIKEY = [f.replace(".swagger", ".apikey.swagger") for f in FILES]
API = app.openapi()["paths"]


@pytest.mark.parametrize("f", FILES + APIKEY)
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


@pytest.mark.parametrize("f", APIKEY)
def test_apikey_variants_use_a_header_key_not_oauth(f):
    spec = json.loads((ROOT / f).read_text())
    assert spec["securityDefinitions"] == {"api_key": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
    assert spec["security"] == [{"api_key": []}] and "oauth2" not in json.dumps(spec)
    entra = json.loads((ROOT / f.replace(".apikey", "")).read_text())
    assert spec["paths"] == entra["paths"]                      # identical operations, only the security differs


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
            if k == "required" and isinstance(v, list):
                yield path, v
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}/{i}")


@pytest.mark.parametrize("f", FILES + APIKEY)
def test_no_empty_required_arrays(f):
    """Power Platform refuses `required: []` ("requires at least one value")."""
    spec = json.loads((ROOT / f).read_text())
    assert [p for p, v in _walk(spec) if v == []] == []
