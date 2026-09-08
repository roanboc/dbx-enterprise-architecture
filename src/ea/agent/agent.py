"""An agent that answers questions about the architecture with tools, grounded in what the tools returned.

Two providers: `anthropic` (Claude, tool use) and `stub` (no model; runs a
sensible tool sequence and formats the result), so the app and the tests work
without an API key. The provider is chosen from settings: `auto` picks Claude
when credentials are present.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from ea.agent.tools import ToolBox
from ea.config import Settings
from ea.metamodel.registry import Registry

ID_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,7}-[A-Za-z0-9][A-Za-z0-9-]{1,40}\b")

SYSTEM_PROMPT = """You are the architecture assistant of an enterprise architecture repository.

You answer questions about elements (applications, data entities, information assets, positions, ...) and the relationships between them, using ONLY the tools provided. Rules:
- Every element id, name, count or relationship you state must come from a tool result in this conversation. Never invent ids. If the tools return nothing relevant, say so plainly.
- Start with `search_elements` or `list_types` when you do not know an element's id. Use `impact` for blast-radius questions, `trace` with direction "in" for "what depends on X", `get_element` for ownership and detail, `run_sql` for counts and set questions.
- Cite element ids in square brackets after names, e.g. "Student Records System [PAC-SRS]", so the reader can open them.
- Relationship direction matters: a Data Entity is *processed by* an application and *stored in* a technology component; an Information Asset *has* positions in steward roles; a Logical Data Component *encapsulates* data entities and *categorises* information assets.
- Be concise: lead with the answer, then the supporting elements as a short list, then the completeness caveat from the impact tool when you used it.
- When the answer involves several related elements, call `propose_view` with their ids and a short title so the reader gets an architecture diagram in the answer document; the app draws it from the model.

The loaded metamodel:
"""


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    result_preview: str


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    ungrounded_ids: list[str] = field(default_factory=list)
    error: str = ""


class StubProvider:
    """No language model: runs the obvious tools for a question and reports what they found."""

    name = "stub"

    def answer(self, question: str, toolbox: ToolBox, history: list[dict[str, Any]]) -> AgentResult:
        calls: list[ToolCall] = []

        def run(name: str, **kwargs: Any) -> Any:
            import json

            text = toolbox.call(name, kwargs)
            calls.append(ToolCall(name, kwargs, text[:600]))
            return json.loads(text) if text.startswith("{") else text

        ids = ID_RE.findall(question)
        q = question.lower()
        lines: list[str] = []
        target = ids[0] if ids else None
        if target is None:
            words = [
                w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", question) if w.lower() not in _STOPWORDS
            ]
            best: tuple[tuple[int, int], str] | None = None
            for w in sorted(words, key=len, reverse=True)[:5]:
                res = run("search_elements", text=w, limit=5)
                for m in (res.get("matches") or []) if isinstance(res, dict) else []:
                    name = (m.get("name") or "").lower()
                    # An element the question actually names beats one that only matched a
                    # word in it: "who owns the Course Catalogue" is about the catalogue,
                    # not about the first thing "applications" happened to find.
                    score = (2 if name and name in q else 0, len(name))
                    if best is None or score > best[0]:
                        best = (score, m["element_id"])
            if best is not None:
                target = best[1]
        if target is None:
            res = run("list_types")
            totals = res.get("totals", {}) if isinstance(res, dict) else {}
            lines.append(
                f"I could not match your question to an element. The repository holds {totals.get('elements', '?')} elements and "
                f"{totals.get('relationships', '?')} relationships; try naming an element, or ask with its id."
            )
            return AgentResult("\n".join(lines), calls, self.name, "")
        detail = run("get_element", element_id=target)
        if isinstance(detail, dict) and "error" in detail:
            return AgentResult(detail["error"], calls, self.name, "")
        e = detail["element"]
        lines.append(
            f"**{e['name']} [{e['element_id']}]** — {e.get('type_name', e['type_id'])}, status {e['status']}."
        )
        if any(k in q for k in ("impact", "blast", "depend", "affect", "change", "retire", "decommission")):
            imp = run("impact", element_id=target, max_depth=3)
            up, down = imp["upstream_dependants"], imp["downstream_dependencies"]
            lines.append(
                f"{len(up)} elements depend on it (upstream) and it depends on {len(down)} (downstream)."
            )
            for r in up[:15]:
                lines.append(
                    f"- depends on it: {r['name']} [{r['element_id']}] ({r['type_name']}, {r['depth']} hop{'s' if r['depth'] > 1 else ''} via {' > '.join(r['via'])})"
                )
            for r in down[:10]:
                lines.append(f"- it depends on: {r['name']} [{r['element_id']}] ({r['type_name']})")
            c = imp["completeness"]
            lines.append("")  # a line straight after a bullet is read as part of it
            lines.append(
                f"Completeness: {c['populated']}/{c['declared']} relationship types declared for this element type have instances."
                + (f" No instances yet for: {', '.join(c['empty'])}." if c["empty"] else "")
            )
            run(
                "propose_view",
                title=f"Impact of {e['name']}",
                element_ids=[target]
                + [r["element_id"] for r in up[:20]]
                + [r["element_id"] for r in down[:15]],
            )
        else:
            for r in detail["incoming"][:12]:
                q_ = f" ({r['qualifier']})" if r.get("qualifier") else ""
                lines.append(f"- {r['relationship']}{q_}: {r['name']} [{r['element_id']}]")
            for r in detail["outgoing"][:12]:
                q_ = f" ({r['qualifier']})" if r.get("qualifier") else ""
                lines.append(f"- {r['relationship']}{q_}: {r['name']} [{r['element_id']}]")
            if e.get("description"):
                lines.append("")
                lines.append(e["description"][:600])
            around = [r["element_id"] for r in detail["incoming"][:12]] + [
                r["element_id"] for r in detail["outgoing"][:12]
            ]
            if around:
                run("propose_view", title=f"{e['name']} and its relationships", element_ids=[target] + around)
        lines.append("")
        lines.append(
            "_No language model is configured; this answer was assembled from tool results only. Set ANTHROPIC_API_KEY to enable Claude._"
        )
        return AgentResult("\n".join(lines), calls, self.name, "")


_STOPWORDS = {
    "what",
    "which",
    "who",
    "does",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "are",
    "is",
    "of",
    "on",
    "in",
    "to",
    "about",
    "tell",
    "show",
    "list",
    "give",
    "impact",
    "depends",
    "depend",
    "owns",
    "own",
    "owner",
    "data",
    "element",
    "elements",
}


class AnthropicProvider:
    """Claude with tool use (manual loop, so the app controls every step and never needs a beta)."""

    name = "anthropic"

    def __init__(self, model: str, max_turns: int = 12):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_turns = max_turns

    def answer(self, question: str, toolbox: ToolBox, history: list[dict[str, Any]]) -> AgentResult:
        anthropic = self._anthropic
        messages: list[dict[str, Any]] = list(history) + [{"role": "user", "content": question}]
        calls: list[ToolCall] = []
        system = SYSTEM_PROMPT + toolbox.registry.summary_markdown()
        tools = toolbox.specs()
        response = None
        for _ in range(self.max_turns):
            try:
                response = self._create(system, tools, messages)
            except anthropic.AuthenticationError:
                return AgentResult(
                    "",
                    calls,
                    self.name,
                    self.model,
                    error="Anthropic authentication failed; check ANTHROPIC_API_KEY.",
                )
            except anthropic.RateLimitError as exc:
                return AgentResult(
                    "",
                    calls,
                    self.name,
                    self.model,
                    error=f"Rate limited by the model API ({exc.status_code}); try again shortly.",
                )
            except anthropic.APIStatusError as exc:
                return AgentResult(
                    "",
                    calls,
                    self.name,
                    self.model,
                    error=f"Model API error {exc.status_code}: {exc.message}",
                )
            except anthropic.APIConnectionError as exc:
                return AgentResult(
                    "", calls, self.name, self.model, error=f"Could not reach the model API: {exc}"
                )
            if response.stop_reason == "refusal":
                return AgentResult(
                    "", calls, self.name, self.model, error="The model declined to answer this request."
                )
            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                break
            results = []
            for tu in tool_uses:
                text = toolbox.call(tu.name, dict(tu.input or {}))
                calls.append(ToolCall(tu.name, dict(tu.input or {}), text[:600]))
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": text})
            messages.append({"role": "user", "content": results})
        if response is None:
            return AgentResult("", calls, self.name, self.model, error="no response")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        history[:] = messages  # so a follow-up question keeps the context
        return AgentResult(text, calls, self.name, getattr(response, "model", self.model))

    def _create(self, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]]):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16000,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": tools,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
        }
        try:
            # Server-side refusal fallbacks keep the assistant answering when a safety classifier declines;
            # unsupported SDKs or platforms fall back to the plain endpoint.
            return self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        except (TypeError, self._anthropic.BadRequestError):
            return self.client.messages.create(**kwargs)


class Agent:
    def __init__(self, toolbox: ToolBox, settings: Settings | None = None):
        self.toolbox = toolbox
        self.settings = settings or Settings.from_env()
        self.history: list[dict[str, Any]] = []
        self.provider = self._make_provider()

    def _make_provider(self):
        choice = self.settings.agent_provider
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        if choice == "anthropic" or (choice == "auto" and has_key):
            try:
                return AnthropicProvider(self.settings.agent_model)
            except Exception:  # noqa: BLE001 — missing SDK or credentials; the stub keeps the app usable
                if choice == "anthropic":
                    raise
        return StubProvider()

    def ask(self, question: str) -> AgentResult:
        self.toolbox.seen_ids.clear()
        self.toolbox.requested_views.clear()
        result = self.provider.answer(question, self.toolbox, self.history)
        cited = set(ID_RE.findall(result.answer))
        known_now = {i for i in cited if self.toolbox.backend.get_element(i) is not None}
        result.ungrounded_ids = sorted(
            i for i in cited if i not in self.toolbox.seen_ids and i not in known_now
        )
        return result

    def reset(self) -> None:
        self.history.clear()


def registry_summary(registry: Registry) -> str:
    return registry.summary_markdown()
