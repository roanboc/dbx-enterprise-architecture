"""Proposal templates: the document shapes an organisation proposes a change in (DOBJ3.9).

A template is a Markdown document an architect fills in, and it is read **against the
metamodel first**: a table under a heading that names an element type — its name or its
plural, *Application components* — holds that type, and a column whose header names an
element field or an attribute of the metamodel — *Owner* — fills it. The front matter names
the metamodel the template is typed in and declares only what the template names
differently. A well-named template therefore needs no declaration at all, and nothing here
knows a framework (principle `P5`): the names come from the registry and from the document.

An organisation keeps its own templates in the store. The repository ships starters beside
the packs they are typed in (`packs/<pack>/proposal-template.md`), offered for download and
for adding to an organisation's own.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ea.backend.base import DatabaseBackend
from ea.config import ROOT
from ea.metamodel.registry import Registry
from ea.models import Issue, NotFoundError, ProposalTemplate, ValidationError
from ea.services.roles import require

log = logging.getLogger(__name__)

#: The file a pack directory's starter template is recognised by.
TEMPLATE_FILE = "proposal-template.md"
STARTER_DIR = ROOT / "packs"

_FRONT = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_TABLE_ROW = re.compile(r"^\s*\|(.*)\|\s*$")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_NUMBERING = re.compile(r"^\s*(\d+(\.\d+)*\.?|[A-Z]\.)\s+")

#: The element fields a column can fill, by the words a header may use for them.
ELEMENT_FIELDS = {
    "type": "type",
    "element_type": "type",
    "name": "name",
    "element": "name",
    "existing_id": "existing_id",
    "existing_identifier": "existing_id",
    "id": "existing_id",
    "identifier": "existing_id",
    "description": "description",
    "current_state": "current_state",
    "current": "current_state",
    "target_state": "target_state",
    "target": "target_state",
    "note": "note",
    "notes": "note",
}
#: The relationship fields a column can fill.
RELATIONSHIP_FIELDS = {
    "source": "source",
    "from": "source",
    "relationship": "relationship",
    "relationship_type": "relationship",
    "rel_type": "relationship",
    "relation": "relationship",
    "target": "target",
    "to": "target",
    "note": "note",
    "notes": "note",
    "qualifier": "qualifier",
    "role": "qualifier",
    "target_state": "target_state",
    "state": "target_state",
}


def norm_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def norm_heading(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _NUMBERING.sub("", text or "").lower()).strip()


def cell(text: str) -> str:
    """A table cell without the emphasis or code marks around it."""
    return re.sub(r"^[`*_ ]+|[`*_ ]+$", "", (text or "").strip())


def _split_row(line: str) -> list[str]:
    inner = _TABLE_ROW.match(line).group(1)
    return [c.strip() for c in re.split(r"(?<!\\)\|", inner)]


def markdown_tables(text: str) -> list[dict[str, Any]]:
    """Every pipe table in the text: {'heading', 'headers', 'rows'} with the heading it sits under."""
    tables: list[dict[str, Any]] = []
    heading = ""
    lines = text.splitlines()
    i = 0
    in_fence = False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("#"):
            heading = line.lstrip("#").strip()
        if not in_fence and _TABLE_ROW.match(line) and i + 1 < len(lines) and _SEPARATOR.match(lines[i + 1]):
            headers = [cell(h) for h in _split_row(line)]
            rows = []
            i += 2
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                cells = [cell(c) for c in _split_row(lines[i])]
                cells += [""] * (len(headers) - len(cells))
                rows.append(cells[: len(headers)])
                i += 1
            tables.append({"heading": heading, "headers": headers, "rows": rows})
            continue
        i += 1
    return tables


# --------------------------------------------------------------- declaration


@dataclass
class Declaration:
    """What a template's front matter says of it: its name, its metamodel, and what it names
    differently from the metamodel (`sections`: heading → type; `columns`: header → field or
    attribute)."""

    name: str = ""
    metamodel: str = ""
    description: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    columns: dict[str, str] = field(default_factory=dict)


def split_front_matter(text: str) -> tuple[Declaration | None, str]:
    """The template's declaration, if its front matter carries one, and the body after it.

    Front matter that is not YAML, or says nothing of a template, is dropped from the body and
    declares nothing: a page is read the same with or without it.
    """
    m = _FRONT.match(text or "")
    if not m:
        return None, text or ""
    body = (text or "")[m.end() :]
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        log.info("front matter is not YAML (%s); read as a page without a declaration", exc)
        return None, body
    block = data.get("proposal_template") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return None, body

    def mapping(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if k and v}

    return (
        Declaration(
            name=str(block.get("name") or "").strip(),
            metamodel=str(block.get("metamodel") or "").strip(),
            description=" ".join(str(block.get("description") or "").split()),
            sections=mapping(block.get("sections")),
            columns=mapping(block.get("columns")),
        ),
        body,
    )


# ------------------------------------------------------------------- reading


class Reading:
    """How one template is read against one metamodel: which type a heading holds, and which
    field or attribute a column fills. The declaration is consulted first, the metamodel's own
    names second; without a registry only the fixed field words are understood."""

    def __init__(self, registry: Registry | None = None, declaration: Declaration | None = None):
        self.registry = registry
        self.declaration = declaration or Declaration()
        self._sections = {norm_heading(k): v for k, v in self.declaration.sections.items()}
        self._columns = {norm_header(k): v for k, v in self.declaration.columns.items()}
        self._attributes: dict[str, str] = {}
        if registry is not None:
            defs = list(registry.pack.common_attributes)
            for t in registry.pack.element_types:
                defs.extend(t.attributes)
            for a in defs:
                for word in (a.name, a.label):
                    if word:
                        self._attributes.setdefault(norm_header(word), a.name)

    # ------------------------------------------------------------ headings
    def type_for_heading(self, heading: str) -> str:
        """The element type a table under this heading holds, or empty."""
        if self.registry is None or not heading:
            return ""
        label = self._sections.get(norm_heading(heading)) or _NUMBERING.sub("", heading).strip()
        t = self.registry.resolve_type(label)
        return t.id if t is not None else ""

    # ------------------------------------------------------------- columns
    def element_column(self, header: str) -> str:
        """The field a column of an element table fills — `name`, `description`, … — or
        `attr:<name>` for an attribute, or empty when it fills nothing."""
        key = norm_header(header)
        declared = self._columns.get(key)
        if declared:
            key = norm_header(declared)
        if key in ELEMENT_FIELDS:
            return ELEMENT_FIELDS[key]
        if key in self._attributes:
            return "attr:" + self._attributes[key]
        return ""

    def relationship_column(self, header: str) -> str:
        key = norm_header(header)
        declared = self._columns.get(key)
        if declared:
            key = norm_header(declared)
        return RELATIONSHIP_FIELDS.get(key, "")

    # --------------------------------------------------------------- shape
    def table_kind(self, table: dict[str, Any]) -> str:
        """`elements`, `relationships`, `untyped` (rows with names and nothing to type them by),
        `front` (the two-column header table) or empty."""
        rel = {self.relationship_column(h) for h in table["headers"]}
        if {"source", "relationship", "target"} <= rel:
            return "relationships"
        el = {self.element_column(h) for h in table["headers"]}
        if "name" in el:
            return "elements" if ("type" in el or self.type_for_heading(table["heading"])) else "untyped"
        if len(table["headers"]) == 2:
            return "front"
        return ""

    def summary(self) -> str:
        """The reading in words, for a hosted reader's prompt: what the template names differently."""
        lines = []
        if self.declaration.name:
            lines.append(f"The page follows the template {self.declaration.name!r}.")
        if self.declaration.sections:
            lines.append(
                "Its sections hold these element types: "
                + "; ".join(f"{k!r} → {v}" for k, v in self.declaration.sections.items())
                + "."
            )
        if self.declaration.columns:
            lines.append(
                "Its columns fill: "
                + "; ".join(f"{k!r} → {v}" for k, v in self.declaration.columns.items())
                + "."
            )
        lines.append(
            "Elsewhere a table under a heading that names an element type holds that type, and a column named after an attribute fills it."
        )
        return " ".join(lines)


def check(document: str, registry: Registry) -> list[str]:
    """What the application cannot place in a template: a declared type the metamodel lacks, an
    element table whose type it cannot tell, a column that fills nothing, a template typed in
    another metamodel. Nothing here refuses the template; it says what will be ignored."""
    decl, body = split_front_matter(document)
    reading = Reading(registry, decl)
    out: list[str] = []
    if decl is None:
        out.append(
            "No front matter names this template: add `proposal_template:` with a `name` and the `metamodel` it is typed in."
        )
    elif decl.metamodel and decl.metamodel != registry.pack.id:
        out.append(
            f"It is typed in metamodel {decl.metamodel!r}, and this organisation applies {registry.pack.name!r} ({registry.pack.id}): types it names may not exist here."
        )
    for heading, label in (decl.sections if decl else {}).items():
        if registry.resolve_type(label) is None:
            out.append(f"Section {heading!r} is declared as {label!r}, which the metamodel does not have.")
    for t in markdown_tables(body):
        kind = reading.table_kind(t)
        if kind == "elements":
            unplaced = [h for h in t["headers"] if h and not reading.element_column(h)]
            if unplaced:
                out.append(
                    f"Under {t['heading']!r}, column(s) {', '.join(repr(h) for h in unplaced)} fill no field or attribute and are ignored."
                )
        elif kind == "relationships":
            unplaced = [h for h in t["headers"] if h and not reading.relationship_column(h)]
            if unplaced:
                out.append(
                    f"In the relationships table, column(s) {', '.join(repr(h) for h in unplaced)} are ignored."
                )
        elif kind == "untyped":
            out.append(
                f"The table under {t['heading']!r} has no Type column and its heading names no element type, so its rows cannot be typed."
            )
    return out


# ------------------------------------------------------------------- starters


@dataclass(frozen=True)
class StarterTemplate:
    """A template the repository ships beside the pack it is typed in."""

    name: str
    pack_id: str
    description: str
    path: Path

    @property
    def document(self) -> str:
        return self.path.read_text(encoding="utf-8")


def starter_templates(directory: Path | str = STARTER_DIR) -> list[StarterTemplate]:
    """Every template shipped under `directory`, by name. Never raises: a directory that is
    absent or a file that is not a template gives a shorter list and a line in the log."""
    out: list[StarterTemplate] = []
    try:
        candidates = sorted(Path(directory).glob(f"*/{TEMPLATE_FILE}"))
    except OSError as exc:
        log.info("no starter templates under %s: %s", directory, exc)
        return out
    for path in candidates:
        try:
            decl, _ = split_front_matter(path.read_text(encoding="utf-8"))
        except OSError as exc:
            log.warning("%s could not be read as a starter template: %s", path, exc)
            continue
        if decl is None or not decl.name:
            log.warning("%s names no template in its front matter; not offered", path)
            continue
        out.append(StarterTemplate(decl.name, decl.metamodel, decl.description, path))
    return sorted(out, key=lambda s: s.name.lower())


# -------------------------------------------------------------------- service


class TemplateService:
    """The organisation's proposal templates: kept, listed, checked, and started from a starter."""

    def __init__(self, backend: DatabaseBackend, registry: Registry, starter_dir: Path | str = STARTER_DIR):
        self.backend, self.registry = backend, registry
        self.starter_dir = starter_dir

    def list(self) -> list[ProposalTemplate]:
        return self.backend.list_proposal_templates()

    def get(self, template_id: str) -> ProposalTemplate:
        t = self.backend.get_proposal_template(template_id)
        if t is None:
            raise NotFoundError(template_id, "proposal template")
        return t

    def find(self, name_or_id: str) -> ProposalTemplate | None:
        """By identifier, then by name, ignoring case."""
        key = (name_or_id or "").strip()
        if not key:
            return None
        found = self.backend.get_proposal_template(key)
        if found is not None:
            return found
        return next((t for t in self.list() if t.name.lower() == key.lower()), None)

    def save(self, document: str, actor: str, template_id: str | None = None) -> ProposalTemplate:
        """Keep a template for the organisation. It names itself in its front matter; a template
        of the same name is replaced rather than kept twice."""
        require("manage_templates", what="keep a proposal template")
        decl, _ = split_front_matter(document)
        if decl is None or not decl.name:
            raise ValidationError(
                [
                    Issue(
                        "error",
                        "template_name",
                        "a template names itself in its front matter: `proposal_template:` with a `name:`",
                    )
                ]
            )
        held = self.backend.get_proposal_template(template_id) if template_id else self.find(decl.name)
        return self.backend.save_proposal_template(
            ProposalTemplate(
                template_id=held.template_id if held else "",
                name=decl.name,
                document=document,
                pack_id=decl.metamodel or self.registry.pack.id,
                description=decl.description,
            ),
            actor,
        )

    def delete(self, template_id: str, actor: str) -> None:
        require("manage_templates", what="delete a proposal template")
        self.backend.delete_proposal_template(self.get(template_id).template_id, actor)

    def starters(self) -> list[StarterTemplate]:
        return starter_templates(self.starter_dir)

    def add_starter(self, name: str, actor: str) -> ProposalTemplate:
        """Keep a copy of a shipped template as the organisation's own, to change as it likes."""
        starter = next((s for s in self.starters() if s.name.lower() == (name or "").strip().lower()), None)
        if starter is None:
            raise NotFoundError(name, "starter template")
        return self.save(starter.document, actor)

    def offered(self) -> list[tuple[str, str, str]]:
        """What an architect may download: (key, label, document) for the organisation's own
        templates, then the starters typed in the metamodel it applies that it does not hold."""
        own = self.list()
        held = {t.name.lower() for t in own}
        out = [(t.template_id, t.name, t.document) for t in own]
        for s in self.starters():
            if s.name.lower() in held or (s.pack_id and s.pack_id != self.registry.pack.id):
                continue
            out.append((f"starter:{s.name}", f"{s.name} (starter)", s.document))
        return out

    def document(self, key: str) -> tuple[str, str]:
        """(name, document) of an offered template, by the key `offered` gave it."""
        if key.startswith("starter:"):
            name = key.split(":", 1)[1]
            starter = next((s for s in self.starters() if s.name == name), None)
            if starter is None:
                raise NotFoundError(name, "starter template")
            return starter.name, starter.document
        t = self.get(key)
        return t.name, t.document

    def check(self, document: str) -> list[str]:
        return check(document, self.registry)

    def reading(self, key: str | None = None, document: str | None = None) -> tuple[Reading, str, str]:
        """How a page is read: with the declaration in its own front matter, which travels with
        it; else with the template `key` names (a page exported from a wiki keeps no front
        matter); else with the metamodel's own names alone.

        Returns the reading, the template's identifier when the organisation keeps it, and its
        name.
        """
        decl, _ = split_front_matter(document or "")
        if decl is not None and decl.name:
            held = self.find(decl.name)
            return Reading(self.registry, decl), (held.template_id if held else ""), decl.name
        if key:
            try:
                name, text = self.document(key)
            except NotFoundError:
                # deleted since the page offered it: read with the metamodel's names instead
                log.info("template %s is gone; the page is read without it", key)
                return Reading(self.registry, None), "", ""
            decl, _ = split_front_matter(text)
            decl = decl or Declaration()
            decl.name = decl.name or name
            return Reading(self.registry, decl), ("" if key.startswith("starter:") else key), decl.name
        return Reading(self.registry, decl), "", ""
