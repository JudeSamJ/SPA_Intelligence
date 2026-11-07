import pytest

from app import llm


@pytest.fixture(autouse=True)
def reset_llm_counter():
    llm._calls = 0
    yield
    llm._calls = 0
