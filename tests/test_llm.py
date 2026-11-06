import json
from types import SimpleNamespace

import pytest

from app import config, llm
from app.llm import AzureOpenAIAdapter, LLMError, ToolCall

TOOLS = [{"name": "t", "description": "d", "input_schema": {"type": "object", "properties": {}}}]


class FakeAzure:
    def __init__(self, *msgs):
        self.msgs, self.calls = list(msgs), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._c))

    def _c(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.msgs.pop(0))])


def tool_msg(name, args, id="c1"):
    return SimpleNamespace(content=None, tool_calls=[SimpleNamespace(
        id=id, function=SimpleNamespace(name=name, arguments=args))])


def test_azure_request_shape_pages_and_forced_tool(monkeypatch):
    monkeypatch.setattr(config, "MODEL", "my-deployment")
    c = FakeAzure(tool_msg("t", '{"a": 1}'))
    r = AzureOpenAIAdapter(c).complete("SYS", [{"role": "user", "content": "go", "pdf": b"x", "pages": ["p one", "p two"]}],
                                       TOOLS, force_tool="t", max_tokens=99)
    kw = c.calls[0]
    assert kw["model"] == "my-deployment" and kw["max_completion_tokens"] == 99
    assert kw["messages"][0] == {"role": "system", "content": "SYS"}
    assert "[PAGE 1]\np one" in kw["messages"][1]["content"] and "[PAGE 2]" in kw["messages"][1]["content"]
    assert kw["tool_choice"] == {"type": "function", "function": {"name": "t"}}
    assert kw["tools"][0]["function"]["parameters"] == TOOLS[0]["input_schema"]
    assert "temperature" not in kw
    assert r.tool_calls == [ToolCall("c1", "t", {"a": 1})]


def test_azure_tool_roundtrip_messages():
    c = FakeAzure(SimpleNamespace(content="done", tool_calls=None))
    msgs = [{"role": "user", "content": "q"},
            {"role": "assistant", "text": "", "tool_calls": [ToolCall("c1", "t", {"x": 2})]},
            {"role": "tool", "results": [{"id": "c1", "content": "res"}]}]
    r = AzureOpenAIAdapter(c).complete("S", msgs, TOOLS)
    sent = c.calls[0]["messages"]
    assert sent[2]["tool_calls"][0]["function"]["arguments"] == json.dumps({"x": 2})
    assert sent[3] == {"role": "tool", "tool_call_id": "c1", "content": "res"}
    assert r.text == "done" and r.tool_calls == []


def test_azure_invalid_json_arguments_become_validation_failure():
    c = FakeAzure(tool_msg("t", "{not json"))
    r = AzureOpenAIAdapter(c).complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert "__invalid_json__" in r.tool_calls[0].args


def test_call_cap_blocks_further_calls(monkeypatch):
    monkeypatch.setattr(config, "MAX_LLM_CALLS", 2)
    c = FakeAzure(*[SimpleNamespace(content="ok", tool_calls=None)] * 3)
    a = AzureOpenAIAdapter(c)
    a.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    a.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    with pytest.raises(LLMError, match="cap"):
        a.complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert len(c.calls) == 2 and llm.calls_made() == 2


def test_unconfigured_azure_raises_setup_hint(monkeypatch):
    monkeypatch.setattr(config, "PROVIDER", "azure_openai")
    for v in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(LLMError, match=".env"):
        AzureOpenAIAdapter().complete("S", [{"role": "user", "content": "q"}], TOOLS)
    assert llm.calls_made() == 0  # config error must not consume the call budget
