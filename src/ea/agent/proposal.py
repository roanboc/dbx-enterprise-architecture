"""Propose: from a design document to a change set on a branch.

A proposal is read (a hosted model reads free text and tables; the stub reads the tables of a
proposal template), every element is matched against the branch it will be applied to (by
identifier, then by name), every relationship is resolved against the metamodel, and what is
missing is listed back as pushback. Nothing is written until the architect applies the
reviewed change set to a branch.

A template is read against the metamodel first (`ea.services.templates`): a table under a
heading naming an element type holds that type, and a column naming an attribute fills it.
A page handed to a branch that already holds one of the same title revises it, updating what
the last pass wrote rather than writing it twice.
"""

from __future__ import annotations

import difflib
import json
import os
import re
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.request import Request, urlopen

from ea import capacity
from ea.agent.tools import ToolBox
from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, current_branch, use_branch
from ea.config import Settings
from ea.metamodel.registry import Registry
from ea.models import CURRENT_STATES, TARGET_STATES, Element, Proposal, ValidationError
from ea.services import BranchService, ChangeImpactService, ChangeInput, RepositoryService, TargetStateService
from ea.services.impact import CHANGING
from ea.services.roles import require
from ea.services.templates import (
    ELEMENT_FIELDS as ELEMENT_HEADERS,
)
from ea.services.templates import (
    RELATIONSHIP_FIELDS as RELATIONSHIP_HEADERS,
)
from ea.services.templates import (
    Reading,
    TemplateService,
    markdown_tables,
    split_front_matter,
)
from ea.services.templates import (
    cell as _cell,
)
from ea.views import View, view_of_change

MAX_LINK_BYTES = 400_000
MIN_DESCRIPTION_CHARS = 20
FUZZY_CUTOFF = 0.88
#: How much of each source is kept with the proposal, so a reviewer reads the page it came from.
MAX_SOURCE_CHARS = 200_000

__all__ = [
    "ELEMENT_HEADERS",
    "RELATIONSHIP_HEADERS",
    "ProposalResult",
    "ProposalService",
    "ProposedElement",
    "ProposedRelationship",
    "fetch_link",
    "markdown_tables",
    "parse_csv",
    "parse_markdown",
    "result_from_payload",
]


# ------------------------------------------------------------------ result


@dataclass
class ProposedElement:
    row: int
    type_label: str
    name: str
    existing_id: str = ""
    description: str = ""
    current_state: str = ""
    target_state: str = ""
    note: str = ""
    attrs: dict[str, str] = field(default_factory=dict)  # attribute values the page gives, by name
    type_id: str = ""
    element_id: str = ""  # resolved id when linked
    action: str = "new"  # link | new | unresolved
    match: str = ""  # id | exact | normalised | fuzzy | ""
    candidates: list[dict[str, str]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    include: bool = True
    on_branch_only: bool = False  # linked to an element an earlier pass created on this branch

    @property
    def ref(self) -> str:
        """How relationships refer to this element: its id when linked, `new:<name>` otherwise."""
        return self.element_id or f"new:{_norm(self.name)}"


@dataclass
class ProposedRelationship:
    row: int
    source: str
    relationship: str
    target: str
    note: str = ""
    qualifier: str = ""
    target_state: str = ""  # what the change does to the relationship: new, keep, decommission, …
    src_ref: str = ""
    dst_ref: str = ""
    rel_type_id: str = ""
    relationship_id: str = ""  # the relationship it names, when it exists already
    issues: list[str] = field(default_factory=list)
    include: bool = True


@dataclass
class ProposalResult:
    title: str = ""
    summary: str = ""
    work_package: str = ""  # as written: an id or a name
    work_package_id: str = ""  # resolved element id, or "" when it will be created
    elements: list[ProposedElement] = field(default_factory=list)
    relationships: list[ProposedRelationship] = field(default_factory=list)
    pushback: list[str] = field(default_factory=list)
    # What the reader found the sources do not say. Its own finding, not the pushback rule's,
    # so it is shown and kept beside the pushback and never stops Apply.
    missing: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    template_id: str = ""  # the organisation's template it was read with
    template_name: str = ""  # the template's name, kept or not
    revises: str = ""  # the proposal on the branch this one revises
    # What the pass it revises wrote and this page no longer carries: listed, never deleted.
    no_longer: list[dict[str, str]] = field(default_factory=list)
    impact: dict[str, Any] = field(default_factory=dict)  # the change impact, when assessed

    @property
    def complete(self) -> bool:
        return not self.pushback and not self.error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProposalResult:
        known_el = set(ProposedElement.__dataclass_fields__)
        known_rel = set(ProposedRelationship.__dataclass_fields__)
        return cls(
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            work_package=d.get("work_package", ""),
            work_package_id=d.get("work_package_id", ""),
            elements=[
                ProposedElement(**{k: v for k, v in e.items() if k in known_el})
                for e in d.get("elements") or []
            ],
            relationships=[
                ProposedRelationship(**{k: v for k, v in r.items() if k in known_rel})
                for r in d.get("relationships") or []
            ],
            pushback=list(d.get("pushback") or []),
            missing=list(d.get("missing") or []),
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            sources=list(d.get("sources") or []),
            error=d.get("error", ""),
            template_id=d.get("template_id", ""),
            template_name=d.get("template_name", ""),
            revises=d.get("revises", ""),
            no_longer=list(d.get("no_longer") or []),
            impact=dict(d.get("impact") or {}),
        )


# ----------------------------------------------------------------- parsing


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def parse_markdown(text: str, reading: Reading | None = None) -> ProposalResult:
    """A page in a proposal template as an unresolved result.

    With a `reading`, a table's type may come from the heading it sits under and a column may
    fill an attribute; without one, only the fixed column words are understood and an element
    table needs a Type column.
    """
    reading = reading or Reading()
    result = ProposalResult()
    decl, body = split_front_matter(text)
    if decl is not None:
        result.template_name = decl.name
    m = re.search(r"^#\s+(.+)$", body, re.M)
    if m:
        result.title = re.sub(r"^proposal\s*:\s*", "", m.group(1).strip(), flags=re.I).strip()
    m = re.search(r"^##\s+Summary\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if m:
        result.summary = " ".join(ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip())[:2000]
    for t in markdown_tables(body):
        kind = reading.table_kind(t)
        if kind == "elements":
            cols = {i: reading.element_column(h) for i, h in enumerate(t["headers"])}
            heading_type = reading.type_for_heading(t["heading"])
            heading_label = reading.registry.types[heading_type].name if heading_type else ""
            for n, row in enumerate(t["rows"], start=1):
                rec: dict[str, str] = {}
                attrs: dict[str, str] = {}
                for i, what in cols.items():
                    if not what or i >= len(row):
                        continue
                    if what.startswith("attr:"):
                        if row[i].strip():
                            attrs[what[5:]] = row[i].strip()
                    else:
                        rec[what] = row[i]
                if not rec.get("name") and not rec.get("type"):
                    continue
                result.elements.append(
                    ProposedElement(
                        row=n,
                        type_label=rec.get("type") or heading_label,
                        name=rec.get("name", ""),
                        existing_id=rec.get("existing_id", ""),
                        description=rec.get("description", ""),
                        current_state=_state(rec.get("current_state", "")),
                        target_state=_state(rec.get("target_state", "")),
                        note=rec.get("note", ""),
                        attrs=attrs,
                    )
                )
        elif kind == "relationships":
            cols = {i: reading.relationship_column(h) for i, h in enumerate(t["headers"])}
            for n, row in enumerate(t["rows"], start=1):
                rec = {what: row[i] for i, what in cols.items() if what and i < len(row)}
                if not (rec.get("source") or rec.get("target")):
                    continue
                result.relationships.append(
                    ProposedRelationship(
                        row=n,
                        source=rec.get("source", ""),
                        relationship=rec.get("relationship", ""),
                        target=rec.get("target", ""),
                        note=rec.get("note", ""),
                        qualifier=rec.get("qualifier", ""),
                        target_state=_state(rec.get("target_state", "")),
                    )
                )
        elif kind == "front" or (t["rows"] and all(len(r) >= 2 for r in t["rows"])):
            # the front table: | **Work package** | value |
            for row in t["rows"]:
                if _norm(row[0]) in ("work package", "workpackage", "initiative") and len(row) > 1:
                    result.work_package = _cell(row[1])
    if not result.work_package:
        m = re.search(r"work package[^\n:|]*[:|]\s*`?([A-Za-z][A-Za-z0-9 _.-]{1,80})`?", body, re.I)
        if m and not m.group(1).lower().startswith("wp-…"):
            result.work_package = m.group(1).strip()
    if result.work_package.startswith("WP-…") or result.work_package.lower().startswith("wp-… ("):
        result.work_package = ""
    # rows are numbered in reading order across every table, so a row number names one row
    for n, el in enumerate(result.elements, start=1):
        el.row = n
    for n, rel in enumerate(result.relationships, start=1):
        rel.row = n
    return result


def _state(text: str) -> str:
    return re.sub(r"[\s-]+", "_", (text or "").strip().lower())


def parse_csv(text: str, name: str = "", reading: Reading | None = None) -> ProposalResult:
    """A CSV with the Elements or the Relationships columns."""
    import csv
    import io

    result = ProposalResult()
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return result
    headers = [c.strip() for c in rows[0]]
    md = "| " + " | ".join(headers) + " |\n|" + "---|" * len(headers) + "\n"
    for r in rows[1:]:
        md += "| " + " | ".join(c.replace("|", "/") for c in r) + " |\n"
    return parse_markdown(md, reading)


def fetch_link(url: str, timeout: int = 10) -> str:
    """The text of a web page (tags stripped), capped; raises with a plain message when unreachable."""
    if not re.match(r"^https?://", url):
        raise ValueError(f"{url}: only http(s) links can be fetched")
    req = Request(url, headers={"User-Agent": "ea-repository/propose"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — the architect chose the link
        raw = resp.read(MAX_LINK_BYTES + 1)
    if len(raw) > MAX_LINK_BYTES:
        raise ValueError(f"{url}: larger than {MAX_LINK_BYTES // 1000} kB; paste the relevant part instead")
    text = raw.decode("utf-8", errors="replace")
    if "<html" in text.lower() or "<body" in text.lower():
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</(p|div|tr|h\d|li)>", "\n", text, flags=re.I)
        text = re.sub(r"</t[dh]>", " | ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------- resolving


class ProposalService:
    """Analyse sources into a reviewed change set, and apply it to a branch."""

    def __init__(
        self,
        backend: DatabaseBackend,
        registry: Registry,
        repo: RepositoryService,
        branches: BranchService,
        target: TargetStateService,
        settings: Settings | None = None,
        toolbox: ToolBox | None = None,
        templates: TemplateService | None = None,
        impact: ChangeImpactService | None = None,
    ):
        self.backend, self.registry, self.repo = backend, registry, repo
        self.branches, self.target = branches, target
        self.settings = settings or Settings.from_env()
        self.toolbox = toolbox
        self.templates = templates or TemplateService(backend, registry)
        self.impact = impact or ChangeImpactService(backend, registry)
        self.provider = self._make_provider()

    # ------------------------------------------------------------ provider
    def _make_provider(self):
        choice = self.settings.agent_provider
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        if choice == "anthropic" or (choice == "auto" and has_key):
            try:
                return AnthropicProposalProvider(self.settings.agent_model)
            except Exception:  # noqa: BLE001 — missing SDK or credentials; the stub keeps the page usable
                if choice == "anthropic":
                    raise
        return StubProposalProvider()

    # ------------------------------------------------------------- analyse
    def analyse(
        self, sources: list[dict[str, str]], branch_id: str | None = None, template: str | None = None
    ) -> ProposalResult:
        """`sources`: [{kind: text|file|link, name, text}]. Returns the resolved, validated result.

        `branch_id` is the branch the proposal will be applied to: the reader looks the
        elements up there, so what an earlier apply created on it is found, not proposed again.
        None reads the current branch.

        The page is read with the template its own front matter names; failing that with
        `template`, the key of a template the organisation keeps or of a starter
        (`TemplateService.offered`); failing both, with the metamodel's own names.
        """
        with _on(branch_id):
            first = next((s.get("text") for s in sources if (s.get("text") or "").strip()), None)
            reading, template_id, template_name = self.templates.reading(template, first)
            result = self.provider.extract(sources, self, reading)
            result.template_id = template_id
            result.template_name = template_name or result.template_name
            result.sources = [
                {
                    "kind": s.get("kind", ""),
                    "name": s.get("name", ""),
                    "chars": len(s.get("text") or ""),
                    "text": (s.get("text") or "")[:MAX_SOURCE_CHARS],
                }
                for s in sources
            ]
            return self._resolve(result)

    def resolve(self, result: ProposalResult, branch_id: str | None = None) -> ProposalResult:
        """Match every element and relationship against the repository and the metamodel; compute the pushback.

        Matched on `branch_id` (the branch the proposal is for), or on the current branch when None.
        """
        with _on(branch_id):
            return self._resolve(result)

    def _resolve(self, result: ProposalResult) -> ProposalResult:
        index = self._index()
        result.pushback = []
        on_branch = current_branch() != MAIN
        main_ids = self._on_main([el.element_id for el in result.elements]) if on_branch else None
        for el in result.elements:
            self._resolve_element(el, index)
            el.on_branch_only = bool(on_branch and el.element_id and el.element_id not in (main_ids or set()))
        refs = {}
        for el in result.elements:
            refs[_norm(el.name)] = el
            if el.element_id:
                refs[el.element_id.lower()] = el
        for rel in result.relationships:
            self._resolve_relationship(rel, refs, index)
        self._resolve_work_package(result)
        self._resolve_revision(result, on_branch)
        result.pushback = self.pushback(result)
        result.impact = self.impact.assess(self.change_input(result)).to_dict()
        return result

    def _on_main(self, ids: list[str]) -> set[str]:
        """Which of these elements `main` holds: the rest were created on the branch."""
        with use_branch(MAIN):
            return {e.element_id for e in self.backend.elements_by_ids([i for i in ids if i])}

    def _resolve_revision(self, result: ProposalResult, on_branch: bool) -> None:
        """The proposal this one revises — the latest of the same title applied to the branch —
        and what it wrote that this page no longer carries."""
        result.revises, result.no_longer = "", []
        if not on_branch or not result.title:
            return
        earlier = [
            p
            for p in self.backend.list_proposals(current_branch())
            if p.status == "applied" and _norm(p.title) == _norm(result.title)
        ]
        if not earlier:
            return
        last = earlier[0]  # newest first
        result.revises = last.proposal_id
        applied = (last.result or {}).get("applied") or {}
        carried = {el.element_id for el in result.elements if el.element_id}
        dropped = [
            i for i in (applied.get("created") or []) + (applied.get("linked") or []) if i not in carried
        ]
        names = {e.element_id: e for e in self.backend.elements_by_ids(dropped)}
        for i in dict.fromkeys(dropped):
            e = names.get(i)
            if e is not None and i != result.work_package_id:
                result.no_longer.append({"kind": "element", "id": i, "name": e.name})
        rel_carried = {r.relationship_id for r in result.relationships if r.relationship_id}
        for rid in applied.get("relationships") or []:
            if rid in rel_carried:
                continue
            r = self.backend.get_relationship(rid)
            if r is not None:
                label = f"{self._element_name(r.src_id)} {self._rel_name(r.rel_type_id)} {self._element_name(r.dst_id)}"
                result.no_longer.append({"kind": "relationship", "id": rid, "name": label})

    def _element_name(self, element_id: str) -> str:
        e = self.backend.get_element(element_id)
        return e.name if e else element_id

    def _rel_name(self, rel_type_id: str) -> str:
        r = self.registry.rel_types.get(rel_type_id)
        return r.name if r else rel_type_id

    def view(self, result: ProposalResult) -> View:
        """The change drawn before it is applied: the ticked elements with their states, the
        relationships among them, and what the change would leave pointing at an element it
        retires, so the gap is on the picture as well as in the list."""
        nodes: dict[str, dict[str, Any]] = {}
        for el in result.elements:
            if el.include and (el.type_id or el.element_id):
                nodes[el.ref] = {
                    "element_id": el.ref,
                    "name": el.name or el.element_id,
                    "type_id": el.type_id,
                    "current_state": el.current_state or ("proposed" if el.action == "new" else "live"),
                    "target_state": el.target_state or ("new" if el.action == "new" else "keep"),
                    "focus": el.action == "new" or el.target_state in CHANGING,
                    "identified": el.action != "new",
                }
        edges = [
            {
                "src": r.src_ref,
                "dst": r.dst_ref,
                "label": self._rel_name(r.rel_type_id) if r.rel_type_id else r.relationship,
                "target_state": r.target_state or "undecided",
            }
            for r in result.relationships
            if r.include and r.src_ref and r.dst_ref
        ]
        dangling = (result.impact or {}).get("dangling") or []
        others = {e.element_id: e for e in self.backend.elements_by_ids([d["other"] for d in dangling])}
        for d in dangling:
            e = others.get(d["other"])
            if e is None:
                continue
            nodes.setdefault(
                e.element_id,
                {
                    "element_id": e.element_id,
                    "name": e.name,
                    "type_id": e.type_id,
                    "current_state": e.current_state,
                    "target_state": e.target_state,
                },
            )
            edges.append(
                {
                    "src": d["src_id"],
                    "dst": d["dst_id"],
                    "label": d["relationship"],
                    "target_state": "undecided",
                }
            )
        return view_of_change(
            self.registry, list(nodes.values()), edges, result.title or "The proposed change"
        )

    def change_input(self, result: ProposalResult) -> ChangeInput:
        """The ticked rows of a proposal as a change set to assess."""
        els = [el for el in result.elements if el.include]
        rels = [r for r in result.relationships if r.include]
        return ChangeInput(
            changed={
                el.element_id: el.target_state
                for el in els
                if el.action == "link" and el.target_state in CHANGING and not el.on_branch_only
            },
            new=[{"ref": el.ref, "name": el.name, "type_id": el.type_id} for el in els if el.action == "new"],
            links=[
                (r.src_ref, r.dst_ref)
                for r in rels
                if r.src_ref and r.dst_ref and r.target_state != "decommission"
            ],
            retired_relationships={
                r.relationship_id for r in rels if r.target_state == "decommission" and r.relationship_id
            },
            named={el.element_id for el in els if el.element_id},
            touched_types=[el.type_id for el in els if el.type_id],
        )

    def _index(self) -> dict[str, Any]:
        """Every element's identifier and name, to match a proposal against.

        **This one reads the whole model on purpose** (decision 0019). Matching a proposed
        name against a candidate set rather than against everything would change what the
        reader finds — it would link a new element to an existing one only when the
        shortlist happened to contain it — and a proposal that silently misses a match is
        worse than one that takes a moment. Only the identifier and the name are kept, not
        the elements, and the model is read in pages so the rows are never all held at once:
        at the capacity the application is assessed for that is about 100,000 short strings.
        """
        by_id: dict[str, Element] = {}
        by_name: dict[str, list[Element]] = {}
        for page in capacity.pages(
            lambda limit, offset: self.backend.find_elements(limit=limit, offset=offset)
        ):
            for e in page:
                by_id[e.element_id.lower()] = e
                by_name.setdefault(_norm(e.name), []).append(e)
        return {"by_id": by_id, "by_name": by_name, "names": list(by_name)}

    def _resolve_element(self, el: ProposedElement, index: dict[str, Any]) -> None:
        el.issues = []
        el.name = (el.name or "").strip()
        t = self.registry.resolve_type(el.type_label) if el.type_label else None
        if el.type_label and t is None:
            el.issues.append(f"type {el.type_label!r} is not in the metamodel")
        elif t is not None and not t.active:
            el.issues.append(f"type {t.name!r} is inactive in the metamodel")
        el.type_id = t.id if t else ""
        existing = None
        el.match, el.candidates = "", []
        if el.existing_id:
            existing = index["by_id"].get(el.existing_id.strip().lower())
            if existing is None:
                el.issues.append(f"existing id {el.existing_id!r} is not in the repository")
            else:
                el.match = "id"
        if existing is None and el.name:
            key = _norm(el.name)
            same = index["by_name"].get(key) or []
            if el.type_id:
                typed = [e for e in same if e.type_id == el.type_id]
                same = typed or same
            if len(same) == 1:
                existing, el.match = same[0], "exact"
            elif len(same) > 1:
                el.issues.append(
                    f"name {el.name!r} matches several elements: " + ", ".join(e.element_id for e in same[:5])
                )
                el.candidates = [
                    {"element_id": e.element_id, "name": e.name, "type_id": e.type_id} for e in same[:5]
                ]
            else:
                close = difflib.get_close_matches(key, index["names"], n=3, cutoff=FUZZY_CUTOFF)
                if close:
                    cands = [e for k in close for e in index["by_name"][k]]
                    if el.type_id:
                        cands = [e for e in cands if e.type_id == el.type_id] or cands
                    el.candidates = [
                        {"element_id": e.element_id, "name": e.name, "type_id": e.type_id} for e in cands[:5]
                    ]
        if existing is not None:
            el.element_id = existing.element_id
            el.action = "link"
            if not el.type_id:
                el.type_id, el.type_label = (
                    existing.type_id,
                    self.registry.types[existing.type_id].name
                    if existing.type_id in self.registry.types
                    else existing.type_id,
                )
            elif existing.type_id != el.type_id and not self.registry.is_a(existing.type_id, el.type_id):
                el.issues.append(
                    f"{existing.element_id} is a {self.registry.types[existing.type_id].name if existing.type_id in self.registry.types else existing.type_id}, not a {el.type_label}"
                )
            if not el.current_state:
                el.current_state = existing.current_state
            if not el.target_state:
                el.target_state = existing.target_state
        else:
            el.element_id = ""
            el.action = "new"
            if el.candidates and not el.issues:
                el.issues.append(
                    "a similar element exists: "
                    + ", ".join(f"{c['name']} [{c['element_id']}]" for c in el.candidates)
                    + " — put its id in Existing id to link it, or keep it new"
                )
            if not el.name:
                el.issues.append("name is missing")
            if not el.type_id and not el.type_label:
                # A row that named a type the metamodel does not carry has already been told
                # so; saying 'type is missing' as well denies that it named one.
                el.issues.append("type is missing")
            if len((el.description or "").strip()) < MIN_DESCRIPTION_CHARS:
                el.issues.append("description is missing or shorter than one sentence")
            el.current_state = el.current_state or "proposed"
            el.target_state = el.target_state or "new"
        if el.current_state and el.current_state not in CURRENT_STATES:
            el.issues.append(f"current state {el.current_state!r} is not one of {', '.join(CURRENT_STATES)}")
        if el.target_state and el.target_state not in TARGET_STATES:
            el.issues.append(f"target state {el.target_state!r} is not one of {', '.join(TARGET_STATES)}")
        if el.action == "link" and not el.current_state:
            el.issues.append("current state is missing")
        if el.action == "link" and not el.target_state:
            el.issues.append("target state is missing")
        if el.attrs and el.type_id:
            el.issues.extend(self._attr_issues(el.type_id, el.attrs))

    def _attr_issues(self, type_id: str, attrs: dict[str, str]) -> list[str]:
        """What the attribute values a page gives say against the type: one it does not declare,
        or a value its rules refuse. Only the values given are checked — a blank cell sets nothing."""
        declared = {a.name for a in self.registry.attributes_for(type_id)}
        out = []
        for name, value in attrs.items():
            if name not in declared:
                out.append(f"attribute {name!r} is not declared on {self._type_name(type_id)}")
                continue
            out.extend(
                i.message
                for i in self.registry.validate_element(type_id, {name: value})
                if i.code != "missing_attribute"
            )
        return out

    def _resolve_ref(self, text: str, refs: dict[str, ProposedElement], index: dict[str, Any]):
        """(ref, type_id, label) for an endpoint written as a name or an id."""
        key = (text or "").strip()
        if not key:
            return "", "", ""
        el = refs.get(key.lower()) or refs.get(_norm(key))
        if el is not None:
            return el.ref, el.type_id, el.name
        e = index["by_id"].get(key.lower())
        if e is None:
            same = index["by_name"].get(_norm(key)) or []
            e = same[0] if len(same) == 1 else None
        if e is not None:
            return e.element_id, e.type_id, e.name
        return "", "", key

    def _resolve_relationship(
        self, rel: ProposedRelationship, refs: dict[str, ProposedElement], index: dict[str, Any]
    ) -> None:
        rel.issues = []
        rel.src_ref, src_t, _ = self._resolve_ref(rel.source, refs, index)
        rel.dst_ref, dst_t, _ = self._resolve_ref(rel.target, refs, index)
        if not rel.src_ref:
            rel.issues.append(f"source {rel.source!r} is neither in the Elements table nor in the repository")
        if not rel.dst_ref:
            rel.issues.append(f"target {rel.target!r} is neither in the Elements table nor in the repository")
        rel.rel_type_id = rel.relationship_id = ""
        if rel.target_state and rel.target_state not in TARGET_STATES:
            rel.issues.append(f"target state {rel.target_state!r} is not one of {', '.join(TARGET_STATES)}")
        if not rel.relationship:
            rel.issues.append("relationship is missing")
        elif src_t and dst_t:
            rt = self.registry.resolve_rel_type(rel.relationship, src_t, dst_t)
            if rt is None:
                allowed = ", ".join(r.name for r in self.registry.allowed_rel_types(src_t, dst_t)) or "none"
                rel.issues.append(
                    f"no relationship {rel.relationship!r} from {self._type_name(src_t)} to {self._type_name(dst_t)}; allowed: {allowed}"
                )
            else:
                rel.rel_type_id = rt.id
                if rel.qualifier and rt.qualifiers and rel.qualifier not in rt.qualifiers:
                    rel.issues.append(f"qualifier {rel.qualifier!r} is not one of {', '.join(rt.qualifiers)}")
                rel.relationship_id = self._existing_relationship(rel)
        if rel.target_state == "decommission" and not rel.relationship_id and not rel.issues:
            rel.issues.append("there is no such relationship to decommission")

    def _existing_relationship(self, rel: ProposedRelationship) -> str:
        """The relationship this row names when both ends exist and it is already there."""
        if (
            not rel.src_ref
            or not rel.dst_ref
            or rel.src_ref.startswith("new:")
            or rel.dst_ref.startswith("new:")
        ):
            return ""
        for r in self.backend.relationships_of(rel.src_ref, "out"):
            if (r.rel_type_id, r.dst_id, r.qualifier or "") == (
                rel.rel_type_id,
                rel.dst_ref,
                rel.qualifier or "",
            ):
                return r.relationship_id
        return ""

    def _type_name(self, type_id: str) -> str:
        t = self.registry.get_type(type_id)
        return t.name if t else type_id

    def _resolve_work_package(self, result: ProposalResult) -> None:
        result.work_package_id = ""
        text = (result.work_package or "").strip()
        if not text:
            return
        wp_type = self.target.work_package_type()
        e = self.backend.get_element(text)
        if e is None:
            for w in self.target.work_packages():
                if _norm(w.name) == _norm(text) or w.element_id.lower() == text.lower():
                    e = w
                    break
        if e is not None and (not wp_type or e.type_id == wp_type):
            result.work_package_id = e.element_id

    # ------------------------------------------------------------- pushback
    def pushback(self, result: ProposalResult) -> list[str]:
        """The minimum the architect must add before the proposal can be applied."""
        out: list[str] = []
        if result.error:
            out.append(result.error)
        if not result.elements:
            out.append(
                "No elements were identified. Add an Elements table (Type, Name, Existing id, Description, Current state, Target state) as in the Proposal Template."
            )
        for el in result.elements:
            if not el.include:
                continue
            for issue in el.issues:
                out.append(f"Element row {el.row} ({el.name or el.type_label or '?'}): {issue}")
        for rel in result.relationships:
            if not rel.include:
                continue
            for issue in rel.issues:
                out.append(
                    f"Relationship row {rel.row} ({rel.source} {rel.relationship} {rel.target}): {issue}"
                )
        if not (result.work_package or "").strip():
            out.append(
                "Name the work package (initiative) the change belongs to: an existing id, or the name of a new one."
            )
        return out

    # ---------------------------------------------------------------- apply
    def apply(self, result: ProposalResult, branch_id: str, actor: str) -> dict[str, Any]:
        """Write the ticked rows to the branch and keep the proposal with it. Pushback stops it."""
        require("propose", what="apply a proposal")
        # Resolved on the branch it is written to, whatever branch the caller stands on: a
        # revised page applied again then links what the last apply created instead of
        # creating it a second time.
        result = self.resolve(result, branch_id)
        if result.pushback:
            raise ValidationError([_issue(p) for p in result.pushback])
        branch = self.branches.get(branch_id)
        if branch.status != "open":
            raise ValidationError([_issue(f"branch {branch_id} is {branch.status}")])
        created, linked, rels, retired, skipped = [], [], [], [], []
        # what an earlier pass created on this branch: a relationship to it is still new
        fresh = {el.element_id for el in result.elements if el.on_branch_only}
        with use_branch(branch_id):
            wp_id = result.work_package_id
            if not wp_id and result.work_package:
                wp_type = self.target.work_package_type()
                if wp_type:
                    wp = self.repo.create_element(
                        wp_type,
                        result.work_package,
                        actor,
                        description_md=result.summary
                        or f"Work package created from the proposal '{result.title}'.",
                        current_state="proposed",
                        target_state="new",
                        origin="proposal",
                    )
                    wp_id = wp.element_id
                    created.append(wp_id)
            ids: dict[str, str] = {}
            for el in result.elements:
                if not el.include:
                    skipped.append(el.ref)
                    continue
                if el.action == "link":
                    ids[el.ref] = el.element_id
                    current = self.repo.element(el.element_id)
                    changes = {}
                    if el.target_state and el.target_state != current.target_state:
                        changes["target_state"] = el.target_state
                    if el.current_state and el.current_state != current.current_state:
                        changes["current_state"] = el.current_state
                    if (
                        wp_id
                        and el.target_state not in ("", "undecided", "keep")
                        and current.target_work_package != wp_id
                    ):
                        changes["target_work_package"] = wp_id
                    if el.note and el.note != current.target_note:
                        changes["target_note"] = el.note
                    if el.attrs and {**current.attrs, **el.attrs} != current.attrs:
                        # a filled cell overwrites; a blank one never empties (it is not in attrs)
                        changes["attrs"] = {**current.attrs, **el.attrs}
                    if el.on_branch_only and el.description and el.description != current.description_md:
                        # an element this proposal created on the branch takes the revised text;
                        # one main already holds keeps its own, however short the page's is
                        changes["description_md"] = el.description
                    if changes:
                        self.repo.update_element(el.element_id, actor, current.version, **changes)
                    linked.append(el.element_id)
                else:
                    e = self.repo.create_element(
                        el.type_id,
                        el.name,
                        actor,
                        description_md=el.description,
                        current_state=el.current_state or "proposed",
                        target_state=el.target_state or "new",
                        target_work_package=wp_id,
                        target_note=el.note,
                        attrs=dict(el.attrs),
                        origin="proposal",
                    )
                    ids[el.ref] = e.element_id
                    created.append(e.element_id)
            for rel in result.relationships:
                if not rel.include:
                    continue
                src, dst = ids.get(rel.src_ref, rel.src_ref), ids.get(rel.dst_ref, rel.dst_ref)
                if src.startswith("new:") or dst.startswith("new:"):
                    skipped.append(f"relationship row {rel.row}: an end was not applied")
                    continue
                src_e, dst_e = self.repo.element(src), self.repo.element(dst)
                rt = self.registry.resolve_rel_type(rel.relationship, src_e.type_id, dst_e.type_id)
                if rt is None:
                    skipped.append(f"relationship row {rel.row}: no such relationship between the ends")
                    continue
                if rel.target_state == "decommission":
                    self.repo.set_relationship_states(
                        rel.relationship_id,
                        actor,
                        target_state="decommission",
                        target_work_package=wp_id or None,
                        target_note=rel.note or None,
                    )
                    retired.append(rel.relationship_id)
                    continue
                target_state = rel.target_state or (
                    "new" if ({src, dst} & (set(created) | fresh)) else "keep"
                )
                changing = target_state not in ("keep", "undecided")
                r = self.repo.add_relationship(
                    rt.id,
                    src,
                    dst,
                    actor,
                    rel.qualifier or "",
                    origin="proposal",
                    current_state="proposed" if target_state == "new" else "live",
                    target_state=target_state,
                    target_work_package=wp_id if changing else "",
                    target_note=rel.note,
                )
                if rel.target_state and r.target_state != rel.target_state:
                    # it was there already, meant for something else: the page says what now
                    r = self.repo.set_relationship_states(
                        r.relationship_id,
                        actor,
                        target_state=rel.target_state,
                        target_work_package=wp_id if changing else None,
                        target_note=rel.note or None,
                    )
                rels.append(r.relationship_id)
        applied = {
            "created": created,
            "linked": linked,
            "relationships": rels,
            "retired": retired,
            "skipped": skipped,
        }
        record = self.backend.save_proposal(
            Proposal(
                proposal_id="",
                branch_id=branch_id,
                title=result.title or branch.name,
                sources=result.sources,
                result=dict(result.to_dict(), applied=applied),
                pushback=[],
                status="applied",
                created_by=actor,
                template_id=result.template_id,
                revises=result.revises,
            )
        )
        return {
            "proposal_id": record.proposal_id,
            "branch_id": branch_id,
            "work_package_id": wp_id,
            "revises": result.revises,
            "no_longer": result.no_longer,
            "impact": result.impact,
            **applied,
        }


def _on(branch_id: str | None):
    """The branch a proposal is matched and written on, or the current one when None."""
    return use_branch(branch_id) if branch_id else nullcontext()


def _issue(message: str):
    from ea.models import Issue

    return Issue("error", "proposal", message)


# --------------------------------------------------------------- providers


class StubProposalProvider:
    """No language model: reads a template's tables (Markdown or CSV) and nothing else."""

    name = "stub"
    model = ""

    def extract(
        self, sources: list[dict[str, str]], service: ProposalService, reading: Reading | None = None
    ) -> ProposalResult:
        reading = reading or Reading(service.registry)
        merged = ProposalResult(provider=self.name)
        for s in sources:
            text = s.get("text") or ""
            name = (s.get("name") or "").lower()
            part = parse_csv(text, name, reading) if name.endswith(".csv") else parse_markdown(text, reading)
            merged.template_name = merged.template_name or part.template_name
            merged.title = merged.title or part.title
            merged.summary = merged.summary or part.summary
            merged.work_package = merged.work_package or part.work_package
            offset = len(merged.elements)
            for el in part.elements:
                el.row += offset
                merged.elements.append(el)
            offset = len(merged.relationships)
            for rel in part.relationships:
                rel.row += offset
                merged.relationships.append(rel)
        if not merged.elements and any((s.get("text") or "").strip() for s in sources):
            merged.error = (
                "No language model is configured, so only a proposal template's tables can be read. "
                "Download a template, fill in its element and relationship tables, and paste or upload it."
            )
        return merged


SUBMIT_TOOL = {
    "name": "submit_proposal",
    "description": (
        "Hand in the structured proposal you extracted from the sources. Call it exactly once, at the end. "
        "List every element the change touches (existing ones with their repository id when you found it with "
        "search_elements or get_element; new ones with a description of at least one sentence) and every "
        "relationship between them, using the metamodel's relationship names."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string", "description": "two to five sentences"},
            "work_package": {
                "type": "string",
                "description": "the work package's id if it exists, else its name",
            },
            "elements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "an element type name of the metamodel"},
                        "name": {"type": "string"},
                        "existing_id": {
                            "type": "string",
                            "description": "repository id when the element exists",
                        },
                        "description": {"type": "string"},
                        "current_state": {"type": "string", "enum": CURRENT_STATES},
                        "target_state": {"type": "string", "enum": TARGET_STATES},
                        "note": {"type": "string"},
                        "attributes": {
                            "type": "object",
                            "description": "attribute values the sources give, by the metamodel's attribute name",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["type", "name"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "element name as listed, or repository id",
                        },
                        "relationship": {
                            "type": "string",
                            "description": "a relationship name of the metamodel",
                        },
                        "target": {"type": "string"},
                        "qualifier": {"type": "string"},
                        "target_state": {
                            "type": "string",
                            "enum": TARGET_STATES,
                            "description": "what the change does to the relationship: new, keep, decommission, …",
                        },
                        "note": {"type": "string"},
                    },
                    "required": ["source", "relationship", "target"],
                },
            },
            "missing": {
                "type": "array",
                "items": {"type": "string"},
                "description": "what the sources do not say and the architect must add",
            },
        },
        "required": ["title", "elements", "relationships"],
    },
}

PROPOSAL_PROMPT = """You turn a solution design document into a change set for an enterprise architecture repository.

Read the sources the architect handed in. Identify every architectural element the change touches and every relationship between them. For each element decide whether it already exists in the repository: use `search_elements` (by name, then by likely synonyms) and `get_element` to confirm, and give its repository id as `existing_id` when it does. Elements you cannot find are new: give them a type of the loaded metamodel, a description of at least one sentence taken from the sources, current state `proposed` and target state `new` unless the document says otherwise. Existing elements keep their states unless the document changes them (an element being replaced is `decommission`, one being modified is `change`, one merely used is `keep`).

Relationships must use the relationship names of the metamodel between the two element types; call `allowed_relationships` for the pair when unsure. A relationship the change removes is `decommission`; one it adds is `new`; one it only relies on is `keep`. Before proposing that an element is decommissioned or changed, look at what depends on it with `impact` or `neighbours`, and name in `missing` anything that would be left without it. `branch_changes` says what the branch already holds from earlier passes; reuse those elements rather than proposing them again. Give attribute values the sources state under `attributes`, by the metamodel's attribute name. Do not invent elements or relationships the sources do not support. Put what the sources fail to say into `missing`, element by element, so the architect can complete the document.

Finish by calling `submit_proposal` exactly once.

The loaded metamodel:
"""


#: The read tools the hosted reader is given, beside `submit_proposal`: enough to find what
#: exists, to place a new element among it, and to see what a change would disturb.
READER_TOOLS = (
    "list_types",
    "search_elements",
    "get_element",
    "neighbours",
    "impact",
    "allowed_relationships",
    "branch_changes",
)


class AnthropicProposalProvider:
    """A hosted model reads free text and tables, checks the repository with tools, and submits a structured result."""

    name = "anthropic"

    def __init__(self, model: str, max_turns: int = 16):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_turns = max_turns

    def extract(
        self, sources: list[dict[str, str]], service: ProposalService, reading: Reading | None = None
    ) -> ProposalResult:
        anthropic = self._anthropic
        toolbox = service.toolbox
        if toolbox is None:
            return ProposalResult(provider=self.name, model=self.model, error="no toolbox for the model")
        read_tools = [t for t in toolbox.specs() if t["name"] in READER_TOOLS]
        tools = read_tools + [SUBMIT_TOOL]
        system = (
            PROPOSAL_PROMPT
            + service.registry.summary_markdown()
            + "\n\nHow the page is read:\n"
            + (reading or Reading(service.registry)).summary()
        )
        content = "\n\n".join(
            f"--- Source {i + 1}: {s.get('kind', 'text')} {s.get('name', '')} ---\n{(s.get('text') or '')[:60_000]}"
            for i, s in enumerate(sources)
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": content or "(no sources)"}]
        submitted: dict[str, Any] | None = None
        for _ in range(self.max_turns):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=16000,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    tools=tools,
                    messages=messages,
                )
            except anthropic.APIError as exc:
                return ProposalResult(provider=self.name, model=self.model, error=f"model API error: {exc}")
            messages.append({"role": "assistant", "content": response.content})
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                break
            results = []
            for tu in uses:
                if tu.name == "submit_proposal":
                    submitted = dict(tu.input or {})
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "received"})
                else:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": toolbox.call(tu.name, dict(tu.input or {})),
                        }
                    )
            messages.append({"role": "user", "content": results})
            if submitted is not None:
                break
        if submitted is None:
            return ProposalResult(
                provider=self.name,
                model=self.model,
                error="the model did not submit a proposal; try again or use the template",
            )
        return result_from_payload(submitted, self.name, self.model)


def result_from_payload(payload: dict[str, Any], provider: str = "", model: str = "") -> ProposalResult:
    """A structured payload (the model's, or the page's edited rows) as an unresolved result."""
    result = ProposalResult(
        title=str(payload.get("title") or ""),
        summary=str(payload.get("summary") or ""),
        work_package=str(payload.get("work_package") or ""),
        provider=provider,
        model=model,
        template_id=str(payload.get("template_id") or ""),
        template_name=str(payload.get("template_name") or ""),
        sources=[dict(x) for x in payload.get("sources") or [] if isinstance(x, dict)],
    )
    for i, e in enumerate(payload.get("elements") or [], start=1):
        result.elements.append(
            ProposedElement(
                row=int(e.get("row") or i),
                type_label=str(e.get("type") or e.get("type_label") or ""),
                name=str(e.get("name") or ""),
                existing_id=str(e.get("existing_id") or ""),
                description=str(e.get("description") or ""),
                current_state=_state(str(e.get("current_state") or "")),
                target_state=_state(str(e.get("target_state") or "")),
                note=str(e.get("note") or ""),
                attrs={
                    str(k): str(v)
                    for k, v in (e.get("attributes") or e.get("attrs") or {}).items()
                    if k and v not in (None, "")
                },
                include=bool(e.get("include", True)),
            )
        )
    for i, r in enumerate(payload.get("relationships") or [], start=1):
        result.relationships.append(
            ProposedRelationship(
                row=int(r.get("row") or i),
                source=str(r.get("source") or ""),
                relationship=str(r.get("relationship") or ""),
                target=str(r.get("target") or ""),
                qualifier=str(r.get("qualifier") or ""),
                note=str(r.get("note") or ""),
                target_state=_state(str(r.get("target_state") or "")),
                include=bool(r.get("include", True)),
            )
        )
    result.missing = [str(m) for m in payload.get("missing") or [] if m]
    return result


def result_json(result: ProposalResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, default=str)
