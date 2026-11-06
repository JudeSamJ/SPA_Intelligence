"""Provider-neutral LLM layer (Azure OpenAI or Anthropic) with a hard call cap.

Neutral messages:
  {"role":"user","content":str, optional "pdf":bytes, "pages":[str]}
  {"role":"assistant","text":str,"tool_calls":[ToolCall]}
  {"role":"tool","results":[{"id","content","is_error"}]}
Adapters convert these to provider formats. Every network call goes through _count(),
which enforces config.MAX_LLM_CALLS per process.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

from . import config


class LLMError(RuntimeError):
    pass


class LLMCapError(LLMError):
    """The per-process LLM call cap was reached."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


_calls = 0


def calls_made() -> int:
    return _calls


def _count() -> None:
    global _calls
    if _calls >= config.MAX_LLM_CALLS:
        raise LLMCapError(f"LLM call cap reached ({config.MAX_LLM_CALLS} per process) to protect the API key. "
                       f"Restart the app or raise LLM_MAX_CALLS in .env if this is intended.")
    _calls += 1


def normalize_endpoint(url: str) -> str:
    """Keep only scheme://host (users often paste a full /openai/deployments/... URL)."""
    from urllib.parse import urlparse
    u = urlparse(url.strip())
    return f"{u.scheme}://{u.netloc}/" if u.scheme and u.netloc else url.strip()


def v1_base_url(endpoint: str) -> str | None:
    """Foundry / Azure OpenAI 'v1' endpoints (…services.ai.azure.com or a /openai/v1 path) use the plain
    OpenAI client at <host>/openai/v1/ with no api-version. Return that base URL, else None (classic)."""
    from urllib.parse import urlparse
    u = urlparse(endpoint.strip())
    if "/openai/v1" in u.path or u.netloc.endswith(".services.ai.azure.com"):
        return f"{u.scheme}://{u.netloc}/openai/v1/"
    return None


def azure_error_hint(status: int | None, detail: str) -> str:
    dep, host = config.MODEL, normalize_endpoint(__import__("os").environ.get("AZURE_OPENAI_ENDPOINT", ""))
    if status == 404:
        return (f"Azure returned 404 (not found) for deployment '{dep}' at {host}. Check that "
                f"AZURE_OPENAI_DEPLOYMENT is the deployment NAME from the Azure portal (Model deployments), "
                f"not just the model name, that it lives in the resource this endpoint belongs to, and that "
                f"AZURE_OPENAI_ENDPOINT is only https://<resource>.openai.azure.com/ . No usage was incurred.")
    if status in (401, 403):
        return f"Azure rejected the key ({status}). Check AZURE_OPENAI_API_KEY belongs to the resource at {host}."
    if status == 400:
        return (f"Azure rejected the request (400): {detail}. If it mentions api-version or an unsupported "
                f"parameter, set AZURE_OPENAI_API_VERSION to the version shown in your Azure portal.")
    return f"Azure request failed ({status}): {detail}"


def pages_text(pages: list[str]) -> str:
    return "\n\n".join(f"[PAGE {i}]\n{t}" for i, t in enumerate(pages, 1))


# ------------------------------------------------------------------ Anthropic
class AnthropicAdapter:
    def __init__(self, client=None):
        self._client = client

    def _c(self):
        if self._client is None:
            import anthropic
            if not config.llm_configured():
                raise LLMError(config.setup_hint())
            self._client = anthropic.Anthropic()
        return self._client

    @staticmethod
    def _convert(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "user":
                if m.get("pdf"):
                    content = [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                                "data": base64.standard_b64encode(m["pdf"]).decode()}},
                               {"type": "text", "text": m["content"]}]
                else:
                    content = m["content"]
                out.append({"role": "user", "content": content})
            elif m["role"] == "assistant":
                blocks = ([{"type": "text", "text": m["text"]}] if m.get("text") else []) + [
                    {"type": "tool_use", "id": t.id, "name": t.name, "input": t.args} for t in m.get("tool_calls", [])]
                out.append({"role": "assistant", "content": blocks or m.get("text", "")})
            else:  # tool results
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"],
                     **({"is_error": True} if r.get("is_error") else {})} for r in m["results"]]})
        return out

    def complete(self, system, messages, tools, force_tool=None, max_tokens=1024) -> LLMReply:
        client = self._c()          # config errors raise before a call is counted
        _count()
        kw = {"tool_choice": {"type": "tool", "name": force_tool}} if force_tool else {}
        resp = client.messages.create(model=config.MODEL, max_tokens=max_tokens, system=system,
                                         tools=tools, messages=self._convert(messages), **kw)
        reply = LLMReply()
        for b in resp.content:
            t = getattr(b, "type", None)
            if t == "text":
                reply.text += b.text
            elif t == "tool_use":
                reply.tool_calls.append(ToolCall(b.id, b.name, dict(b.input)))
        return reply


# ------------------------------------------------------------------ Azure OpenAI
class AzureOpenAIAdapter:
    def __init__(self, client=None):
        self._client = client

    def _c(self):
        if self._client is None:
            if not config.llm_configured():
                raise LLMError(config.setup_hint())
            import os
            import openai
            key, endpoint = os.environ["AZURE_OPENAI_API_KEY"], os.environ["AZURE_OPENAI_ENDPOINT"]
            base = v1_base_url(endpoint)
            if base:   # Foundry v1: api-version is not used
                self._client = openai.OpenAI(api_key=key, base_url=base, max_retries=1)
            else:
                self._client = openai.AzureOpenAI(
                    api_key=key, azure_endpoint=normalize_endpoint(endpoint), max_retries=1,
                    api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or "2025-04-01-preview")
        return self._client

    @staticmethod
    def _convert(system: str, messages: list[dict]) -> list[dict]:
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                text = m["content"]
                if m.get("pages"):   # no native PDF input: send page-tagged text
                    text = ("Contract text, page by page (page markers are [PAGE n]):\n\n"
                            + pages_text(m["pages"]) + "\n\n" + text)
                out.append({"role": "user", "content": text})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("text") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": t.id, "type": "function",
                                          "function": {"name": t.name, "arguments": json.dumps(t.args)}}
                                         for t in m["tool_calls"]]
                out.append(msg)
            else:
                for r in m["results"]:
                    out.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
        return out

    def complete(self, system, messages, tools, force_tool=None, max_tokens=1024) -> LLMReply:
        client = self._c()
        _count()
        kw = {"tool_choice": {"type": "function", "function": {"name": force_tool}}} if force_tool else {}
        fn_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                      "parameters": t["input_schema"]}} for t in tools]
        try:
            resp = client.chat.completions.create(
                model=config.MODEL, messages=self._convert(system, messages), tools=fn_tools,
                max_completion_tokens=max_tokens, **kw)
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status is None:
                raise
            raise LLMError(azure_error_hint(status, str(getattr(e, "message", e))[:300])) from e
        msg = resp.choices[0].message
        reply = LLMReply(text=msg.content or "")
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": tc.function.arguments}
            reply.tool_calls.append(ToolCall(tc.id, tc.function.name, args))
        return reply


def get_llm(client=None):
    """client given (tests / injection) -> Anthropic-style client wrapped in the adapter."""
    if client is not None:
        return AnthropicAdapter(client)
    if config.PROVIDER == "azure_openai":
        return AzureOpenAIAdapter()
    if config.PROVIDER == "anthropic":
        return AnthropicAdapter()
    raise LLMError(f"Unknown LLM_PROVIDER '{config.PROVIDER}' (use azure_openai or anthropic).")
