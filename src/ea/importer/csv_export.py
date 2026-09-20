"""CSV extraction: the store's content written back out in the contract it is read in.

The files this writes are the files `csv_import` reads, so an export edited in a spreadsheet
and dropped back on the Import page lands on the same elements and the same edges rather than
beside them. That is the whole point of it: the cheapest way to correct a thousand rows is to
export them, fix the column, and import the file again.

Elements are written as **one wide file**: the contract's core columns, then a column for every
attribute any exported element carries. A row leaves the cells that do not apply to its type
blank, which is what a spreadsheet user expects and what the importer already reads (`anything
else is an attribute`).

Nothing here holds the model in memory. Both passes page with `capacity.pages()` and write each
page out before reading the next (decision 0019).
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any, TextIO

from ea import capacity
from ea.backend.base import DatabaseBackend
from ea.importer.mapping import CORE_LINK_COLUMNS, OPERATIONS
from ea.metamodel.registry import Registry
from ea.models import CURRENT_STATES, ELEMENT_STATUSES, TARGET_STATES, Element, Relationship

#: The core of an exported elements file, in the order connectors/README.md documents them.
#: `type` is written as the pack's type id, which `resolve_type` reads back exactly.
EXPORT_ELEMENT_COLUMNS = (
    "id",
    "type",
    "name",
    "key",
    "description",
    "status",
    "lifecycle_status",
    "links",
    "current_state",
    "target_state",
    "target_work_package",
    "target_note",
    "source_system",
    "source_ref",
    "origin",
)

#: What a relationships file carries. `source_system` is here because a relationship's identity
#: is derived from it: without it a re-import would duplicate every edge rather than update it.
EXPORT_RELATIONSHIP_COLUMNS = (
    "src_id",
    "rel_type",
    "dst_id",
    "qualifier",
    "status",
    "current_state",
    "target_state",
    "target_work_package",
    "target_note",
    "source_system",
    "source_ref",
)

#: The reference file written beside the three content files. It describes what they may
#: carry — the columns an adopter builds a feed from — and is not itself importable.
SCHEMA_FILE = "schema.csv"

#: What a common attribute's parent is: not one type, but all of them.
EVERY_ELEMENT_TYPE = "(every element type)"

FILES = ("elements.csv", "relationships.csv", "links.csv", SCHEMA_FILE)

SCHEMA_COLUMNS = (
    "file",
    "column",
    "applies_to",
    "kind",
    "data_type",
    "multiple",
    "required",
    "allowed_values",
    "group",
    "default",
    "unit",
    "description",
)

#: What the contract defines whatever pack is applied, with the meanings connectors/README.md
#: gives, so the file and the document cannot drift without one of them being edited.
CONTRACT_COLUMNS: tuple[tuple[str, str, str, str], ...] = (
    ("elements.csv", "id", "string", "Identifier in the source; becomes the element id"),
    ("elements.csv", "type", "string", "Element type: the pack type id, its name or its plural"),
    ("elements.csv", "name", "string", "Display name (required)"),
    ("elements.csv", "key", "string", "The human key the source system knows the row by"),
    ("elements.csv", "description", "markdown", "Markdown; may hold fenced diagrams"),
    ("elements.csv", "status", "enum", "Defaults to approved"),
    ("elements.csv", "lifecycle_status", "string", "Free text from the source (Live, Planned)"),
    ("elements.csv", "links", "list", "URLs separated by |"),
    ("elements.csv", "current_state", "enum", "Left blank, derived from lifecycle_status"),
    ("elements.csv", "target_state", "enum", "What the organisation intends"),
    ("elements.csv", "target_work_package", "string", "Id of the work package carrying the change"),
    ("elements.csv", "target_note", "string", "Why, and into what for merge"),
    ("elements.csv", "source_system", "string", "Which source declared the row; overrides --source"),
    ("elements.csv", "source_ref", "string", "The source's own reference, kept unprefixed"),
    ("elements.csv", "origin", "string", "Provenance override"),
    ("elements.csv", "operation", "enum", "upsert (default) loads the row; delete retires what it names"),
    ("relationships.csv", "src_id", "string", "Element id, or key when the mapping merges on the key"),
    ("relationships.csv", "rel_type", "string", "Relationship type id, or its name as the pack writes it"),
    ("relationships.csv", "dst_id", "string", "Element id, or key when the mapping merges on the key"),
    ("relationships.csv", "qualifier", "string", "Role qualifier where the type declares one"),
    ("relationships.csv", "status", "enum", "Defaults to approved"),
    ("relationships.csv", "current_state", "enum", "As on an element"),
    ("relationships.csv", "target_state", "enum", "As on an element"),
    ("relationships.csv", "target_work_package", "string", "As on an element"),
    ("relationships.csv", "target_note", "string", "As on an element"),
    ("relationships.csv", "source_system", "string", "A relationship's identity is derived from it"),
    ("relationships.csv", "source_ref", "string", "The source's own reference"),
    ("relationships.csv", "operation", "enum", "upsert (default) loads the row; delete retires the edge"),
    ("links.csv", "element_id", "string", "The element the link belongs to"),
    ("links.csv", "url", "string", "http, https or mailto"),
    ("links.csv", "label", "string", "What the link is called"),
)

#: The vocabularies the engine fixes, named per column rather than repeated in prose.
CONTRACT_VOCABULARY = {
    "operation": OPERATIONS,
    "status": ELEMENT_STATUSES,
    "current_state": CURRENT_STATES,
    "target_state": TARGET_STATES,
}


def cell(value: Any) -> str:
    """One attribute value as a cell the importer reads back as the same value.

    A list is joined with `|`, which is what `split_multi` splits on; a boolean is written the
    way Python writes it, which `coerce_values` reads back as a boolean; None is an empty cell.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def _elements(backend: DatabaseBackend):
    return capacity.pages(lambda limit, offset: backend.find_elements(limit=limit, offset=offset))


def attribute_columns(backend: DatabaseBackend, registry: Registry) -> list[str]:
    """Every attribute column the elements file needs, pack order first, then anything else.

    This is a pass of its own over the elements, because the header has to be written before the
    first row and an element may carry an attribute the pack never declared — the importer keeps
    those, so an export that dropped them would not be a round trip. Only the keys are kept, not
    the elements, so the pass costs a set of attribute names rather than the model.
    """
    declared: list[str] = []
    for t in registry.pack.element_types:
        for a in registry.attributes_for(t.id):
            if a.name not in declared:
                declared.append(a.name)
    seen: set[str] = set()
    for page in _elements(backend):
        for e in page:
            seen.update(e.attrs or {})
    extra = sorted(seen - set(declared))
    return [c for c in declared if c in seen] + extra


def write_elements(backend: DatabaseBackend, registry: Registry, out: TextIO) -> int:
    """The elements of the current organisation and branch, as one wide file. Returns the count."""
    attrs = attribute_columns(backend, registry)
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([*EXPORT_ELEMENT_COLUMNS, *attrs])
    written = 0
    for page in _elements(backend):
        for e in page:
            writer.writerow([*_element_row(e, backend), *(cell((e.attrs or {}).get(a)) for a in attrs)])
            written += 1
    return written


def _element_row(e: Element, backend: DatabaseBackend) -> list[str]:
    return [
        e.element_id,
        e.type_id,
        e.name,
        e.key or "",
        e.description_md or "",
        e.status or "",
        e.lifecycle_status or "",
        "|".join(ln.url for ln in backend.get_links(e.element_id)),
        e.current_state or "",
        e.target_state or "",
        e.target_work_package or "",
        e.target_note or "",
        e.source_system or "",
        e.source_ref or "",
        e.origin or "",
    ]


def write_relationships(backend: DatabaseBackend, out: TextIO) -> int:
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_RELATIONSHIP_COLUMNS)
    written = 0
    pages = capacity.pages(lambda limit, offset: backend.find_relationships(limit=limit, offset=offset))
    for page in pages:
        for r in page:
            writer.writerow(_relationship_row(r))
            written += 1
    return written


def _relationship_row(r: Relationship) -> list[str]:
    return [
        r.src_id,
        r.rel_type_id,
        r.dst_id,
        r.qualifier or "",
        r.status or "",
        r.current_state or "",
        r.target_state or "",
        r.target_work_package or "",
        r.target_note or "",
        r.source_system or "",
        r.source_ref or "",
    ]


def write_links(backend: DatabaseBackend, out: TextIO) -> int:
    """The links file, for the elements that carry one.

    `linked_element_ids()` names only the elements that have a link and there is no batch read
    for links, so this is one read per such element. At the assessed capacity that is bounded by
    how many elements carry documentation rather than by the model, and the elements file already
    carries the same URLs in its `links` column — this file exists so a label survives the trip.
    """
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CORE_LINK_COLUMNS)
    written = 0
    for element_id in backend.linked_element_ids():
        for ln in backend.get_links(element_id):
            writer.writerow([element_id, ln.url, ln.label or ""])
            written += 1
    return written


def write_schema(registry: Registry, out: TextIO) -> int:
    """What the three content files may carry, one row per column.

    This is the reference an adopter builds a feed from: every column, the type or file that
    is its parent, the data type the value is read as, whether it takes many values, and what
    the pack says the attribute means. It is written from the version this organisation
    applies, so it describes the columns *this* import will accept rather than a general idea
    of them — and it is a reference, not an importable file.
    """
    out_writer = csv.writer(out, lineterminator="\n")
    out_writer.writerow(SCHEMA_COLUMNS)
    written = 0
    for file, column, data_type, description in CONTRACT_COLUMNS:
        allowed = "|".join(CONTRACT_VOCABULARY.get(column, ()))
        out_writer.writerow([file, column, file, "core", data_type, "", "", allowed, "", "", "", description])
        written += 1
    # A common attribute belongs to every element type, so it is said once. Repeating it under
    # each type would name one of them as its parent, which is not true of it.
    common = {a.name for a in registry.pack.common_attributes}
    for a in registry.pack.common_attributes:
        out_writer.writerow(_attribute_row("elements.csv", EVERY_ELEMENT_TYPE, a, registry))
        written += 1
    for t in registry.pack.element_types:
        for a in registry.attributes_for(t.id):
            if a.name in common:
                continue
            out_writer.writerow(_attribute_row("elements.csv", t.id, a, registry))
            written += 1
    for r in registry.pack.relationship_types:
        for a in registry.attributes_for_relationship(r.id):
            out_writer.writerow(_attribute_row("relationships.csv", r.id, a, registry))
            written += 1
    return written


def _attribute_row(file: str, parent: str, a: Any, registry: Registry) -> list[str]:
    return [
        file,
        a.name,
        parent,
        "attribute",
        a.type or "string",
        "yes" if a.multiple else "",
        "yes" if a.required else "",
        "|".join(a.enum) if a.enum else "",
        registry.group_name(a.group) if a.group else "",
        cell(a.default),
        a.unit or "",
        a.description or a.help or a.label or "",
    ]


def export_directory(backend: DatabaseBackend, registry: Registry, directory: str | Path) -> dict[str, int]:
    """Write the three contract files into a directory. Returns what each one holds."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with open(d / "elements.csv", "w", encoding="utf-8", newline="") as fh:
        counts["elements"] = write_elements(backend, registry, fh)
    with open(d / "relationships.csv", "w", encoding="utf-8", newline="") as fh:
        counts["relationships"] = write_relationships(backend, fh)
    with open(d / "links.csv", "w", encoding="utf-8", newline="") as fh:
        counts["links"] = write_links(backend, fh)
    with open(d / SCHEMA_FILE, "w", encoding="utf-8", newline="") as fh:
        counts["schema"] = write_schema(registry, fh)
    return counts


def export_archive(backend: DatabaseBackend, registry: Registry) -> bytes:
    """The same three files as a ZIP, for the download on the Import page."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, write in (
            ("elements.csv", lambda fh: write_elements(backend, registry, fh)),
            ("relationships.csv", lambda fh: write_relationships(backend, fh)),
            ("links.csv", lambda fh: write_links(backend, fh)),
            (SCHEMA_FILE, lambda fh: write_schema(registry, fh)),
        ):
            buf = io.StringIO()
            write(buf)
            archive.writestr(name, buf.getvalue())
    return out.getvalue()
