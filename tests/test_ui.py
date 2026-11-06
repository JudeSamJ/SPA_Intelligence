"""Headless UI smoke test: loads the app for each sample using pre-seeded cache (test-only fakes)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import config
from app.extract import extract_contract
from tests.fakes import FakeClient, oracle_input

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    for p in sorted(SAMPLES.glob("*.pdf")):
        extract_contract(p.read_bytes(), p.name, client=FakeClient(oracle_input(p)))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.mark.parametrize("idx", [0, 1, 2])
def test_all_tabs_load_for_each_sample(seeded, idx):
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    at.selectbox[0].select_index(idx).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 5
    assert any("not legal advice" in w.value for w in at.warning)
    assert len(at.dataframe) >= 3          # terms, payment plan, penalty/cashflow tables


def test_sample_c_shows_warnings(seeded):
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    at.selectbox[0].select_index(2).run()
    errs = " ".join(e.value for e in at.error)
    assert "sum to 95%" in errs and "No cancellation clause" in errs


def test_chat_refuses_legal_question_without_api(seeded):
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    at.chat_input[0].set_value("Can I cancel and get a refund?").run()
    assert not at.exception
    assert any("legal team" in m.markdown[0].value for m in at.chat_message if m.name == "assistant")


def test_unseeded_no_key_shows_error_not_fake_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    assert not at.exception and any("ANTHROPIC_API_KEY" in e.value for e in at.error)
