"""What a draft proposal still leaves open, asked top-down, and an answer applied to it.

Initiative 24 (BPROC2.2, principle P9). The questions come from the rules the application
already applies — the metamodel, the matching, the impact — so the reader without a model asks
them too, and a picked choice is applied without one. Understanding an answer in the
architect's own words needs a model (`ea.agent.proposal`).

The change is settled top-down. Why it is made and which business it changes are asked
first; a question about a row below the business layer is held until both are clear. Every
new or changing element below the business layer has to trace up — over the page's
relationships, or the model's for what exists — to something in the business, strategy or
motivation layers. The layers are read from the metamodel's own notation, so the order holds
in any framework.

An element earns its place by its relationships (P9): a new element below the business layer
whose every relationship ends at one and the same application or technology element relates
to nothing outside that system, and one of a type the metamodel places at the `solution`
level is below the line by definition. Either is asked about: link it from the system, keep
it, or leave it out.

The architect decides every question. An answer edits the draft only; nothing is written
until the architect applies it (P3, decision 0004).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ea.models import ElementFilter
from ea.services.impact import CHANGING

if TYPE_CHECKING:
    from ea.agent.proposal import ProposalResult, ProposedElement, ProposedRelationship
    from ea.backend.base import DatabaseBackend
    from ea.metamodel.registry import Registry
    from ea.services.target import TargetStateService

#: Top-down order of the layers a pack's notation names.
LAYER_RANK = {
    "motivation": 0,
    "strategy": 1,
    "business": 2,
    "application": 3,
    "technology": 4,
    "physical": 4,
    "implementation": 5,
    "other": 6,
}
CONTEXT_LAYERS = ("motivation", "strategy")  # why a change is made
UPPER_LAYERS = ("motivation", "strategy", "business")  # what an element below them traces to
LOWER_LAYERS = ("application", "technology", "physical")  # below the business layer
MIN_DESCRIPTION_CHARS = 20  # one short sentence
#: How many questions are shown at once; the rest wait their turn.
MAX_SHOWN = 5
MAX_CANDIDATES = 5
#: Steps through the model an existing element is followed to find what it serves.
TRACE_DEPTH = 2
#: Existing elements followed through the model per pass, so a long page stays quick.
MAX_WALKS = 40

#: Questions whose open state stops Apply. The rest inform.
BLOCKING = (
    "why",
    "business",
    "trace",
    "match",
    "type",
    "relationship",
    "work_package",
    "boundary",
    "description",
)
#: The order questions of one layer are asked in.
KIND_ORDER = (
    "why",
    "business",
    "work_package",
    "type",
    "match",
    "trace",
    "boundary",
    "relationship",
    "description",
    "dangling",
    "isolated",
    "assistant",
)


@dataclass
class Option:
    """One choice. `needs` says what the architect adds with it: nothing, a sentence (`text`),
    a name (`name`), or a web address (`url`); `choices` is a second pick it needs, such as
    the relationship to use or the type of a new element."""

    key: str
    label: str
    needs: str = ""
    choices: list[dict[str, str]] = field(default_factory=list)
    hint: str = ""


@dataclass
class Question:
    qid: str  # stable across passes: kind, then what it is about
    kind: str
    layer: str
    about: str  # change | element:<row> | relationship:<row> | relationship:<id>
    text: str
    options: list[Option] = field(default_factory=list)
    free: bool = False  # an answer in words is understood without a model
    blocking: bool = True
    held: bool = False  # waits until why and which business are settled
    asked_by: str = "rules"  # rules | assistant

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Question:
        return cls(
            qid=str(d.get("qid") or ""),
            kind=str(d.get("kind") or ""),
            layer=str(d.get("layer") or ""),
            about=str(d.get("about") or ""),
            text=str(d.get("text") or ""),
            options=[
                Option(
                    key=str(o.get("key") or ""),
                    label=str(o.get("label") or ""),
                    needs=str(o.get("needs") or ""),
                    choices=[dict(c) for c in o.get("choices") or []],
                    hint=str(o.get("hint") or ""),
                )
                for o in d.get("options") or []
            ],
            free=bool(d.get("free", False)),
            blocking=bool(d.get("blocking", True)),
            held=bool(d.get("held", False)),
            asked_by=str(d.get("asked_by") or "rules"),
        )


class AnswerError(ValueError):
    """An answer that does not fit its question: a choice it does not offer, or a value it needs and lacks."""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def shown(questions: list[dict[str, Any]], limit: int = MAX_SHOWN) -> list[dict[str, Any]]:
    """The questions to put to the architect now: the first few that are not held."""
    return [q for q in questions if not q.get("held")][:limit]


class QuestionRules:
    """The questions a resolved draft leaves open, and a picked choice applied to the draft."""

    def __init__(self, backend: DatabaseBackend, registry: Registry, target: TargetStateService):
        self.backend, self.registry, self.target = backend, registry, target

    # ------------------------------------------------------------ helpers
    def layer(self, type_id: str) -> str:
        return self.registry.notation(type_id)["layer"] if type_id in self.registry.types else ""

    def _type_name(self, type_id: str) -> str:
        t = self.registry.get_type(type_id)
        return t.name if t else type_id

    def _types_in(self, layers: tuple[str, ...]) -> list[dict[str, str]]:
        return [
            {"key": t.id, "label": t.name}
            for t in sorted(
                self.registry.concrete_types(),
                key=lambda t: (LAYER_RANK.get(self.layer(t.id), 9), t.sort_order, t.name),
            )
            if t.active and self.layer(t.id) in layers
        ]

    def _relationships_between(self, a_type: str, b_type: str) -> list[dict[str, str]]:
        """The relationships the metamodel allows between two types, either way round, as
        choices: `out:<id>` from the first to the second, `in:<id>` from the second to the first."""
        out = [
            {"key": f"out:{r.id}", "label": r.name} for r in self.registry.allowed_rel_types(a_type, b_type)
        ]
        back = [
            {"key": f"in:{r.id}", "label": f"{r.name} (from the other end)"}
            for r in self.registry.allowed_rel_types(b_type, a_type)
        ]
        return out + back

    # ----------------------------------------------------------- the pass
    def open_questions(self, result: ProposalResult) -> list[Question]:
        """Every open question, top layer first; lower layers held while the context is open."""
        rows = [el for el in result.elements if el.include]
        rels = [r for r in result.relationships if r.include]
        held_by_answer = {qid for qid, a in (result.answers or {}).items() if a.get("holds")}
        endpoints = self._endpoints(rows, rels)
        layer_of = {ref: self.layer(t) for ref, (t, _name) in endpoints.items()}
        below = [
            el
            for el in rows
            if layer_of.get(el.ref) in LOWER_LAYERS and (el.action == "new" or el.target_state in CHANGING)
        ]
        questions: list[Question] = []

        def add(q: Question) -> None:
            if q.qid not in held_by_answer:
                questions.append(q)

        has_context = any(layer_of.get(ref) in CONTEXT_LAYERS for ref in endpoints)
        has_business = any(layer_of.get(ref) == "business" for ref in endpoints)
        why_open = not has_context and not (result.reason or "").strip()
        business_open = bool(below) and not has_business and not result.technical
        if why_open:
            add(self._why(result, rows, blocking=bool(below)))
        if business_open:
            add(self._business(result, rows))
        if not (result.work_package or "").strip():
            add(self._work_package(rows))
        for el in rows:
            q = self._row_question(el)
            if q is not None:
                add(q)
        traced = self._traced(rows, rels, endpoints, layer_of)
        for el in below:
            if el.ref not in traced and not el.referenced_from:
                add(self._trace(el, rows, result))
        for el in below:
            q = self._boundary(el, rels, endpoints, layer_of)
            if q is not None:
                add(q)
        for rel in rels:
            q = self._relationship(rel, endpoints)
            if q is not None:
                add(q)
        for el in rows:
            if (
                el.action == "new"
                and el.name
                and el.type_id
                and len((el.description or "").strip()) < MIN_DESCRIPTION_CHARS
            ):
                add(
                    Question(
                        qid=f"description:{norm(el.name)}",
                        kind="description",
                        layer=layer_of.get(el.ref, ""),
                        about=f"element:{el.row}",
                        text=f"Describe {el.name} in a sentence: what it is and what it is for.",
                        options=[Option("describe", "Describe it", needs="text")],
                        free=True,
                    )
                )
        for d in (result.impact or {}).get("dangling") or []:
            add(self._dangling(d, rows))
        asked_trace = {q.qid.split(":", 1)[1] for q in questions if q.kind == "trace"}
        for iso in (result.impact or {}).get("isolated") or []:
            if norm(iso.get("name", "")) in asked_trace:
                continue  # the trace question asks the same, and blocks
            add(self._isolated(iso, rows))
        for a in result.asked or []:
            q = Question.from_dict(a)
            if q.qid not in (result.answers or {}):
                questions.append(q)
        context_open = why_open or business_open
        for q in questions:
            q.blocking = q.kind in BLOCKING and q.blocking
            q.held = context_open and LAYER_RANK.get(q.layer, 2) >= LAYER_RANK["application"]
        questions.sort(
            key=lambda q: (
                q.held,
                LAYER_RANK.get(q.layer, 2),
                KIND_ORDER.index(q.kind) if q.kind in KIND_ORDER else 99,
                q.about,
            )
        )
        return questions

    # -------------------------------------------------------- what exists
    def _endpoints(
        self, rows: list[ProposedElement], rels: list[ProposedRelationship]
    ) -> dict[str, tuple[str, str]]:
        """Every element the change names — its rows and the existing ends of its
        relationships — as ref → (type, name)."""
        out: dict[str, tuple[str, str]] = {el.ref: (el.type_id, el.name) for el in rows if el.type_id}
        missing = {
            ref
            for r in rels
            if r.target_state != "decommission"
            for ref in (r.src_ref, r.dst_ref)
            if ref and not ref.startswith("new:") and ref not in out
        }
        for e in self.backend.elements_by_ids(sorted(missing)):
            out[e.element_id] = (e.type_id, e.name)
        return out

    def _nearby(self, ids: list[str], layers: tuple[str, ...]) -> list[dict[str, str]]:
        """Elements in these layers within `TRACE_DEPTH` steps of existing ones, nearest first."""
        best: dict[str, int] = {}
        for eid in ids[:MAX_WALKS]:
            for direction in ("out", "in"):
                for r in self.backend.trace(eid, direction, TRACE_DEPTH):
                    nid = r["element_id"]
                    if nid not in best or r["depth"] < best[nid]:
                        best[nid] = int(r["depth"])
        found = self.backend.elements_by_ids(list(best))
        kept = [e for e in found if self.layer(e.type_id) in layers]
        kept.sort(key=lambda e: (best[e.element_id], LAYER_RANK.get(self.layer(e.type_id), 9), e.name))
        return [{"element_id": e.element_id, "name": e.name, "type_id": e.type_id} for e in kept]

    def _search(
        self, text: str, layers: tuple[str, ...], limit: int = MAX_CANDIDATES
    ) -> list[dict[str, str]]:
        types = [t["key"] for t in self._types_in(layers)]
        if not text.strip() or not types:
            return []
        out: dict[str, dict[str, str]] = {}
        words = [text] + sorted(
            {w for w in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", text)}, key=len, reverse=True
        )[:3]
        for w in words:
            for e in self.backend.find_elements(ElementFilter(text=w, type_ids=types), limit=limit):
                out.setdefault(
                    e.element_id, {"element_id": e.element_id, "name": e.name, "type_id": e.type_id}
                )
            if len(out) >= limit:
                break
        return list(out.values())[:limit]

    def _candidates(self, result: ProposalResult, rows: list[ProposedElement], layers: tuple[str, ...]):
        linked = [el.element_id for el in rows if el.action == "link" and el.element_id]
        seen = {el.element_id for el in rows if el.element_id}
        out = [c for c in self._nearby(linked, layers) if c["element_id"] not in seen]
        if len(out) < MAX_CANDIDATES:
            for c in self._search(result.title or "", layers):
                if c["element_id"] not in seen and all(c["element_id"] != o["element_id"] for o in out):
                    out.append(c)
        return out[:MAX_CANDIDATES]

    def _existing_option(self, c: dict[str, str]) -> Option:
        return Option(
            f"link:{c['element_id']}", f"{c['name']} [{c['element_id']}] — {self._type_name(c['type_id'])}"
        )

    # ----------------------------------------------------------- the kinds
    def _why(self, result: ProposalResult, rows: list[ProposedElement], blocking: bool) -> Question:
        options = [self._existing_option(c) for c in self._candidates(result, rows, CONTEXT_LAYERS)]
        types = self._types_in(CONTEXT_LAYERS)
        if types:
            options.append(Option("new", "A new one", needs="name", choices=types))
        options.append(Option("words", "Say why in words", needs="text"))
        return Question(
            qid="why",
            kind="why",
            layer="motivation",
            about="change",
            text="What is this change for? The page names nothing it serves in the strategy or motivation layers.",
            options=options,
            free=True,
            blocking=blocking,
        )

    def _business(self, result: ProposalResult, rows: list[ProposedElement]) -> Question:
        options = [self._existing_option(c) for c in self._candidates(result, rows, ("business",))]
        types = self._types_in(("business",))
        if types:
            options.append(Option("new", "A new one", needs="name", choices=types))
        options.append(Option("technical", "None: a purely technical change"))
        return Question(
            qid="business",
            kind="business",
            layer="business",
            about="change",
            text="Which part of the business does this change affect? The page names nothing in the business layer.",
            options=options,
        )

    def _work_package(self, rows: list[ProposedElement]) -> Question:
        carried = {el.element_id for el in rows if el.element_id}
        wps = self.target.work_packages() if self.target.work_package_type() else []
        held = self.backend.elements_by_ids(sorted(carried))
        near = {e.target_work_package for e in held if e.target_work_package}
        wps.sort(key=lambda w: (w.element_id not in near, w.name))
        options = [Option(f"wp:{w.element_id}", f"{w.name} [{w.element_id}]") for w in wps[:MAX_CANDIDATES]]
        options.append(Option("new", "A new work package", needs="name"))
        return Question(
            qid="work_package",
            kind="work_package",
            layer="business",
            about="change",
            text="Which work package delivers this change?",
            options=options,
            free=True,
        )

    def _row_question(self, el: ProposedElement) -> Question | None:
        """A row's type or its match: what has to be settled before anything else about it."""
        if el.referenced_from:
            return None
        label = el.name or el.type_label or f"row {el.row}"
        if not el.type_id and el.action != "link":
            names = [t for t in self._types_in(tuple(LAYER_RANK))]
            if el.type_label:
                close = difflib.get_close_matches(
                    el.type_label.lower(), [t["label"].lower() for t in names], n=len(names), cutoff=0
                )
                rank = {c: i for i, c in enumerate(close)}
                names.sort(key=lambda t: rank.get(t["label"].lower(), 999))
            said = f"{el.type_label!r} is not in the metamodel" if el.type_label else "the row names no type"
            return Question(
                qid=f"type:{norm(el.name) or el.row}",
                kind="type",
                layer="",
                about=f"element:{el.row}",
                text=f"What type is {label}? {said[0].upper() + said[1:]}.",
                options=[Option(f"type:{t['key']}", t["label"]) for t in names[:12]],
            )
        if el.action == "new" and el.candidates and not el.confirmed_new:
            several = any("matches several" in i for i in el.issues)
            text = (
                f"{label} matches more than one element the model holds. Which is it?"
                if several
                else f"{label} is close to an element the model holds. Is it the same one?"
            )
            options = [
                Option(
                    f"link:{c['element_id']}",
                    f"It is {c['name']} [{c['element_id']}] — {self._type_name(c['type_id'])}",
                )
                for c in el.candidates[:MAX_CANDIDATES]
            ]
            options.append(Option("new", "It is new"))
            return Question(
                qid=f"match:{norm(el.name)}",
                kind="match",
                layer=self.layer(el.type_id),
                about=f"element:{el.row}",
                text=text,
                options=options,
            )
        return None

    def _traced(self, rows, rels, endpoints, layer_of) -> set[str]:
        """The refs connected — over the change's relationships, or the model's for what
        exists — to something in the upper layers."""
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for ref in endpoints:
            find(ref)
        for r in rels:
            if r.src_ref and r.dst_ref and r.target_state != "decommission":
                parent[find(r.src_ref)] = find(r.dst_ref)
        anchored = {find(ref) for ref, layer in layer_of.items() if layer in UPPER_LAYERS}
        # what exists may already trace up in the model: follow it, a few steps, per group
        groups: dict[str, list[str]] = {}
        for ref in endpoints:
            if not ref.startswith("new:") and find(ref) not in anchored:
                groups.setdefault(find(ref), []).append(ref)
        walks = 0
        for root, ids in groups.items():
            for eid in ids:
                if walks >= MAX_WALKS:
                    break
                walks += 1
                if self._traces_in_model(eid):
                    anchored.add(root)
                    break
        return {ref for ref in endpoints if find(ref) in anchored}

    def _traces_in_model(self, element_id: str) -> bool:
        reached: list[str] = []
        for direction in ("out", "in"):
            reached += [r["element_id"] for r in self.backend.trace(element_id, direction, TRACE_DEPTH)]
        return any(self.layer(e.type_id) in UPPER_LAYERS for e in self.backend.elements_by_ids(reached))

    def _trace(self, el: ProposedElement, rows: list[ProposedElement], result: ProposalResult) -> Question:
        anchors: list[tuple[str, str, str]] = []  # (ref, label, type_id): the page's own first
        for other in rows:
            if other is el or not other.type_id or self.layer(other.type_id) not in UPPER_LAYERS:
                continue
            anchors.append((other.ref, other.name, other.type_id))
        for c in self._candidates(result, rows, UPPER_LAYERS):
            anchors.append((c["element_id"], f"{c['name']} [{c['element_id']}]", c["type_id"]))
        options = []
        for ref, label, type_id in anchors:
            choices = self._relationships_between(el.type_id, type_id)
            if choices:
                options.append(
                    Option(f"serve:{ref}", f"{label} — {self._type_name(type_id)}", choices=choices)
                )
            if len(options) >= MAX_CANDIDATES:
                break
        options.append(Option("drop", "Leave it out of this change"))
        return Question(
            qid=f"trace:{norm(el.name)}",
            kind="trace",
            layer=self.layer(el.type_id),
            about=f"element:{el.row}",
            text=(
                f"What business or strategy does {el.name} serve? Nothing on the page or in the "
                "model connects it upward."
            ),
            options=options,
        )

    def _boundary(self, el: ProposedElement, rels, endpoints, layer_of) -> Question | None:
        """P9: a new element below the business layer that relates only to its own system, or
        of a type the metamodel places below the enterprise level."""
        if el.action != "new" or el.referenced_from or not el.type_id:
            return None
        ends = {
            (r.dst_ref if r.src_ref == el.ref else r.src_ref)
            for r in rels
            if r.target_state != "decommission" and el.ref in (r.src_ref, r.dst_ref)
        } - {el.ref, ""}
        t = self.registry.get_type(el.type_id)
        below_line = t is not None and getattr(t, "level", "enterprise") == "solution"
        lower_ends = [ref for ref in ends if layer_of.get(ref) in LOWER_LAYERS]
        inside_one = len(ends) == 1 and len(lower_ends) == 1
        if not (below_line or inside_one):
            return None
        options = []
        for ref in lower_ends[:3]:
            name = endpoints.get(ref, ("", ref))[1] or ref
            options.append(
                Option(
                    f"reference:{ref}",
                    f"Link it from {name}",
                    needs="url",
                    hint="the page that describes it: a wiki page, a portal, the system's own documentation",
                )
            )
        system = endpoints.get(lower_ends[0], ("", ""))[1] if inside_one else ""
        options.append(
            Option(
                "keep",
                "Keep it",
                needs="text",
                hint=f"what outside {system or 'its system'} relates to it",
            )
        )
        options.append(Option("drop", "Leave it out of this change"))
        if below_line:
            text = (
                f"{el.name} is a {t.name}, a type the metamodel places below the enterprise level. "
                "A system's inside is linked from the system rather than modelled."
            )
        else:
            text = (
                f"{el.name} relates only to {system}. Nothing outside {system} relates to it, so it "
                f"looks like part of {system}'s inside, which is linked from the system rather than modelled."
            )
        return Question(
            qid=f"boundary:{norm(el.name)}",
            kind="boundary",
            layer=self.layer(el.type_id),
            about=f"element:{el.row}",
            text=text,
            options=options,
        )

    def _relationship(self, rel: ProposedRelationship, endpoints) -> Question | None:
        if rel.rel_type_id or not rel.relationship or not (rel.src_ref and rel.dst_ref):
            return None
        src_t = endpoints.get(rel.src_ref, ("", ""))[0]
        dst_t = endpoints.get(rel.dst_ref, ("", ""))[0]
        if not (src_t and dst_t):
            return None
        options = [
            Option(f"rel:{r.id}", f"{rel.source} {r.name} {rel.target}")
            for r in self.registry.allowed_rel_types(src_t, dst_t)
        ] + [
            Option(f"reverse:{r.id}", f"{rel.target} {r.name} {rel.source}")
            for r in self.registry.allowed_rel_types(dst_t, src_t)
        ]
        options = options[:10] + [Option("drop", "Leave it out of this change")]
        return Question(
            qid=f"relationship:{norm(rel.source)}|{norm(rel.relationship)}|{norm(rel.target)}",
            kind="relationship",
            layer=min((self.layer(src_t), self.layer(dst_t)), key=lambda x: LAYER_RANK.get(x, 9)),
            about=f"relationship:{rel.row}",
            text=(
                f"{rel.source} {rel.relationship} {rel.target}: the metamodel has no {rel.relationship!r} "
                f"from {self._type_name(src_t)} to {self._type_name(dst_t)}. Which relationship is it?"
            ),
            options=options,
        )

    def _dangling(self, d: dict[str, Any], rows: list[ProposedElement]) -> Question:
        retiring = next((el for el in rows if el.element_id == d["retiring"]), None)
        retiring_type = retiring.type_id if retiring else ""
        options = [Option("retire", "Retire that relationship too")]
        for el in rows:
            if el.action != "new" or not el.type_id or (retiring_type and el.type_id != retiring_type):
                continue
            options.append(Option(f"move:{el.ref}", f"Move it to {el.name}"))
            if len(options) >= 4:
                break
        options.append(Option("keep_element", f"Keep {d.get('retiring_name') or d['retiring']}"))
        options.append(Option("leave", "Leave it for now"))
        other = d.get("other_name") or d["other"]
        return Question(
            qid=f"dangling:{d['relationship_id']}",
            kind="dangling",
            layer=self.layer(retiring_type) if retiring_type else "",
            about=f"relationship:{d['relationship_id']}",
            text=(
                f"{d.get('retiring_name') or d['retiring']} is retired, but {other} still has a "
                f"'{d['relationship']}' relationship with it. What happens to that?"
            ),
            options=options,
            blocking=False,
        )

    def _isolated(self, iso: dict[str, Any], rows: list[ProposedElement]) -> Question:
        el = next((x for x in rows if x.ref == iso.get("ref")), None)
        type_id = iso.get("type_id") or (el.type_id if el else "")
        options = []
        if type_id:
            seen = {x.element_id for x in rows if x.element_id}
            for c in self._search(iso.get("name", ""), tuple(LAYER_RANK)):
                if c["element_id"] in seen:
                    continue
                choices = self._relationships_between(type_id, c["type_id"])
                if choices:
                    options.append(
                        Option(
                            f"serve:{c['element_id']}",
                            f"{c['name']} [{c['element_id']}] — {self._type_name(c['type_id'])}",
                            choices=choices,
                        )
                    )
                if len(options) >= 4:
                    break
        options.append(Option("leave", "Leave it"))
        return Question(
            qid=f"isolated:{norm(iso.get('name', ''))}",
            kind="isolated",
            layer=self.layer(type_id),
            about=f"element:{el.row}" if el else "change",
            text=f"{iso.get('name')} is new and connected to nothing that exists. What does it serve or use?",
            options=options,
            blocking=False,
        )

    # ------------------------------------------------------------ answers
    def apply_answer(
        self,
        result: ProposalResult,
        question: Question,
        key: str,
        text: str = "",
        choice: str = "",
        actor: str = "",
    ) -> str:
        """Apply a picked choice to the draft and record it. Returns the answer in words.

        Raises `AnswerError` when the choice is not one the question offers, or lacks what it needs.
        """
        option = next((o for o in question.options if o.key == key), None)
        if option is None:
            raise AnswerError(f"{key!r} is not one of the choices for this question")
        text = (text or "").strip()
        if option.needs and not text:
            raise AnswerError(f"{option.label}: {option.needs} is needed")
        if option.needs == "url" and not re.match(r"^https?://\S+$", text):
            raise AnswerError("the page must be a web address starting with http:// or https://")
        if option.choices and not choice:
            if len(option.choices) == 1:
                choice = option.choices[0]["key"]
            else:
                raise AnswerError(
                    f"{option.label}: pick one of {', '.join(c['label'] for c in option.choices)}"
                )
        if option.choices and choice not in {c["key"] for c in option.choices}:
            raise AnswerError(f"{choice!r} is not one of the choices offered")
        holds = key in ("leave", "keep")
        said = self._apply(result, question, key, text, choice)
        result.answers[question.qid] = {
            "question": question.text,
            "kind": question.kind,
            "key": key,
            "text": text,
            "choice": choice,
            "said": said,
            "holds": holds,
            "by": actor,
            "at": now(),
        }
        return said

    def _row(self, result: ProposalResult, about: str) -> Any:
        kind, _, n = about.partition(":")
        pool = result.elements if kind == "element" else result.relationships
        return next((x for x in pool if str(x.row) == n), None)

    def _next_row(self, pool: list) -> int:
        return max((x.row for x in pool), default=0) + 1

    def _add_existing(self, result: ProposalResult, element_id: str) -> Any:
        """The row for an existing element, added to the draft (its states as they are) if missing."""
        from ea.agent.proposal import ProposedElement

        for el in result.elements:
            if el.element_id == element_id or el.existing_id == element_id:
                el.include = True
                return el
        e = self.backend.get_element(element_id)
        if e is None:
            raise AnswerError(f"{element_id} is not in the repository")
        el = ProposedElement(
            row=self._next_row(result.elements),
            type_label=self._type_name(e.type_id),
            name=e.name,
            existing_id=e.element_id,
        )
        result.elements.append(el)
        return el

    def _add_new(self, result: ProposalResult, type_id: str, name: str) -> Any:
        from ea.agent.proposal import ProposedElement

        el = ProposedElement(
            row=self._next_row(result.elements),
            type_label=self._type_name(type_id),
            name=name,
            current_state="proposed",
            target_state="new",
        )
        result.elements.append(el)
        return el

    def _add_relationship(self, result: ProposalResult, a: str, b: str, choice: str) -> Any:
        """A relationship between two named ends, `a` and `b`, as the choice says (`out:` a→b, `in:` b→a)."""
        from ea.agent.proposal import ProposedRelationship

        direction, _, rel_id = choice.partition(":")
        rt = self.registry.rel_types.get(rel_id)
        if rt is None:
            raise AnswerError(f"{rel_id!r} is not a relationship of the metamodel")
        src, dst = (a, b) if direction == "out" else (b, a)
        rel = ProposedRelationship(
            row=self._next_row(result.relationships),
            source=src,
            relationship=rt.name,
            target=dst,
            target_state="new",
        )
        result.relationships.append(rel)
        return rel

    def _named(self, result: ProposalResult, ref: str) -> str:
        """How a relationship row names an element: by id when it exists, by its row's name when new."""
        if not ref.startswith("new:"):
            return ref
        el = next((x for x in result.elements if x.ref == ref), None)
        if el is None:
            raise AnswerError("that element is no longer in the draft")
        return el.name

    def _drop_row(self, result: ProposalResult, el: Any) -> None:
        el.include = False
        for r in result.relationships:
            if el.ref in (r.src_ref, r.dst_ref):
                r.include = False

    def _apply(self, result: ProposalResult, q: Question, key: str, text: str, choice: str) -> str:
        head, _, arg = key.partition(":")
        if q.kind in ("why", "business"):
            if head == "link":
                el = self._add_existing(result, arg)
                return f"It serves {el.name} [{arg}]."
            if head == "new":
                el = self._add_new(result, choice, text)
                return f"A new {self._type_name(choice)}: {el.name}."
            if key == "words":
                result.reason = text
                return f"Why: {text}"
            if key == "technical":
                result.technical = True
                return "A purely technical change."
        if q.kind == "work_package":
            if head == "wp":
                result.work_package = arg
                return f"Work package {arg}."
            result.work_package = text
            return f"A new work package: {text}."
        if q.kind == "description":
            el = self._row(result, q.about)
            if el is None:
                raise AnswerError("that row is no longer in the draft")
            el.description = text
            return text
        if q.kind == "type":
            el = self._row(result, q.about)
            if el is None:
                raise AnswerError("that row is no longer in the draft")
            el.type_label = self._type_name(arg)
            return f"{el.name or 'It'} is a {el.type_label}."
        if q.kind == "match":
            el = self._row(result, q.about)
            if el is None:
                raise AnswerError("that row is no longer in the draft")
            if head == "link":
                el.existing_id = arg
                return f"{el.name} is {arg}."
            el.confirmed_new = True
            return f"{el.name} is new."
        if q.kind in ("trace", "isolated", "boundary"):
            el = self._row(result, q.about) if q.about.startswith("element:") else None
            if el is None and q.kind != "isolated":
                raise AnswerError("that row is no longer in the draft")
            if head == "serve" and el is not None:
                if not arg.startswith("new:"):
                    other = self._add_existing(result, arg)
                    arg = other.element_id or other.existing_id or arg
                rel = self._add_relationship(
                    result, self._named(result, el.ref), self._named(result, arg), choice
                )
                return f"{rel.source} {rel.relationship} {rel.target}."
            if key == "drop" and el is not None:
                self._drop_row(result, el)
                return f"{el.name} is left out of this change."
            if head == "reference" and el is not None:
                self._drop_row(result, el)
                el.referenced_from, el.reference_url = arg, text
                system = self._named(result, arg)
                return f"{el.name} is linked from {system}: {text}"
            if key == "keep":
                return f"Kept: {text}"
            if key == "leave":
                return "Left as it is."
        if q.kind == "relationship":
            rel = self._row(result, q.about)
            if rel is None:
                raise AnswerError("that row is no longer in the draft")
            if key == "drop":
                rel.include = False
                return f"{rel.source} {rel.relationship} {rel.target} is left out."
            rt = self.registry.rel_types.get(arg)
            if rt is None:
                raise AnswerError(f"{arg!r} is not a relationship of the metamodel")
            if head == "reverse":
                rel.source, rel.target = rel.target, rel.source
            rel.relationship = rt.name
            return f"{rel.source} {rel.relationship} {rel.target}."
        if q.kind == "dangling":
            d = next(
                (
                    x
                    for x in (result.impact or {}).get("dangling") or []
                    if q.qid == f"dangling:{x['relationship_id']}"
                ),
                None,
            )
            if d is None:
                raise AnswerError("that relationship is no longer left behind")
            rt_name = d["relationship"]
            if key == "retire":
                from ea.agent.proposal import ProposedRelationship

                result.relationships.append(
                    ProposedRelationship(
                        row=self._next_row(result.relationships),
                        source=d["src_id"],
                        relationship=rt_name,
                        target=d["dst_id"],
                        target_state="decommission",
                    )
                )
                return f"{d['src_id']} {rt_name} {d['dst_id']} is retired too."
            if head == "move":
                from ea.agent.proposal import ProposedRelationship

                replacement = self._named(result, arg)
                src = replacement if d["src_id"] == d["retiring"] else d["src_id"]
                dst = replacement if d["dst_id"] == d["retiring"] else d["dst_id"]
                for s, t, state in ((d["src_id"], d["dst_id"], "decommission"), (src, dst, "new")):
                    result.relationships.append(
                        ProposedRelationship(
                            row=self._next_row(result.relationships),
                            source=s,
                            relationship=rt_name,
                            target=t,
                            target_state=state,
                        )
                    )
                return f"Moved to {replacement}: {src} {rt_name} {dst}."
            if key == "keep_element":
                el = next((x for x in result.elements if x.element_id == d["retiring"]), None)
                if el is not None:
                    el.target_state = "keep"
                return f"{d.get('retiring_name') or d['retiring']} is kept."
            if key == "leave":
                return "Left for now."
        if q.kind == "assistant":
            return text or next((o.label for o in q.options if o.key == key), key)
        raise AnswerError(f"{key!r} cannot be applied to a {q.kind} question")
