"""Central configuration. Change MODEL here to switch the Claude model everywhere."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "claude-sonnet-5-5"          # <- single place to change the model
MAX_TOKENS = 4096
AGENT_MAX_TURNS = 6

SAMPLES_DIR = ROOT / "samples"
CACHE_DIR = Path(os.environ.get("SPA_CACHE_DIR") or ROOT / "data" / "cache")
RULES_DIR = ROOT / "rules"
GROUND_TRUTH_PATH = ROOT / "ground_truth.json"
EVAL_RESULTS_PATH = ROOT / "eval" / "results.json"
DEFAULT_RULES = "uae"

DISCLAIMER = "Decision support, not legal advice."


def get_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


@lru_cache(maxsize=None)
def load_rules(name: str = DEFAULT_RULES) -> dict:
    """Load jurisdiction rules from rules/<name>.yaml (nothing jurisdictional is hardcoded in code)."""
    with open(RULES_DIR / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
