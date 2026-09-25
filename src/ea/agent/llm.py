"""The assistant's model: how Ask and Propose reach it (decision 0023).

- `databricks` — a Model Serving endpoint, queried over the chat completions API that every
  model the platform serves speaks, at `<workspace>/serving-endpoints/<endpoint>/invocations`.
  The workspace decides what answers: one model, or several behind the endpoint's AI Gateway
  with traffic splitting and fallbacks; changing it is the workspace's setting, not this code.
  Each request is signed as the app's own identity on Databricks and with the architect's own
  Databricks credentials on a laptop — the Databricks SDK decides which, and renews the token.
- `anthropic` — one provider's own API, directly with a key: for development on a laptop
  without a workspace.
- `stub` — no model: the reader of a template's tables, and the rule-based questions.

`auto` picks the served endpoint when one is configured, the direct API when a key is present,
and no model otherwise. Both hosted ways run the same tool loop over one neutral conversation,
in the chat completions shape; the direct way translates it for its own API.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ea.config import Settings

#: Retries of a request the endpoint was too busy or failed to answer, and the first wait.
MAX_RETRIES = 2
RETRY_BACKOFF = 1.0
SERVED_TIMEOUT = 180.0
#: What a tool is answered with when the model's arguments were not a JSON object.
MALFORMED = '{"error": "the arguments were not a JSON object; call the tool again with one"}'


class ModelUnavailable(RuntimeError):
    """The configured model cannot be reached: said plainly, so the page or the command line shows it."""


class ModelError(RuntimeError):
    """A request the model's service refused or failed, in the words a person reads."""


@dataclass
class ToolUse:
    id: str
    name: str
    arguments: dict[str, Any]
    malformed: bool = False  # the arguments were not a JSON object


@dataclass
class Reply:
    text: str
    tool_uses: list[ToolUse]
    stop: str  # tools | end | length | refused
    model: str
    message: dict[str, Any]  # the model's turn, to append to the conversation


class ChatModel(Protocol):
    provider: str  # databricks | anthropic
    model: str  # the serving endpoint's name, or the direct API's model

    def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        """One request: the conversation so far and the tools on offer, and the model's reply."""


def tool_result(use: ToolUse, content: str) -> dict[str, Any]:
    """A tool's answer, as the conversation's next message."""
    return {"role": "tool", "tool_call_id": use.id, "content": content}


# ------------------------------------------------------------------ choosing


def choice(settings: Settings) -> str:
    """Which way `settings` points at: databricks, anthropic or stub."""
    wanted = (settings.agent_provider or "auto").lower()
    if wanted != "auto":
        return wanted
    if settings.agent_endpoint:
        return "databricks"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    return "stub"


def chat_model(settings: Settings) -> ChatModel | None:
    """The model the settings name, or None for no model.

    Under `auto`, a way that cannot be set up (no SDK, no credentials) falls back to no model,
    so the application stays usable; named explicitly, it raises `ModelUnavailable`.
    """
    way = choice(settings)
    explicit = (settings.agent_provider or "auto").lower() != "auto"
    try:
        if way == "databricks":
            return served_model(
                settings.agent_endpoint, settings.databricks_host, max_tokens=settings.agent_max_tokens
            )
        if way == "anthropic":
            return DirectModel(settings.agent_model)
    except Exception as exc:  # noqa: BLE001 — missing SDK or credentials
        if explicit:
            raise ModelUnavailable(str(exc)) from exc
    return None


# ------------------------------------------------------------ the served way


def served_model(
    endpoint: str,
    host: str = "",
    authenticate: Callable[[], dict[str, str]] | None = None,
    max_tokens: int = 8192,
    http: Any = None,
) -> ServedModel:
    """A Model Serving endpoint of this workspace.

    `authenticate` returns the headers that sign one request; by default the Databricks SDK's,
    which reads the app's service principal on the platform and the architect's own profile
    or token on a laptop. `host` defaults to the SDK's.
    """
    if not endpoint:
        raise ModelUnavailable("no serving endpoint is configured: set EA_AGENT_ENDPOINT")
    if authenticate is None or not host:
        try:
            from databricks.sdk.core import Config
        except ImportError as exc:
            raise ModelUnavailable(
                "the Databricks SDK is not installed: run with the databricks extra "
                "(uv run --extra databricks …)"
            ) from exc
        config = Config(host=host) if host else Config()
        authenticate = authenticate or config.authenticate
        host = host or config.host
    base = host.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    return ServedModel(endpoint, base, authenticate, max_tokens, http)


class ServedModel:
    """A serving endpoint, over the chat completions API every model the platform serves speaks."""

    provider = "databricks"

    def __init__(
        self,
        endpoint: str,
        base_url: str,
        authenticate: Callable[[], dict[str, str]],
        max_tokens: int = 8192,
        http: Any = None,
    ):
        import httpx2

        self.model = endpoint
        self.max_tokens = max_tokens
        self._url = f"{base_url}/serving-endpoints/{endpoint}/invocations"
        self._authenticate = authenticate
        self._http = http or httpx2.Client(timeout=httpx2.Timeout(SERVED_TIMEOUT, connect=15.0))

    def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        body: dict[str, Any] = {
            "messages": [{"role": "system", "content": system}] + [_on_the_wire(m) for m in messages],
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = [_function(t) for t in tools]
        return _reply_from_chat(self._post(body), self.model)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """The request, signed afresh each time, retried when the endpoint is busy or failing."""
        import httpx2

        said = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._http.post(self._url, json=body, headers=dict(self._authenticate()))
            except httpx2.HTTPError as exc:
                said = f"Could not reach the serving endpoint {self.model!r}: {exc}"
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ModelError(
                            f"the serving endpoint {self.model!r} answered with something that is not JSON"
                        ) from exc
                said = self._refused(response)
                if response.status_code not in (429, 500, 502, 503, 504):
                    raise ModelError(said)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * 2**attempt)
        raise ModelError(said)

    def _refused(self, response: Any) -> str:
        where, code = f"the serving endpoint {self.model!r}", response.status_code
        if code in (401, 403):
            return (
                f"{where} refused the request ({code}); check the app may query the endpoint "
                "(CAN_QUERY), or your own Databricks sign-in."
            )
        if code == 404:
            return f"{where} was not found ({code}); check EA_AGENT_ENDPOINT names an endpoint of this workspace."
        if code == 429:
            return f"Rate limited by {where} ({code}); try again shortly."
        return f"{where} answered with error {code}: {_detail(response)}"


def _detail(response: Any) -> str:
    try:
        data = response.json()
    except ValueError:
        return (response.text or "")[:300]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)[:300]
    return str((data.get("message") if isinstance(data, dict) else None) or error or data)[:300]


def _on_the_wire(message: dict[str, Any]) -> dict[str, Any]:
    """A message without what only this side keeps (keys starting with an underscore)."""
    return {k: v for k, v in message.items() if not k.startswith("_")}


def _function(tool: dict[str, Any]) -> dict[str, Any]:
    """A tool as a function the model may call: its name, what it is for, the JSON schema of its arguments."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        },
    }


def _text(content: Any) -> str:
    """A message's text, whether a string or a list of parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text") or "")
    return "".join(parts).strip()


def _reply_from_chat(data: dict[str, Any], endpoint: str) -> Reply:
    choices = data.get("choices") or []
    if not choices:
        raise ModelError(f"the serving endpoint {endpoint!r} returned no answer")
    message = choices[0].get("message") or {}
    finish = choices[0].get("finish_reason") or ""
    text = _text(message.get("content"))
    uses, calls = [], []
    for n, call in enumerate(message.get("tool_calls") or []):
        fn = call.get("function") or {}
        raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            args = None
        use_id = call.get("id") or f"call_{n}"
        uses.append(
            ToolUse(
                use_id,
                fn.get("name") or "",
                args if isinstance(args, dict) else {},
                not isinstance(args, dict),
            )
        )
        calls.append(
            {
                "id": use_id,
                "type": "function",
                "function": {
                    "name": fn.get("name") or "",
                    "arguments": raw if isinstance(raw, str) else json.dumps(raw),
                },
            }
        )
    turn: dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls:
        turn["tool_calls"] = calls
    stop = "tools" if uses else {"length": "length", "content_filter": "refused"}.get(finish, "end")
    return Reply(text, uses, stop, data.get("model") or endpoint, turn)


# ------------------------------------------------------------ the direct way


class DirectModel:
    """One provider's own API, directly with a key: for development without a workspace. The
    neutral conversation is translated for it, and its own turns kept as it wrote them."""

    provider = "anthropic"

    def __init__(self, model: str, client: Any = None, max_tokens: int = 16000):
        import anthropic

        self._sdk = anthropic
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": provider_messages(messages),
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
        }
        if tools:
            kwargs["tools"] = tools
        sdk = self._sdk
        try:
            try:
                # Server-side refusal fallbacks keep the assistant answering when a safety
                # classifier declines; an SDK or platform without them takes the plain request.
                response = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            except (TypeError, sdk.BadRequestError):
                response = self.client.messages.create(**kwargs)
        except sdk.APIError as exc:
            raise ModelError(self._failure(exc)) from exc
        return reply_from_provider(response, self.model)

    def _failure(self, exc: Exception) -> str:
        sdk = self._sdk
        if isinstance(exc, sdk.AuthenticationError | sdk.PermissionDeniedError):
            return f"the model API refused the request ({exc.status_code}); check ANTHROPIC_API_KEY."
        if isinstance(exc, sdk.RateLimitError):
            return f"Rate limited by the model API ({exc.status_code}); try again shortly."
        if isinstance(exc, sdk.APIStatusError):
            return f"the model API answered with error {exc.status_code}: {exc.message}"
        if isinstance(exc, sdk.APIConnectionError):
            return f"Could not reach the model API: {exc}"
        return f"the model API failed: {exc}"


def provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The neutral conversation in the direct API's own shape: a model turn as that API wrote
    it when kept (`_raw`), tool calls as its blocks, and consecutive tool answers as one turn."""
    out: list[dict[str, Any]] = []
    answering = False  # the last turn out holds tool answers, and the next one joins it
    for m in messages:
        role = m.get("role")
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id"),
                "content": m.get("content") or "",
            }
            if answering:
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
                answering = True
            continue
        answering = False
        if role == "assistant":
            if "_raw" in m:
                out.append({"role": "assistant", "content": m["_raw"]})
                continue
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for call in m.get("tool_calls") or []:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append(
                    {"type": "tool_use", "id": call.get("id"), "name": fn.get("name"), "input": args}
                )
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": "user", "content": m.get("content") or ""})
    return out


def reply_from_provider(response: Any, model: str) -> Reply:
    """The direct API's answer as a neutral reply; its own turn kept for the next request."""
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    uses = [ToolUse(b.id, b.name, dict(b.input or {})) for b in response.content if b.type == "tool_use"]
    if response.stop_reason == "refusal":
        stop = "refused"
    elif uses:
        stop = "tools"
    else:
        stop = "length" if response.stop_reason == "max_tokens" else "end"
    turn: dict[str, Any] = {"role": "assistant", "content": text or None, "_raw": response.content}
    if uses:
        turn["tool_calls"] = [
            {
                "id": u.id,
                "type": "function",
                "function": {"name": u.name, "arguments": json.dumps(u.arguments)},
            }
            for u in uses
        ]
    return Reply(text, uses, stop, getattr(response, "model", None) or model, turn)
