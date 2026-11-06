"""Central configuration. Provider/model/keys come from .env (never commit real keys)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---- LLM provider: "azure_openai" (default) or "anthropic" -------------------------------
PROVIDER = (os.environ.get("LLM_PROVIDER") or "azure_openai").strip().lower()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-5-5"
AZURE_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT") or ""   # your Azure deployment name
MODEL = AZURE_DEPLOYMENT if PROVIDER == "azure_openai" else ANTHROPIC_MODEL   # <- the one model constant

MAX_TOKENS = 4096            # extraction output cap
AGENT_MAX_TOKENS = 600       # per agent answer
AGENT_MAX_TURNS = 4          # tool round-trips per question
AGENT_HISTORY_MESSAGES = 6   # chat history sent back to the model
# Hard safety cap on LLM calls per Python process (protects a shared company key).
MAX_LLM_CALLS = int(os.environ.get("LLM_MAX_CALLS") or 40)

UPLOAD_DIR = Path(os.environ.get("SPA_UPLOAD_DIR") or ROOT / "data" / "uploads")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_PAGES = 300
CORS_ORIGINS = [o.strip() for o in (os.environ.get("CORS_ORIGINS") or "http://localhost:5173").split(",")
                if o.strip() and o.strip() != "*"]          # explicit origins only, never a wildcard
SERVE_FRONTEND = os.environ.get("SERVE_FRONTEND") == "1"
FRONTEND_DIST = ROOT / "frontend" / "dist"
UPLOAD_RATE = (int(os.environ.get("RATE_UPLOADS") or 10), 60)   # requests, window seconds
CHAT_RATE = (int(os.environ.get("RATE_CHAT") or 30), 60)
SAMPLES_DIR = ROOT / "samples"
CACHE_DIR = Path(os.environ.get("SPA_CACHE_DIR") or ROOT / "data" / "cache")
RULES_DIR = ROOT / "rules"
GROUND_TRUTH_PATH = ROOT / "ground_truth.json"
EVAL_RESULTS_PATH = ROOT / "eval" / "results.json"
DEFAULT_RULES = "uae"

DISCLAIMER = "Decision support, not legal advice."

_AZURE_VARS = ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"]


def model_tag() -> str:
    """Provider + model; used to invalidate cached extractions when either changes."""
    return f"{PROVIDER}/{MODEL}"


def missing_settings() -> list[str]:
    """Names of required settings that are empty for the active provider."""
    if PROVIDER == "azure_openai":
        return [v for v in _AZURE_VARS if not os.environ.get(v)]
    if PROVIDER == "anthropic":
        return [] if os.environ.get("ANTHROPIC_API_KEY") else ["ANTHROPIC_API_KEY"]
    return [f"LLM_PROVIDER (unknown value '{PROVIDER}')"]


def llm_configured() -> bool:
    return not missing_settings()


def setup_hint() -> str:
    return ("LLM is not configured. Add the missing values to the .env file in the project root: "
            + ", ".join(missing_settings()) + ".")


@lru_cache(maxsize=None)
def load_rules(name: str = DEFAULT_RULES) -> dict:
    """Load jurisdiction rules from rules/<name>.yaml (nothing jurisdictional is hardcoded in code)."""
    with open(RULES_DIR / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
