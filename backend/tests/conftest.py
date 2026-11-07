import os

import pytest

os.environ.setdefault("SPA_DISABLE_SCHEDULER", "1")

from app import llm


@pytest.fixture(autouse=True)
def reset_llm_counter():
    llm._calls = 0
    yield
    llm._calls = 0
