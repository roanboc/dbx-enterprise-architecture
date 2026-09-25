"""A deep dive (initiative 25, BPROC3): a brief settled in conversation, then an analysis read top-down.

**The brief.** What the analysis is about, which kind it is, how far it reaches and what it is
for, asked a few questions at a time with the choices the model allows, as Propose asks about
a draft. A choice is applied without a model; the reader's own words are searched as names,
or read by a hosted model when one is configured, which may ask a question of its own.

**The analysis.** Five kinds — impact, landscape, transition, information flow and model
quality — each a bounded read of the store around its subject: at most `MAX_SCOPE` elements
within three steps, walked by the store and never by the in-process graph (decision 0019).
Every element it rests on is given a maturity read from what it carries; where an element and
its documentation disagree is recorded; and seven rules the application already applies give
the findings. A hosted model, when there is one, writes the summary from them, and every
identifier it cites is checked against what the analysis holds (principle P6).

**Top-down.** What is kept reads from the highest level down, in two styles: the context and
the overview are drawn to be presented, the architecture and the detail in the metamodel's own
notation. Every shape that stands for an element carries its identifier (P8); a chart carries
figures only. Nothing here draws: the pack (`ea.views.deep_dive_pack`) draws what is kept.

Nothing here writes. The catalogue (`ea.services.deep_dives`) keeps what `analyse` returns.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

from ea.agent.agent import ID_RE
from ea.agent.llm import MALFORMED, ChatModel, ModelError, tool_result
from ea.agent.questions import (
    LOWER_LAYERS,
    MAX_WALKS,
    MIN_DESCRIPTION_CHARS,
    TRACE_DEPTH,
    UPPER_LAYERS,
)
from ea.agent.tools import ToolBox
from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import (
    DEEP_DIVE_KINDS,
    MATURITY_LEVELS,
    DeepDive,
    DeepDiveElement,
    Element,
    ElementFilter,
    Relationship,
)
from ea.services.deep_dives import DeepDiveService
from ea.services.graph import GraphService
from ea.services.health import STALE_DAYS, _naive
from ea.services.impact import CHANGING, RETIRING
from ea.services.repository import RepositoryService
from ea.services.target import NOT_REAL, TargetStateService
from ea.views.model import (
    DEFAULT_MAX_NODES,
    LAYER_ORDER,
    LAYER_TITLES,
    layer_rank,
    view_of_change,
    view_to_dict,
)

#: What each kind of analysis is called, and the question it answers.
KINDS: dict[str, dict[str, str]] = {
    "impact": {"label": "Impact", "article": "An", "asks": "What happens if this changes or goes?"},
    "landscape": {"label": "Landscape", "article": "A", "asks": "What makes up this area?"},
    "transition": {
        "label": "Transition",
        "article": "A",
        "asks": "What does this work package change, and what does it leave behind?",
    },
    "flow": {
        "label": "Information flow",
        "article": "An",
        "asks": "Where does this information come from, and where does it go?",
    },
    "quality": {
        "label": "Model quality",
        "article": "A",
        "asks": "How far can what the repository says about this area be trusted?",
    },
}
assert list(KINDS) == DEEP_DIVE_KINDS
#: Words that point at a kind of analysis. The more specific kinds are tried first on a tie.
KIND_HINTS: dict[str, tuple[str, ...]] = {
    "transition": ("work package", "upgrade", "project", "roadmap", "migrat", "transition", "target state"),
    "flow": ("flow", "lineage", "come from", "comes from", "consume", "feeds", "where does", "master"),
    "quality": ("quality", "trust", "maturity", "complete", "consisten", "reliab", "accura"),
    "landscape": ("landscape", "overview", "made up", "makes up", "what is in", "area", "map of"),
    "impact": (
        "impact",
        "happens if",
        "retire",
        "decommission",
        "replace",
        "remove",
        "switch off",
        "break",
        "depend",
        "affect",
        "blast",
    ),
}
REACHES = {1: "one step", 2: "two steps", 3: "three steps"}
MAX_REACH = max(REACHES)
#: The most elements one analysis reads — within what a quick answer may read (decision 0019).
MAX_SCOPE = 120
MAX_SUBJECT = 5
MAX_CANDIDATES = 5
#: The key elements drawn up close at level 4.
MAX_KEY = 3
#: Upper-layer elements the context map shows around the subject, per group.
MAX_CONTEXT = 8
#: How recently an approved element must have been refreshed to be current.
RECENT_DAYS = STALE_DAYS[-1]
#: How many elements must depend on one directly for it to be a single point of dependency.
SINGLE_POINT_MIN = 5
SINGLE_POINT_HIGH = 8
#: The findings a reader is shown first, on the page that opens the deep dive.
HEADLINE = 3
SEVERITIES = ("high", "medium", "low")
#: The seven rules, in the order they are stated (and a tie is broken in).
RULES = (
    "single_point",
    "retiring",
    "outside_package",
    "untraced",
    "empty_relationship",
    "documentation",
    "maturity",
)
#: Who is concerned, by what the notation says an element is.
PEOPLE = ("BusinessActor", "BusinessRole", "BusinessCollaboration", "Stakeholder")
LEVELS = (
    (1, "Context", "presentation"),
    (2, "Overview", "presentation"),
    (3, "Architecture", "architecture"),
    (4, "Detail", "architecture"),
)
_URL = re.compile(r"^https?://[^\s/]+\.[^\s]+$")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "about", "what", "which",
    "who", "does", "do", "is", "are", "if", "we", "it", "its", "this", "that", "tell", "me", "show",
    "happens", "whether", "can", "be", "how", "far", "our", "from", "into", "by", "at", "as",
}  # fmt: skip


# ------------------------------------------------------------------ the brief
@dataclass
class Brief:
    """What a deep dive is to answer, settled with the reader before anything is analysed."""

    question: str = ""
    subject: list[str] = field(default_factory=list)  # element identifiers
    work_package: str = ""
    kind: str = ""  # one of DEEP_DIVE_KINDS; a guess until `kind` is in `settled`
    reach: int = 2
    layers: list[str] = field(default_factory=list)  # empty: every layer
    purpose: str = ""
    settled: list[str] = field(default_factory=list)  # the questions the reader has answered
    asked: str = ""  # a question the model asked in its own words
    note: str = ""  # what the last answer could not do, in words
    from_deep_dive: str = ""  # the deep dive this one runs again

    def ready(self) -> bool:
        return bool((self.subject or self.work_package) and self.kind in KINDS)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Brief:
        d = d or {}
        known = {f.name for f in fields(cls)}
        b = cls(**{k: v for k, v in d.items() if k in known})
        b.subject, b.layers, b.settled = list(b.subject or []), list(b.layers or []), list(b.settled or [])
        b.reach = _reach(b.reach)
        return b


@dataclass
class BriefQuestion:
    """One question of the brief. An option's `needs` says what the reader adds: nothing, or `text`."""

    qid: str
    text: str
    options: list[dict[str, str]] = field(default_factory=list)
    answer: str = ""  # the current answer, in words
    settled: bool = False
    free: bool = False  # the reader may answer in their own words
    optional: bool = False
    multi: bool = False
    asked_by: str = "rules"  # rules | assistant

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reach(value: Any) -> int:
    return max(1, min(MAX_REACH, int(value or 2)))


def _stem(word: str) -> str:
    word = word.lower()
    if len(word) > 4 and word.endswith("s"):
        word = word[:-1]
    return word[:6] if len(word) > 6 else word


def _words(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 1}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def guess_kind(text: str) -> str:
    """The kind the reader's words point to, or '' when they point nowhere."""
    low = (text or "").lower()
    scores = {k: sum(1 for h in hints if h in low) for k, hints in KIND_HINTS.items()}
    best = max(scores.values())
    return next((k for k, s in scores.items() if s == best), "") if best else ""


def confidence(levels: list[int]) -> dict[str, Any]:
    """How far findings resting on elements of these maturities can be trusted."""
    if not levels:
        return {"level": "low", "average": 0.0, "low_share": 1.0, "text": "Low: nothing was read to rest on."}
    average = round(sum(levels) / len(levels), 1)
    low_share = sum(1 for v in levels if v <= 2) / len(levels)
    pct = round(100 * low_share)
    if average < 2.5 or low_share >= 0.5:
        level = "low"
        text = (
            f"Low: {pct}% of what it rests on is named or described only, so read its findings as "
            "leads to check rather than facts."
        )
    elif average >= 3.5 and low_share < 0.25:
        level = "high"
        text = "High: most of what it rests on is described, related to what it serves, and approved."
    else:
        level = "medium"
        text = (
            f"Medium: the average maturity is {average} of 5, and {pct}% of what it rests on is named "
            "or described only."
        )
    return {"level": level, "average": average, "low_share": round(low_share, 2), "text": text}


# --------------------------------------------------------------- the analysis
@dataclass
class _Area:
    """What one analysis read: the scope, the walks that found it, and what it touches."""

    subject: list[str]
    work_package: str = ""
    scope: list[str] = field(default_factory=list)  # ordered, subject first; at most MAX_SCOPE
    depth: dict[str, int] = field(default_factory=dict)
    up: dict[str, int] = field(default_factory=dict)  # trace in: depends on it
    down: dict[str, int] = field(default_factory=dict)  # trace out: it depends on
    paths: dict[str, list[str]] = field(default_factory=dict)
    members: list[str] = field(default_factory=list)  # a work package's own elements
    outside: dict[str, str] = field(default_factory=dict)  # reached outside it → via which member
    context: dict[str, int] = field(default_factory=dict)  # upper-layer elements around the subject
    truncated: bool = False


class DeepDiveAnalyst:
    """Settles a brief with a reader and analyses it. Reads only; `DeepDiveService` keeps the result."""

    def __init__(
        self,
        backend: DatabaseBackend,
        registry: Registry,
        model: ChatModel | None = None,
        now: datetime | None = None,
        dives: DeepDiveService | None = None,
    ):
        self.backend, self.registry, self.model = backend, registry, model
        self.graph = GraphService(backend, registry)
        self.target = TargetStateService(backend, registry)
        self.dives = dives or DeepDiveService(backend, registry)
        self._pinned = now

    @property
    def now(self) -> datetime:
        return self._pinned or datetime.now(UTC).replace(tzinfo=None)

    # ------------------------------------------------------------ lookups
    def layer(self, type_id: str) -> str:
        return self.registry.notation(type_id).get("layer", "other")

    def _type_name(self, type_id: str) -> str:
        t = self.registry.get_type(type_id)
        return t.name if t else type_id

    def _wp_type(self) -> str:
        return self.target.work_package_type() or ""

    def _named(self, ids: list[str]) -> list[str]:
        held = {e.element_id: e for e in self.backend.elements_by_ids(ids)}
        return [f"{held[i].name} [{i}]" for i in ids if i in held]

    # ============================================================ the brief
    def start(self, question: str) -> Brief:
        """A brief from the reader's first words: what they name, and the kind they point to."""
        brief = Brief(question=(question or "").strip())
        if self.model is not None:
            return self._model_read(brief, brief.question)
        self._apply_words(brief, brief.question, guess=True)
        return brief

    def _apply_words(self, brief: Brief, words: str, guess: bool) -> bool:
        """Identifiers in the words, else the element the words name best. True when found."""
        ids = self._existing(ID_RE.findall(words or ""))
        if not ids and not guess:
            best = self._candidates(words)[:1]
            ids = [e.element_id for e in best]
        wp_type = self._wp_type()
        held = {e.element_id: e for e in self.backend.elements_by_ids(ids)}
        packages = [i for i in ids if i in held and held[i].type_id == wp_type]
        subject = [i for i in ids if i in held and i not in packages][:MAX_SUBJECT]
        if guess and not brief.kind:
            brief.kind = guess_kind(words)
        if packages and not subject:
            brief.work_package, brief.subject = packages[0], []
            if not brief.kind and "kind" not in brief.settled:
                brief.kind = "transition"
        elif subject:
            brief.subject, brief.work_package = subject, ""
        else:
            return False
        if "subject" not in brief.settled:
            brief.settled.append("subject")
        return True

    def _existing(self, ids: list[str]) -> list[str]:
        wanted = list(dict.fromkeys(ids))
        held = {e.element_id for e in self.backend.elements_by_ids(wanted)}
        return [i for i in wanted if i in held]

    def _candidates(self, text: str) -> list[Element]:
        """The elements the words most likely mean: the most of an element's name the words hold."""
        said = _words(text)
        if not said:
            return []
        looked: dict[str, Element] = {}
        for w in sorted({w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}, key=len)[
            ::-1
        ][:6]:
            for e in self.backend.find_elements(ElementFilter(text=w), limit=20):
                looked.setdefault(e.element_id, e)
        scored = []
        for e in looked.values():
            name = _words(e.name)
            hit = len(name & said)
            if hit:
                scored.append(((-hit, -hit / len(name), len(e.name), e.element_id), e))
        return [e for _, e in sorted(scored, key=lambda s: s[0])][:MAX_CANDIDATES]

    def questions(self, brief: Brief) -> list[BriefQuestion]:
        """What the brief asks, top-down: what it is about, which kind, how far, which layers, what for."""
        out = [self._subject_question(brief), self._kind_question(brief)]
        out.append(
            BriefQuestion(
                "reach",
                "How far should it reach from the subject?",
                [{"key": str(n), "label": words.capitalize(), "needs": ""} for n, words in REACHES.items()],
                answer=REACHES[brief.reach].capitalize(),
                settled="reach" in brief.settled,
            )
        )
        present = [
            lv for lv in LAYER_ORDER if any(self.layer(t.id) == lv for t in self.registry.concrete_types())
        ]
        out.append(
            BriefQuestion(
                "layers",
                "Which layers should it cover?",
                [{"key": "all", "label": "Every layer", "needs": ""}]
                + [{"key": lv, "label": LAYER_TITLES[lv], "needs": ""} for lv in present],
                answer=_join([LAYER_TITLES[lv] for lv in brief.layers]) or "Every layer",
                settled="layers" in brief.settled,
                multi=True,
            )
        )
        out.append(
            BriefQuestion(
                "purpose",
                "What is it for? The decision it supports orders what you are told first.",
                [
                    {"key": "text", "label": "In my own words", "needs": "text"},
                    {"key": "skip", "label": "No particular decision", "needs": ""},
                ],
                answer=brief.purpose,
                settled="purpose" in brief.settled,
                free=True,
                optional=True,
            )
        )
        if brief.asked:
            out.append(
                BriefQuestion(
                    "assistant",
                    brief.asked,
                    [{"key": "text", "label": "Answer", "needs": "text"}],
                    free=True,
                    optional=True,
                    asked_by="assistant",
                )
            )
        return out

    def _subject_question(self, brief: Brief) -> BriefQuestion:
        wp_type = self._wp_type()
        options: list[dict[str, str]] = []
        current = brief.subject or ([brief.work_package] if brief.work_package else [])
        seen: set[str] = set()

        def offer(e: Element) -> None:
            if e.element_id in seen:
                return
            seen.add(e.element_id)
            key = ("wp:" if e.type_id == wp_type else "el:") + e.element_id
            options.append(
                {
                    "key": key,
                    "label": f"{e.name} [{e.element_id}] — {self._type_name(e.type_id)}",
                    "needs": "",
                }
            )

        for e in self.backend.elements_by_ids(current):
            offer(e)
        for e in self._candidates(brief.question):
            offer(e)
        if brief.kind == "transition" and not brief.work_package and wp_type:
            for e in self.backend.find_elements(
                ElementFilter(type_ids=[wp_type], sort="name"), limit=MAX_CANDIDATES
            ):
                offer(e)
        options.append({"key": "other", "label": "Something else — name it", "needs": "text"})
        return BriefQuestion(
            "subject",
            "What should the analysis be about?",
            options,
            answer=_join(self._named(current)),
            settled="subject" in brief.settled and bool(current),
            free=True,
        )

    def _kind_question(self, brief: Brief) -> BriefQuestion:
        first = brief.kind or guess_kind(brief.question)
        order = ([first] if first else []) + [k for k in KINDS if k != first]
        return BriefQuestion(
            "kind",
            "Which kind of analysis?",
            [{"key": k, "label": f"{KINDS[k]['label']} — {KINDS[k]['asks']}", "needs": ""} for k in order],
            answer=KINDS[brief.kind]["label"] if brief.kind in KINDS else "",
            settled="kind" in brief.settled,
        )

    def answer(self, brief: Brief, qid: str, key: str, text: str = "") -> Brief:
        """The brief with one answer applied. Raises ValueError on a choice the question does not offer."""
        b = Brief.from_dict(brief.to_dict())
        b.note = ""
        if qid == "subject":
            if key.startswith("el:"):
                b.subject, b.work_package = self._existing([key[3:]]), ""
            elif key.startswith("wp:"):
                b.work_package, b.subject = key[3:], []
                if "kind" not in b.settled:
                    b.kind = "transition"
            elif key == "other":
                if self.model is not None:
                    return self._model_read(b, text)
                if not self._apply_words(b, text, guess=False):
                    b.note = f"Nothing in the model is named like “{text.strip()}”; try another name or an identifier."
                    return b
            else:
                raise ValueError(f"not a subject: {key}")
            if not (b.subject or b.work_package):
                b.note = "That element is not in the model."
                return b
        elif qid == "kind":
            if key not in KINDS:
                raise ValueError(f"the kind of analysis is one of {', '.join(KINDS)}")
            b.kind = key
        elif qid == "reach":
            b.reach = _reach(key)
        elif qid == "layers":
            picked = [p.strip() for p in (key or "").split(",") if p.strip()]
            if "all" in picked:
                b.layers = []
            else:
                unknown = [p for p in picked if p not in LAYER_ORDER]
                if unknown:
                    raise ValueError(f"not a layer: {', '.join(unknown)}")
                b.layers = sorted(set(picked), key=layer_rank)
        elif qid == "purpose":
            b.purpose = "" if key == "skip" else (text or "").strip()
        elif qid == "assistant":
            b.asked = ""
            if self.model is not None:
                return self._model_read(b, text)
        else:
            raise ValueError(f"not a question of the brief: {qid}")
        if qid not in b.settled:
            b.settled.append(qid)
        return b

    def sentence(self, brief: Brief) -> str:
        """The brief as one sentence, as the reader sees it before the deep dive is written."""
        kind = KINDS.get(brief.kind)
        head = (
            f"{kind['article']} {kind['label'].lower()} analysis"
            if kind
            else "An analysis (kind still to choose)"
        )
        if brief.work_package and not brief.subject:
            what = f"the work package {_join(self._named([brief.work_package])) or brief.work_package}"
        else:
            what = _join(self._named(brief.subject)) or "an element still to choose"
        layers = [LAYER_TITLES[lv].lower() for lv in brief.layers if lv in LAYER_TITLES]
        across = f"the {_join(layers)} layer{'s' if len(layers) > 1 else ''}" if layers else "every layer"
        out = f"{head} of {what}, {REACHES[brief.reach]} out, across {across}."
        if brief.purpose:
            out += f" For: {brief.purpose.rstrip('.')}."
        return out

    def earlier(self, brief: Brief, limit: int = 5) -> list[DeepDive]:
        """The kept deep dives on the same elements, best rated first — one may already answer it."""
        ids = brief.subject or ([brief.work_package] if brief.work_package else [])
        return self.dives.earlier(ids, limit) if ids else []

    def again(self, d: DeepDive) -> Brief:
        """The brief of a kept deep dive, to run it again: a new one, which names the one it came from."""
        b = Brief.from_dict(d.brief)
        b.from_deep_dive, b.note, b.asked = d.deep_dive_id, "", ""
        for q in ("subject", "kind"):
            if q not in b.settled:
                b.settled.append(q)
        return b

    # ======================================================== the analysis
    def analyse(self, brief: Brief) -> DeepDive:
        """The deep dive the brief asks for, ready to keep. Raises ValueError on a brief not ready."""
        if not brief.ready():
            raise ValueError("the brief needs what the analysis is about and which kind it is")
        steps: list[dict[str, str]] = []
        area = self._area(brief, steps)
        els, rels = self._read(area, steps)
        links = {i: self.backend.get_links(i) for i in area.scope}
        adjacency = self._adjacency(rels)
        traced, walks = self._traced(els, adjacency)
        maturity = {i: self._maturity(els[i], adjacency, links.get(i, []), traced.get(i)) for i in els}
        inconsistencies = self._inconsistencies(area, els, rels, links)
        findings = self._findings(brief, area, els, rels, adjacency, maturity, traced, inconsistencies)
        key = self._key(area, findings, adjacency)
        detail = self._detail(key, els, maturity, adjacency, traced, steps)
        steps.append(
            {"tool": "trace up", "detail": f"{walks} walk(s) through the store to test principle P9"}
        )
        rows = self._rows(area, els, maturity, findings)
        levels = self._levels(brief, area, els, rels, rows, findings, detail)
        levels_scope = [maturity[i][0] for i in area.scope if i in maturity]
        conf = confidence(levels_scope)
        headline = self._headline(findings, brief.purpose)
        content: dict[str, Any] = {
            "question": brief.question,
            "brief_sentence": self.sentence(brief),
            "purpose": brief.purpose,
            "subject_ids": list(area.subject),
            "work_package": area.work_package,
            "confidence": conf,
            "headline": headline,
            "elements": rows,
            "levels": levels,
            "findings": findings,
            "inconsistencies": inconsistencies,
            "references": self._references(brief, area, key),
            "key_ids": key,
            "read": {
                "elements": len(area.scope),
                "relationships": len([r for r in rels if r.src_id in area.scope and r.dst_id in area.scope]),
                "truncated": area.truncated,
                "reach": brief.reach,
                "layers": list(brief.layers),
            },
            "as_of": self.now.isoformat(timespec="minutes"),
            "trace": {"steps": steps, "ungrounded": [], "provider": "rules", "model": "", "model_error": ""},
        }
        content["summary"] = self._rules_summary(brief, content)
        if self.model is not None:
            self._model_summary(content)
        subject = area.subject or ([area.work_package] if area.work_package else [])
        cited = {i for f in findings for i in f["elements"]}
        elements = [
            DeepDiveElement(
                i,
                "subject" if i in subject else ("finding" if i in cited else "drawn"),
                maturity[i][0],
            )
            for i in rows
        ]
        wp = area.work_package or next((els[i].target_work_package for i in area.subject if i in els), "")
        return DeepDive(
            title=self._title(brief, area, els),
            kind=brief.kind,
            brief=brief.to_dict(),
            content=content,
            work_package=wp or "",
            elements=elements,
        )

    # ------------------------------------------------------------ the area
    def _work_package(self, brief: Brief) -> str:
        if brief.work_package:
            return brief.work_package
        wp_type = self._wp_type()
        for e in self.backend.elements_by_ids(brief.subject):
            if e.type_id == wp_type:
                return e.element_id
            if e.target_work_package:
                return e.target_work_package
        return ""

    def _area(self, brief: Brief, steps: list[dict[str, str]]) -> _Area:
        subject = self._existing(brief.subject)[:MAX_SUBJECT]
        area = _Area(subject=subject)
        reach = brief.reach
        found: dict[str, int] = {}

        def reached(rows: list[dict[str, Any]], into: dict[str, int] | None = None) -> None:
            for r in rows:
                nid, d = r["element_id"], int(r["depth"])
                if nid in subject:
                    continue
                if nid not in found or d < found[nid]:
                    found[nid] = d
                    area.paths[nid] = list(r.get("path") or [])
                if into is not None and (nid not in into or d < into[nid]):
                    into[nid] = d

        if brief.kind == "transition":
            wp = self._work_package(brief)
            if not wp:
                raise ValueError(
                    "a transition analysis needs a work package: pick one, or an element it changes"
                )
            area.work_package = wp
            members = [wp] + [
                e.element_id
                for e in self.backend.find_elements(
                    ElementFilter(work_packages=[wp], sort="name"), limit=MAX_SCOPE
                )
                if e.element_id != wp
            ]
            area.members = members
            held = {e.element_id: e for e in self.backend.elements_by_ids(members)}
            steps.append({"tool": "work package", "detail": f"{wp}: {len(members) - 1} element(s) it names"})
            for m in members[1:]:
                e = held.get(m)
                if e is None or e.target_state not in (*CHANGING, "new"):
                    continue
                for rel in self.backend.relationships_of(m, "both"):
                    other = rel.dst_id if rel.src_id == m else rel.src_id
                    if other not in held and other not in area.outside:
                        area.outside[other] = m
            steps.append(
                {
                    "tool": "relationships",
                    "detail": f"what the changing elements touch: {len(area.outside)} outside",
                }
            )
            for i in members:
                found.setdefault(i, 0 if i == wp else 1)
            for i in area.outside:
                found.setdefault(i, 2)
        else:
            for s in subject:
                if brief.kind in ("impact", "flow"):
                    up, down = self.backend.trace(s, "in", reach), self.backend.trace(s, "out", reach)
                    reached(up, area.up)
                    reached(down, area.down)
                    steps.append(
                        {
                            "tool": "trace",
                            "detail": f"{s}: {len(up)} upstream and {len(down)} downstream within {reach}",
                        }
                    )
                else:
                    rows = self.backend.trace(s, "both", reach)
                    reached(rows)
                    steps.append(
                        {"tool": "trace", "detail": f"{s}: {len(rows)} within {reach} step(s), both ways"}
                    )
        # the upper layers around the subject: what it serves, and who is concerned
        centre = subject or ([area.work_package] if area.work_package else [])
        for s in centre[:MAX_SUBJECT]:
            rows = self.backend.trace(s, "both", MAX_REACH)
            for r in rows:
                nid = r["element_id"]
                if nid not in area.context or int(r["depth"]) < area.context[nid]:
                    area.context[nid] = int(r["depth"])
                    area.paths.setdefault(nid, list(r.get("path") or []))
            steps.append(
                {"tool": "trace", "detail": f"{s}: its context, {len(rows)} within {MAX_REACH} steps"}
            )
        ordered = sorted(found, key=lambda i: (found[i], i))
        if brief.layers:
            kinds = {e.element_id: e.type_id for e in self.backend.elements_by_ids(ordered)}
            ordered = [
                i
                for i in ordered
                if i == area.work_package or (i in kinds and self.layer(kinds[i]) in brief.layers)
            ]
        head = [i for i in ([area.work_package] if area.work_package else []) + subject]
        rest = [i for i in ordered if i not in head]
        area.truncated = len(head) + len(rest) > MAX_SCOPE
        area.scope = list(dict.fromkeys(head + rest))[:MAX_SCOPE]
        area.depth = {i: found.get(i, 0) for i in area.scope}
        kept = set(area.scope)
        area.up = {i: d for i, d in area.up.items() if i in kept}
        area.down = {i: d for i, d in area.down.items() if i in kept}
        area.outside = {i: v for i, v in area.outside.items() if i in kept}
        return area

    def _read(
        self, area: _Area, steps: list[dict[str, str]]
    ) -> tuple[dict[str, Element], list[Relationship]]:
        """Every element the deep dive draws, and the relationships among them, in one read each."""
        wanted = list(area.scope)
        ups = [i for i in area.context if i not in area.scope]
        held = {e.element_id: e for e in self.backend.elements_by_ids(ups)}
        upper = sorted(
            (i for i in ups if i in held and self.layer(held[i].type_id) in UPPER_LAYERS),
            key=lambda i: (area.context[i], i),
        )[: MAX_CONTEXT * 3]
        area.context = {i: area.context[i] for i in upper}
        paths = [n for i in upper for n in area.paths.get(i, [])]
        wanted = list(dict.fromkeys(wanted + upper + paths))
        els = {e.element_id: e for e in self.backend.elements_by_ids(wanted)}
        rels = self.backend.edges_among(list(els))
        steps.append(
            {"tool": "read", "detail": f"{len(els)} element(s) and {len(rels)} relationship(s) among them"}
        )
        return els, rels

    @staticmethod
    def _adjacency(rels: list[Relationship]) -> dict[str, dict[str, set[str]]]:
        out: dict[str, set[str]] = {}
        inc: dict[str, set[str]] = {}
        for r in rels:
            out.setdefault(r.src_id, set()).add(r.dst_id)
            inc.setdefault(r.dst_id, set()).add(r.src_id)
        return {"out": out, "in": inc}

    # ------------------------------------------------------- maturity
    def _traced(
        self,
        els: dict[str, Element],
        adjacency: dict[str, dict[str, set[str]]],
        budget: list[int] | None = None,
    ) -> tuple[dict[str, bool | None], int]:
        """Principle P9 for every element below the business layer: does it trace up?

        First over what was read — one direction at a time, `TRACE_DEPTH` steps, as Propose
        tests it — then, for what that does not settle, by the store's walk, at most
        `MAX_WALKS` of them. What is past the budget is not known, and is neither a finding nor
        held against the element's maturity.
        """
        budget = budget if budget is not None else [MAX_WALKS]
        out: dict[str, bool | None] = {}
        walks = 0
        for i, e in els.items():
            if self.layer(e.type_id) not in LOWER_LAYERS:
                continue
            hit = False
            for direction in ("out", "in"):
                frontier, seen = {i}, {i}
                for _ in range(TRACE_DEPTH):
                    frontier = {n for f in frontier for n in adjacency[direction].get(f, set())} - seen
                    seen |= frontier
                    if any(n in els and self.layer(els[n].type_id) in UPPER_LAYERS for n in frontier):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                out[i] = True
                continue
            if budget[0] <= 0:
                out[i] = None
                continue
            budget[0] -= 1
            walks += 1
            reached: list[str] = []
            for direction in ("out", "in"):
                reached += [r["element_id"] for r in self.backend.trace(i, direction, TRACE_DEPTH)]
            out[i] = any(self.layer(x.type_id) in UPPER_LAYERS for x in self.backend.elements_by_ids(reached))
        return out, walks

    def _maturity(
        self,
        e: Element,
        adjacency: dict[str, dict[str, set[str]]],
        links: list[Any],
        traced: bool | None,
    ) -> tuple[int, str]:
        """(level, why): 1 Named, 2 Described, 3 Related, 4 Approved, 5 Current — each needs the last."""
        missing: list[str] = []
        text = (e.description_md or "").strip()
        required = [a.name for a in self.registry.attributes_for(e.type_id) if a.required]
        empty = [a for a in required if e.attrs.get(a) in (None, "")]
        broken = _link_problems(links)
        if len(text) < MIN_DESCRIPTION_CHARS:
            missing.append("no description" if not text else "a description too short to say what it is")
        if empty:
            missing.append(f"{_join(empty)} not filled in")
        if broken:
            missing.append("a broken or repeated link")
        described = not missing
        degree = len(adjacency["out"].get(e.element_id, set()) | adjacency["in"].get(e.element_id, set()))
        if degree == 0 and not self.backend.relationships_of(e.element_id, "both"):
            related, why_not = False, "related to nothing"
        elif traced is False:
            related, why_not = False, "traces up to nothing in the business or the strategy"
        else:
            related, why_not = True, ""
        approved = e.status == "approved"
        updated = _naive(e.updated_at)
        age = (self.now - updated).days if updated else None
        current = age is not None and age < RECENT_DAYS
        level = 1
        if described:
            level = 2
            if related:
                level = 3
                if approved:
                    level = 4
                    if current:
                        level = 5
        if level == 1:
            why = f"Named only: {_join(missing)}."
        elif level == 2:
            why = f"Described, but {why_not}."
        elif level == 3:
            why = f"Described and related, but {'still a draft' if e.status == 'draft' else 'retired'}."
        elif level == 4:
            why = (
                f"Approved, but not refreshed for {age} days."
                if age is not None
                else "Approved, but when it was last refreshed is not recorded."
            )
        else:
            why = f"Described, related and approved, and refreshed {age} day(s) ago."
        return level, why

    # ------------------------------------------------ inconsistencies
    def _inconsistencies(
        self,
        area: _Area,
        els: dict[str, Element],
        rels: list[Relationship],
        links: dict[str, list[Any]],
    ) -> list[dict[str, Any]]:
        """Where an element and what the repository holds about it disagree, within what was read."""
        out: list[dict[str, Any]] = []
        scope = [i for i in area.scope if i in els]
        joined = {frozenset((r.src_id, r.dst_id)) for r in rels}

        def add(rule: str, element_id: str, text: str, other_id: str = "") -> None:
            out.append({"rule": rule, "element_id": element_id, "other_id": other_id, "text": text})

        # the description names an element nothing joins it to
        patterns = []
        for o in scope:
            e = els[o]
            pieces = [re.escape(o)]
            if e.key and e.key != o and len(e.key) >= 4:
                pieces.append(re.escape(e.key))
            if len(_WORD.findall(e.name.lower())) >= 2:
                pieces.append(re.escape(e.name.lower()))
            patterns.append(
                (o, re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(pieces) + r")(?![A-Za-z0-9])", re.I))
            )
        for i in scope:
            text = els[i].description_md or ""
            if not text:
                continue
            spans = [(m.start(), m.end(), o) for o, pattern in patterns for m in pattern.finditer(text)]
            # a name inside a longer name the text uses is that longer name's, not a mention of its own
            mentioned = {
                o
                for a, b, o in spans
                if not any(x <= a and b <= y and (y - x) > (b - a) and p != o for x, y, p in spans)
            }
            for o in sorted(mentioned):
                if o != i and frozenset((i, o)) not in joined:
                    add(
                        "names_unrelated",
                        i,
                        f"{els[i].name} [{i}] says it concerns {els[o].name} [{o}], and no relationship joins them.",
                        o,
                    )
        # a state contradicts the relationships
        for r in rels:
            if r.src_id not in els or r.dst_id not in els:
                continue
            if r.src_id not in area.scope and r.dst_id not in area.scope:
                continue
            if r.current_state == "retired" or r.target_state == "decommission" or r.status == "retired":
                continue
            for a, b in ((r.src_id, r.dst_id), (r.dst_id, r.src_id)):
                ea, eb = els[a], els[b]
                if ea.current_state == "live" and (eb.current_state == "retired" or eb.status == "retired"):
                    if ea.status != "retired":
                        add(
                            "state",
                            a,
                            f"{ea.name} [{a}] is live and still related to {eb.name} [{b}], which is retired.",
                            b,
                        )
                if ea.target_state == "new" and eb.target_state in RETIRING:
                    add(
                        "state",
                        a,
                        f"{ea.name} [{a}] is planned as new, and related to {eb.name} [{b}], which is to be "
                        f"{'decommissioned' if eb.target_state == 'decommission' else 'merged'}.",
                        b,
                    )
        # the status contradicts the documentation
        for i in scope:
            e = els[i]
            if e.status == "approved" and not (e.description_md or "").strip():
                add("status", i, f"{e.name} [{i}] is approved, and nothing is written about it.")
            if e.status == "retired" and e.current_state == "live":
                add("status", i, f"{e.name} [{i}] is retired as a record, and recorded as live.")
        # a link is malformed, or the same page is linked twice
        for i in scope:
            for problem in _link_problems(links.get(i, [])):
                add("link", i, f"{els[i].name} [{i}]: {problem}.")
        return out

    # ------------------------------------------------------ findings
    def _findings(
        self,
        brief: Brief,
        area: _Area,
        els: dict[str, Element],
        rels: list[Relationship],
        adjacency: dict[str, dict[str, set[str]]],
        maturity: dict[str, tuple[int, str]],
        traced: dict[str, bool | None],
        inconsistencies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        scope = [i for i in area.scope if i in els]
        in_scope = set(scope)
        subject = set(area.subject) | ({area.work_package} if area.work_package else set())

        def name(i: str) -> str:
            return f"{els[i].name} [{i}]" if i in els else i

        def add(
            rule: str, severity: str, title: str, text: str, elements: list[str], why: str, level: int
        ) -> None:
            found.append(
                {
                    "rule": rule,
                    "severity": severity,
                    "title": title,
                    "text": text,
                    "elements": [i for i in dict.fromkeys(elements) if i in els],
                    "why": why,
                    "level": level,
                }
            )

        # 1. many elements depend on one
        points = []
        for i in scope:
            # a work package that plans a change to it does not depend on it
            dependants = sorted(
                n
                for n in adjacency["in"].get(i, set())
                if n in in_scope and self.layer(els[n].type_id) != "implementation"
            )
            if len(dependants) >= SINGLE_POINT_MIN:
                points.append((i, dependants))
        for i, dependants in sorted(points, key=lambda p: (-len(p[1]), p[0]))[:MAX_KEY]:
            add(
                "single_point",
                "high" if len(dependants) >= SINGLE_POINT_HIGH else "medium",
                f"{name(i)} is a single point of dependency",
                f"{len(dependants)} elements in the area read depend on it directly: "
                f"{_join([name(n) for n in dependants[:8]])}{' and more' if len(dependants) > 8 else ''}.",
                [i, *dependants],
                "A change to it, or its loss, reaches every one of them at once.",
                3,
            )
        # 2. something depends on an element that is retired or being decommissioned
        for i in scope:
            e = els[i]
            going = e.target_state in RETIRING
            gone = e.current_state == "retired" or e.status == "retired"
            if not (going or gone):
                continue
            left = []
            for r in rels:
                if (
                    i not in (r.src_id, r.dst_id)
                    or r.target_state in RETIRING
                    or r.current_state == "retired"
                ):
                    continue
                other = r.dst_id if r.src_id == i else r.src_id
                o = els.get(other)
                if o is None or o.target_state in RETIRING or o.current_state == "retired":
                    continue
                left.append(other)
            if left:
                state = (
                    "retired"
                    if gone
                    else ("being decommissioned" if e.target_state == "decommission" else "being merged")
                )
                add(
                    "retiring",
                    "high",
                    f"{len(left)} element(s) stay related to {name(i)}, which is {state}",
                    f"{_join([name(n) for n in sorted(set(left))])} "
                    f"{'is' if len(set(left)) == 1 else 'are'} still related to it, and nothing retires the relationship.",
                    [i, *sorted(set(left))],
                    "When it goes, what still relates to it is left depending on nothing.",
                    3,
                )
        # 3. a change reaches elements outside its work package
        if area.work_package and area.outside:
            via = sorted(set(area.outside.values()))
            add(
                "outside_package",
                "medium",
                f"The change reaches {len(area.outside)} element(s) outside {name(area.work_package)}",
                f"{_join([name(v) for v in via])} change, and relate to "
                f"{_join([name(o) for o in sorted(area.outside)[:10]])}"
                f"{' and more' if len(area.outside) > 10 else ''}, which the work package does not name.",
                [*via, *sorted(area.outside)],
                "What a work package changes but does not name is changed without a plan saying so.",
                3,
            )
        # 4. an element below the business layer traces up to nothing (P9)
        untraced = [i for i in scope if traced.get(i) is False]
        for i in [i for i in untraced if i in subject]:
            add(
                "untraced",
                "high",
                f"{name(i)} traces up to nothing",
                f"Nothing within {TRACE_DEPTH} steps of it is in the business, the strategy or the motivation.",
                [i],
                "Principle P9: an element earns its place in the repository by what it serves.",
                3,
            )
        rest = [i for i in untraced if i not in subject]
        if rest:
            add(
                "untraced",
                "medium",
                f"{len(rest)} element(s) below the business trace up to nothing",
                f"{_join([name(i) for i in rest[:10]])}{' and more' if len(rest) > 10 else ''}: nothing within "
                f"{TRACE_DEPTH} steps of them is in the business, the strategy or the motivation.",
                rest,
                "Principle P9: an element earns its place in the repository by what it serves.",
                3,
            )
        # 5. a relationship type the element's type declares has no instance
        by_type: dict[str, list[str]] = {}
        for i in area.subject:
            if i in els:
                by_type.setdefault(els[i].type_id, []).append(i)
        for type_id, ids in by_type.items():
            empty = self.graph.completeness(type_id)["empty"]
            if empty:
                add(
                    "empty_relationship",
                    "low",
                    f"{len(empty)} relationship type(s) {self._type_name(type_id)} declares hold no instance",
                    f"The metamodel declares {_join(empty[:6])}{' and more' if len(empty) > 6 else ''}; the model "
                    "holds none of them, so an answer that follows them finds nothing.",
                    ids,
                    "An answer is only as complete as the relationships the model holds.",
                    4,
                )
        # 6. an element and its documentation disagree
        doc = [x for x in inconsistencies if x["rule"] != "state"]
        if doc:
            involved = [i for x in doc for i in (x["element_id"], x["other_id"]) if i]
            add(
                "documentation",
                "medium" if set(involved) & subject else "low",
                f"An element and its documentation disagree in {len(doc)} place(s)",
                " ".join(x["text"] for x in doc[:3]) + (f" And {len(doc) - 3} more." if len(doc) > 3 else ""),
                involved,
                "Where the record and what it says contradict each other, one of them is wrong, and a reader "
                "cannot tell which.",
                4,
            )
        # 7. it rests on low maturity, or on content not refreshed for long
        if scope:
            low = [i for i in scope if maturity[i][0] <= 2]
            share = len(low) / len(scope)
            if share >= 0.25:
                add(
                    "maturity",
                    "high" if share >= 0.5 else "medium",
                    f"{round(100 * share)}% of what it rests on is named or described only",
                    f"{_join([name(i) for i in low[:10]])}{' and more' if len(low) > 10 else ''} carry too "
                    "little for the analysis to check.",
                    low,
                    "A finding is as good as the elements it rests on.",
                    2,
                )
            stale = []
            for i in scope:
                updated = _naive(els[i].updated_at)
                if updated is not None and (self.now - updated).days >= RECENT_DAYS:
                    stale.append(i)
            if stale:
                add(
                    "maturity",
                    "medium" if len(stale) / len(scope) >= 0.5 else "low",
                    f"{len(stale)} element(s) not refreshed for {RECENT_DAYS} days or more",
                    f"{_join([name(i) for i in stale[:10]])}{' and more' if len(stale) > 10 else ''} have not been "
                    "refreshed from their source or confirmed by a person for long.",
                    stale,
                    "Content its source has not refreshed for long may no longer be true.",
                    2,
                )
        found = [f for f in found if f["elements"]]
        found.sort(key=lambda f: (SEVERITIES.index(f["severity"]), RULES.index(f["rule"])))
        for n, f in enumerate(found, 1):
            f["id"] = f"F{n}"
        return found

    @staticmethod
    def _headline(findings: list[dict[str, Any]], purpose: str) -> list[dict[str, Any]]:
        """The findings that matter most for what the analysis is for: severity, raised by the purpose."""
        wanted = _words(purpose)

        def key(pair: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
            n, f = pair
            relevant = bool(wanted & _words(f"{f['title']} {f['text']} {f['rule']}"))
            return SEVERITIES.index(f["severity"]) - (1 if relevant else 0), 0 if relevant else 1, n

        ordered = [f for _, f in sorted(enumerate(findings), key=key)]
        return [
            {"id": f["id"], "rule": f["rule"], "severity": f["severity"], "title": f["title"]}
            for f in ordered[:HEADLINE]
        ]

    # ------------------------------------------------------ the levels
    def _key(
        self, area: _Area, findings: list[dict[str, Any]], adjacency: dict[str, dict[str, set[str]]]
    ) -> list[str]:
        """The elements drawn up close: the subject, then what the findings cite most, then the most related."""
        cited = Counter(i for f in findings for i in f["elements"])
        head = list(area.subject) or ([area.work_package] if area.work_package else [])
        scope = [i for i in area.scope if i not in head]

        def degree(i: str) -> int:
            return len(adjacency["out"].get(i, set()) | adjacency["in"].get(i, set()))

        rest = sorted(scope, key=lambda i: (-cited.get(i, 0), -degree(i), i))
        return (head + rest)[:MAX_KEY]

    def _detail(
        self,
        key: list[str],
        els: dict[str, Element],
        maturity: dict[str, tuple[int, str]],
        adjacency: dict[str, dict[str, set[str]]],
        traced: dict[str, bool | None],
        steps: list[dict[str, str]],
    ) -> dict[str, dict[str, Any]]:
        """Each key element's neighbourhood, one step out; what it adds is read and given a maturity."""
        out: dict[str, dict[str, Any]] = {}
        for k in key:
            sub = self.graph.neighbours(k, 1, "both", max_nodes=DEFAULT_MAX_NODES)
            out[k] = sub
            steps.append(
                {"tool": "neighbours", "detail": f"{k}: {len(sub['nodes']) - 1} element(s) one step out"}
            )
        new = [n["element_id"] for sub in out.values() for n in sub["nodes"] if n["element_id"] not in els]
        if new:
            more = {e.element_id: e for e in self.backend.elements_by_ids(new)}
            els.update(more)
            extra = self._adjacency(self.backend.edges_among(list(els)))
            for d in ("out", "in"):
                for i, ns in extra[d].items():
                    adjacency[d].setdefault(i, set()).update(ns)
            added, _ = self._traced(more, adjacency, [MAX_WALKS // 4])
            traced.update(added)
            for i, e in more.items():
                maturity[i] = self._maturity(e, adjacency, [], traced.get(i))
        return out

    def _rows(
        self,
        area: _Area,
        els: dict[str, Element],
        maturity: dict[str, tuple[int, str]],
        findings: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        cited = Counter(i for f in findings for i in f["elements"])
        subject = set(area.subject) | ({area.work_package} if area.work_package else set())
        order = [i for i in area.scope if i in els] + sorted(i for i in els if i not in area.scope)
        rows: dict[str, dict[str, Any]] = {}
        for i in order:
            e = els[i]
            notation = self.registry.notation(e.type_id)
            updated = _naive(e.updated_at)
            level, why = maturity[i]
            rows[i] = {
                "element_id": i,
                "name": e.name,
                "type_id": e.type_id,
                "type_name": self._type_name(e.type_id),
                "layer": notation.get("layer", "other"),
                "archimate": notation.get("archimate", ""),
                "glyph": notation.get("glyph", ""),
                "status": e.status,
                "current_state": e.current_state,
                "target_state": e.target_state,
                "target_work_package": e.target_work_package or "",
                "source": e.source_system or "",
                "updated": updated.date().isoformat() if updated else "",
                "maturity": level,
                "maturity_label": MATURITY_LEVELS[level],
                "maturity_why": why,
                "findings": cited.get(i, 0),
                "role": "subject" if i in subject else ("drawn" if i in area.scope else "context"),
            }
        return rows

    def _node_rows(
        self, rows: dict[str, dict[str, Any]], ids: list[str], focus: set[str]
    ) -> list[dict[str, Any]]:
        return [dict(rows[i], focus=i in focus) for i in ids if i in rows]

    def _edge_rows(self, rels: list[Relationship], real_only: bool = False) -> list[dict[str, Any]]:
        out = []
        for r in rels:
            if real_only and (r.current_state in NOT_REAL or r.current_state == "retired"):
                continue
            rt = self.registry.rel_types.get(r.rel_type_id)
            label = rt.name if rt else r.rel_type_id
            if r.qualifier:
                label = f"{label} ({r.qualifier})"
            out.append(
                {
                    "src": r.src_id,
                    "dst": r.dst_id,
                    "label": label,
                    "rel_type_id": r.rel_type_id,
                    "qualifier": r.qualifier or "",
                    "target_state": r.target_state or "undecided",
                }
            )
        return out

    def _view(
        self,
        rows: dict[str, dict[str, Any]],
        rels: list[Relationship],
        ids: list[str],
        title: str,
        focus: set[str],
        real_only: bool = False,
    ) -> dict[str, Any]:
        wanted = [i for i in dict.fromkeys([*[i for i in ids if i in focus], *ids]) if i in rows]
        if real_only:
            wanted = [i for i in wanted if rows[i]["current_state"] not in NOT_REAL or i in focus]
        view = view_of_change(
            self.registry,
            self._node_rows(rows, wanted, focus),
            self._edge_rows(rels, real_only),
            title,
            max_nodes=DEFAULT_MAX_NODES,
        )
        return view_to_dict(view)

    def _levels(
        self,
        brief: Brief,
        area: _Area,
        els: dict[str, Element],
        rels: list[Relationship],
        rows: dict[str, dict[str, Any]],
        findings: list[dict[str, Any]],
        detail: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scope = [i for i in area.scope if i in rows]
        centre = list(area.subject) or ([area.work_package] if area.work_package else [])
        focus = set(centre)
        levels: list[dict[str, Any]] = []
        for number, title, style in LEVELS:
            levels.append({"level": number, "title": title, "style": style, "figures": []})

        def figure(level: int, kind: str, title: str, reading: str, **data: Any) -> None:
            figures = levels[level - 1]["figures"]
            figures.append(
                {
                    "fid": f"{level}.{len(figures) + 1}",
                    "level": level,
                    "kind": kind,
                    "style": levels[level - 1]["style"],
                    "title": title,
                    "reading": reading,
                    **data,
                }
            )

        # ---- 1. Context: the subject in its enterprise
        around = [i for i in dict.fromkeys([*scope, *area.context]) if i in rows and i not in focus]
        near = sorted(around, key=lambda i: (area.depth.get(i, area.context.get(i, 9)), i))
        groups = []
        serves = [i for i in near if rows[i]["layer"] in ("motivation", "strategy")][:MAX_CONTEXT]
        people = [i for i in near if rows[i]["layer"] == "business" and rows[i]["archimate"] in PEOPLE][
            :MAX_CONTEXT
        ]
        business = [i for i in near if rows[i]["layer"] == "business" and i not in people][:MAX_CONTEXT]
        linked = {n for c in centre for n in self._neighbours_of(c, rels)}
        beside = [i for i in near if i in linked and rows[i]["layer"] not in UPPER_LAYERS][:MAX_CONTEXT]
        for key, label, ids in (
            ("serves", "What it serves", serves),
            ("business", "The business it supports", business),
            ("who", "Who is concerned", people),
            ("around", "Beside it", beside),
        ):
            if ids:
                groups.append({"key": key, "title": label, "ids": ids})
        subject_names = _join([f"{rows[c]['name']} [{c}]" for c in centre if c in rows])
        reading = (
            f"{subject_names} in its enterprise: "
            + (
                "; ".join(f"{g['title'].lower()}, {len(g['ids'])}" for g in groups)
                if groups
                else "nothing around it reaches the business, the strategy or the motivation"
            )
            + "."
        )
        figure(1, "context_map", f"{subject_names} in context", reading, centre=centre, groups=groups)

        # ---- 2. Overview: the landscape, layer by layer, and where the findings sit
        bands = [
            {"layer": lv, "title": LAYER_TITLES[lv], "ids": [i for i in scope if rows[i]["layer"] == lv]}
            for lv in LAYER_ORDER
        ]
        bands = [b for b in bands if b["ids"]]
        figure(
            2,
            "layer_bands",
            "The area, layer by layer",
            f"{len(scope)} elements across {len(bands)} layer(s): "
            + "; ".join(f"{b['title']}, {len(b['ids'])}" for b in bands)
            + ".",
            bands=bands,
        )
        cells = [
            {
                "id": i,
                "layer": rows[i]["layer"],
                "maturity": rows[i]["maturity"],
                "findings": rows[i]["findings"],
            }
            for i in scope
        ]
        flagged = sum(1 for c in cells if c["findings"] or c["maturity"] <= 2)
        figure(
            2,
            "heat_map",
            "Where the low maturity and the findings sit",
            f"Each element coloured by its maturity; {flagged} of {len(cells)} carry a finding or a maturity of "
            "two or less.",
            cells=cells,
        )
        counts = Counter(c["maturity"] for c in cells)
        figure(
            2,
            "chart_maturity",
            "Maturity of what it rests on",
            "How many of the elements read sit at each maturity level.",
            series=[
                {"label": f"{n} — {label}", "value": counts.get(n, 0)} for n, label in MATURITY_LEVELS.items()
            ],
        )
        severities = Counter(f["severity"] for f in findings)
        figure(
            2,
            "chart_findings",
            "Findings by severity",
            f"{len(findings)} finding(s) in all.",
            series=[{"label": s.capitalize(), "value": severities.get(s, 0)} for s in SEVERITIES],
        )

        # ---- 3. Architecture: one chapter per aspect of the analysis
        def arch(
            title: str, ids: list[str], reading: str, marked: bool = False, real_only: bool = False, **more
        ):
            figure(
                3,
                "view",
                title,
                reading,
                view=self._view(rows, rels, ids, title, focus, real_only),
                marked=marked,
                **more,
            )

        up = sorted(area.up, key=lambda i: (area.up[i], i))
        down = sorted(area.down, key=lambda i: (area.down[i], i))
        if brief.kind == "impact":
            upper = [
                i
                for i in dict.fromkeys([*scope, *area.context])
                if i in rows and rows[i]["layer"] in UPPER_LAYERS
            ]
            path = [n for i in upper for n in area.paths.get(i, []) if n in rows]
            arch(
                "What it serves",
                [*centre, *path, *upper],
                f"From {subject_names} up to the {len(upper)} business, strategy and motivation element(s) it "
                "reaches, with the elements between.",
                marked=True,
            )
            arch(
                "Depends on it (upstream)",
                [*centre, *up],
                f"{len(up)} element(s) depend on it within {brief.reach} step(s), each marked with its target state.",
                marked=True,
            )
            arch(
                "It depends on (downstream)",
                [*centre, *down],
                f"It depends on {len(down)} element(s) within {brief.reach} step(s).",
                marked=True,
            )
        elif brief.kind == "flow":
            sources = sorted({rows[i]["source"] for i in scope if rows[i]["source"]})
            arch(
                "Where it comes from",
                [*centre, *up],
                f"{len(up)} element(s) reach it within {brief.reach} step(s)"
                + (f"; content mastered in {_join(sources)}." if sources else "."),
            )
            arch(
                "Where it goes",
                [*centre, *down],
                f"It reaches {len(down)} element(s) within {brief.reach} step(s).",
            )
            arch(
                "The whole flow",
                [*up, *centre, *down],
                "From what reaches it, through it, to what it reaches.",
            )
        elif brief.kind == "landscape":
            for b in bands:
                arch(
                    b["title"],
                    [*centre, *b["ids"]],
                    f"The {b['title'].lower()} layer of the area: {len(b['ids'])} element(s)"
                    + (", beside the subject." if not focus & set(b["ids"]) else "."),
                )
        elif brief.kind == "transition":
            members = [i for i in area.members if i in rows]
            changing = [i for i in members if rows[i]["target_state"] in (*CHANGING, "new")]
            arch(
                "As it is",
                members,
                "The work package's elements that exist today, as they are.",
                real_only=True,
            )
            arch(
                "As targeted",
                members,
                f"The same elements as the work package targets them: {len(changing)} change, arrive or go.",
                marked=True,
            )
            outside = sorted(area.outside)
            arch(
                "What it touches outside the package",
                [*sorted(set(area.outside.values())), *outside],
                f"{len(outside)} element(s) outside the package that the changing elements relate to.",
                marked=True,
            )
        else:  # quality
            marked_ids = [i for i in scope if rows[i]["findings"] or rows[i]["maturity"] <= 2]
            order = [*centre, *marked_ids, *[i for i in scope if i not in marked_ids]]
            arch(
                "The area, its findings marked",
                order,
                f"{len(marked_ids)} element(s) carry a finding or a maturity of two or less, and are marked.",
                flagged=marked_ids,
            )

        # ---- 4. Detail: the key elements up close
        for k, sub in detail.items():
            ids = [n["element_id"] for n in sub["nodes"]]
            edges = [
                {
                    "src": e["src_id"],
                    "dst": e["dst_id"],
                    "label": e["label"],
                    "rel_type_id": e.get("rel_type_id") or "",
                    "qualifier": e.get("qualifier") or "",
                    "target_state": e.get("target_state") or "undecided",
                }
                for e in sub["edges"]
            ]
            view = view_of_change(
                self.registry,
                self._node_rows(rows, ids, {k}),
                edges,
                f"{rows[k]['name']} and what it relates to",
                max_nodes=DEFAULT_MAX_NODES,
            )
            about = [x for x in findings if k in x["elements"]]
            figure(
                4,
                "view",
                f"{rows[k]['name']} [{k}] up close",
                f"Maturity {rows[k]['maturity']} — {rows[k]['maturity_label']}: {rows[k]['maturity_why']} "
                f"{len(about)} finding(s) cite it.",
                view=view_to_dict(view),
                marked=True,
                element_id=k,
                findings=[x["id"] for x in about],
            )
        return levels

    @staticmethod
    def _neighbours_of(element_id: str, rels: list[Relationship]) -> set[str]:
        return {
            r.dst_id if r.src_id == element_id else r.src_id
            for r in rels
            if element_id in (r.src_id, r.dst_id)
        }

    # ---------------------------------------------------- the rest
    def _references(self, brief: Brief, area: _Area, key: list[str]) -> dict[str, Any]:
        ids = list(area.subject) or ([area.work_package] if area.work_package else [])
        earlier = self.dives.earlier(ids, 5) if ids else []
        if brief.from_deep_dive and all(d.deep_dive_id != brief.from_deep_dive for d in earlier):
            source = self.dives.get(brief.from_deep_dive)
            if source is not None:
                earlier = [source, *earlier]
        elif brief.from_deep_dive:
            earlier.sort(key=lambda d: d.deep_dive_id != brief.from_deep_dive)
        dives = [
            {
                "deep_dive_id": d.deep_dive_id,
                "title": d.title,
                "kind": d.kind,
                "created_by": d.created_by,
                "created_at": str(d.created_at or "")[:16],
                "rating_average": d.rating_average,
                "rating_count": d.rating_count,
                "run_again_from": d.deep_dive_id == brief.from_deep_dive,
                "findings": [
                    {"title": f.get("title", ""), "severity": f.get("severity", "")}
                    for f in (d.content.get("findings") or [])[:5]
                ],
            }
            for d in earlier
        ]
        links = []
        for k in key:
            for ln in self.backend.get_links(k):
                links.append({"element_id": k, "url": ln.url, "label": ln.label, "read": False})
        return {"deep_dives": dives, "links": links}

    def _title(self, brief: Brief, area: _Area, els: dict[str, Element]) -> str:
        ids = list(area.subject) or ([area.work_package] if area.work_package else [])
        names = [els[i].name for i in ids if i in els]
        return f"{KINDS[brief.kind]['label']}: {_join(names)}"[:150]

    def _rules_summary(self, brief: Brief, content: dict[str, Any]) -> str:
        findings = content["findings"]
        by = Counter(f["severity"] for f in findings)
        layers = {r["layer"] for r in content["elements"].values() if r["role"] != "context"}
        read = content["read"]
        parts = [
            f"{content['brief_sentence']} It read {read['elements']} element(s) across {len(layers)} layer(s)"
            + (", and stopped at the most it may read in one analysis." if read["truncated"] else "."),
            content["confidence"]["text"],
        ]
        if findings:
            parts.append(
                f"{len(findings)} finding(s): {by.get('high', 0)} high, {by.get('medium', 0)} medium, "
                f"{by.get('low', 0)} low. First: " + "; ".join(h["title"] for h in content["headline"]) + "."
            )
        else:
            parts.append("The rules found nothing to report.")
        refs = content["references"]["deep_dives"]
        if refs:
            parts.append(
                f"{len(refs)} earlier deep dive(s) on the same elements are listed among its references."
            )
        return " ".join(parts)

    # ============================================================ a hosted model
    def _model_read(self, brief: Brief, words: str) -> Brief:
        """The reader's words read by the model into the brief; the rules when it cannot be reached."""
        toolbox = ToolBox(
            self.backend, self.registry, RepositoryService(self.backend, self.registry), self.graph
        )
        tools = [t for t in toolbox.specs() if t["name"] in READ_TOOLS] + [SETTLE_TOOL]
        system = BRIEF_PROMPT + self.registry.summary_markdown()
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": f"The reader's words: {words}\n\nThe brief so far: {json.dumps(brief.to_dict())}",
            }
        ]
        settled: dict[str, Any] | None = None
        try:
            for _ in range(MAX_TURNS):
                reply = self.model.turn(system, messages, tools)  # type: ignore[union-attr]
                if reply.stop == "refused":
                    raise ModelError("the model declined to read these words")
                messages.append(reply.message)
                if not reply.tool_uses:
                    break
                for use in reply.tool_uses:
                    if use.malformed:
                        text = MALFORMED
                    elif use.name == SETTLE_TOOL["name"]:
                        settled, text = dict(use.arguments or {}), "settled"
                    else:
                        text = toolbox.call(use.name, use.arguments)
                    messages.append(tool_result(use, text))
        except ModelError as exc:
            brief.note = f"The assistant could not be reached ({exc}); your words were searched as names."
            self._apply_words(brief, words, guess=not brief.subject)
            return brief
        if settled is None:
            self._apply_words(brief, words, guess=not brief.subject)
            return brief
        ids = self._existing([str(i) for i in settled.get("subject") or []])
        wp_type = self._wp_type()
        held = {e.element_id: e for e in self.backend.elements_by_ids(ids)}
        subject = [i for i in ids if held[i].type_id != wp_type][:MAX_SUBJECT]
        packages = [i for i in ids if held[i].type_id == wp_type]
        wp = self._existing([str(settled.get("work_package") or "")]) or packages
        if subject:
            brief.subject, brief.work_package = subject, ""
        elif wp:
            brief.subject, brief.work_package = [], wp[0]
        if (subject or wp) and "subject" not in brief.settled:
            brief.settled.append("subject")
        if settled.get("kind") in KINDS and "kind" not in brief.settled:
            brief.kind = settled["kind"]
        if settled.get("reach") and "reach" not in brief.settled:
            brief.reach = _reach(settled["reach"])
        if (settled.get("purpose") or "").strip() and "purpose" not in brief.settled:
            brief.purpose = settled["purpose"].strip()
        brief.asked = str(settled.get("ask") or "").strip()
        return brief

    def _model_summary(self, content: dict[str, Any]) -> None:
        """The summary in the model's words, from the findings; every identifier it cites checked."""
        rows = content["elements"]
        material = {
            "brief": content["brief_sentence"],
            "purpose": content["purpose"],
            "confidence": content["confidence"],
            "findings": [
                {k: f[k] for k in ("id", "severity", "title", "text", "elements")}
                for f in content["findings"]
            ],
            "inconsistencies": [x["text"] for x in content["inconsistencies"][:20]],
            "elements": [
                {k: r[k] for k in ("element_id", "name", "type_name", "layer", "maturity", "role")}
                for r in list(rows.values())[:MAX_SCOPE]
            ],
            "earlier_deep_dives": content["references"]["deep_dives"],
        }
        try:
            reply = self.model.turn(  # type: ignore[union-attr]
                SUMMARY_PROMPT, [{"role": "user", "content": json.dumps(material, default=str)}], []
            )
        except ModelError as exc:
            content["trace"]["model_error"] = str(exc)
            return
        if reply.stop == "refused" or not (reply.text or "").strip():
            content["trace"]["model_error"] = "the model gave no summary"
            return
        cited = list(dict.fromkeys(ID_RE.findall(reply.text)))
        content["summary"] = reply.text.strip()
        content["trace"].update(
            provider=self.model.provider,  # type: ignore[union-attr]
            model=reply.model or self.model.model,  # type: ignore[union-attr]
            ungrounded=[i for i in cited if i not in rows],
        )


def _link_problems(links: list[Any]) -> list[str]:
    """What is wrong with an element's links: a malformed address, or the same page twice."""
    out: list[str] = []
    seen: set[str] = set()
    for ln in links:
        url = (getattr(ln, "url", "") or "").strip()
        if not _URL.match(url):
            out.append(f"the link “{url}” is not a web address")
        elif url.rstrip("/").lower() in seen:
            out.append(f"{url} is linked twice")
        seen.add(url.rstrip("/").lower())
    return out


MAX_TURNS = 8
READ_TOOLS = ("list_types", "search_elements", "get_element", "neighbours")
SETTLE_TOOL = {
    "name": "settle_brief",
    "description": (
        "Record what the reader's words settle about the deep dive: the elements it is about "
        "(identifiers a tool returned), or the work package; the kind of analysis; how many steps "
        "it reaches; what it is for; and, when the words leave something unclear that the rules "
        "cannot ask about, one short question for the reader."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "array", "items": {"type": "string"}},
            "work_package": {"type": "string"},
            "kind": {"type": "string", "enum": list(KINDS)},
            "reach": {"type": "integer", "minimum": 1, "maximum": MAX_REACH},
            "purpose": {"type": "string"},
            "ask": {"type": "string"},
        },
        "additionalProperties": False,
    },
}
BRIEF_PROMPT = """You settle the brief of a deep dive with a reader of an enterprise architecture repository.

The reader said, in their own words, what they need to know. Find the elements they mean with the tools, and call `settle_brief` once with what their words settle: the subject (identifiers a tool returned — never invented), the kind of analysis (impact: what happens if it changes or goes; landscape: what makes up the area; transition: what a work package changes; flow: where information comes from and goes; quality: how far the model can be trusted there), the reach in steps, and the purpose when they said one. Ask one short question with `ask` only when their words leave the subject or the kind unclear; the reader answers it in their own words. Finish with one sentence.

The loaded metamodel:
"""
SUMMARY_PROMPT = """You write the summary of a deep dive into an enterprise architecture repository.

You are given the brief, the findings the rules made, the elements read with their maturity, and the earlier deep dives on the same elements with their ratings. Write four to eight sentences for a reader who is not an architect: lead with what matters most for the purpose, say how far it can be trusted from the maturity, and mention an earlier deep dive only when its findings still hold in what you were given. Cite every element by name with its identifier in square brackets, e.g. "Student Records System [PAC-SRS]", and use only identifiers you were given. Plain prose, no headings, no lists."""
