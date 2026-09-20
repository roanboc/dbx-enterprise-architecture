"""An import mapping: how a source's files and columns land on the CSV contract.

Without a mapping the importer expects the contract as-is (see connectors/README.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

STATE_COLUMNS = ("current_state", "target_state", "target_work_package", "target_note")
CORE_ELEMENT_COLUMNS = (
    "id",
    "type",
    "name",
    "key",
    "description",
    "status",
    "lifecycle_status",
    "links",
    "source_ref",
    "origin",
    "source_system",
    *STATE_COLUMNS,
)
CORE_RELATIONSHIP_COLUMNS = (
    "src_id",
    "rel_type",
    "dst_id",
    "qualifier",
    "status",
    "source_ref",
    # A relationship's identity is derived from the source system that declared it, so a file
    # that carries it re-imports onto the same edge instead of creating a second one. That is
    # what makes an export of this repository's own content a round trip.
    "source_system",
    *STATE_COLUMNS,
)
CORE_LINK_COLUMNS = ("element_id", "url", "label")

# How a source's lifecycle text maps onto the current state when the mapping says nothing:
# the first keyword found in the lowercased text wins, in this order.
DEFAULT_LIFECYCLE_KEYWORDS: list[tuple[str, str]] = [
    ("retired", "retired"),
    ("decommissioned", "retired"),
    ("sunset", "retired"),
    ("end of life", "retired"),
    ("archived", "retired"),
    ("in implementation", "in_implementation"),
    ("implementing", "in_implementation"),
    ("in development", "in_implementation"),
    ("build", "in_implementation"),
    ("pilot", "in_implementation"),
    ("planned", "planned"),
    ("approved for build", "planned"),
    ("roadmap", "planned"),
    ("proposed", "proposed"),
    ("candidate", "proposed"),
    ("idea", "proposed"),
    ("concept", "proposed"),
    ("draft", "proposed"),
    ("non-existent", "non_existent"),
    ("does not exist", "non_existent"),
    ("live", "live"),
    ("production", "live"),
    ("operational", "live"),
    ("in use", "live"),
    ("active", "live"),
    ("current", "live"),
]


def derive_current_state(
    lifecycle_text: str, table: dict[str, str] | None = None, default: str = "live"
) -> str:
    """The current state a lifecycle text implies: an exact entry of the mapping's table first, then keywords."""
    text = (lifecycle_text or "").strip()
    if not text:
        return default
    low = text.lower()
    for k, v in (table or {}).items():
        if k.strip().lower() == low:
            return v
    for keyword, state in DEFAULT_LIFECYCLE_KEYWORDS:
        if keyword in low:
            return state
    return default


@dataclass
class Mapping:
    source_system: str = ""
    element_files: list[str] = field(default_factory=lambda: ["*element*.csv"])
    relationship_files: list[str] = field(default_factory=lambda: ["*relationship*.csv"])
    link_files: list[str] = field(default_factory=lambda: ["*link*.csv"])
    element_columns: dict[str, str] = field(default_factory=dict)
    relationship_columns: dict[str, str] = field(default_factory=dict)
    link_columns: dict[str, str] = field(default_factory=dict)
    type_names: dict[str, str] = field(default_factory=dict)
    rel_names: dict[str, str] = field(default_factory=dict)
    type_from_filename: bool = False
    element_defaults: dict[str, Any] = field(default_factory=dict)
    relationship_defaults: dict[str, Any] = field(default_factory=dict)
    ignore_columns: list[str] = field(default_factory=list)
    lifecycle_states: dict[str, str] = field(default_factory=dict)  # lifecycle text -> current_state
    encoding: str = "utf-8-sig"
    #: The field separator the source writes. A spreadsheet saved as CSV uses the list
    #: separator of the machine that saved it, which is a semicolon across much of Europe.
    delimiter: str = ","

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Mapping:
        files = d.get("files") or {}
        el = d.get("elements") or {}
        rel = d.get("relationships") or {}
        ln = d.get("links") or {}
        return cls(
            source_system=d.get("source_system", ""),
            element_files=list(files.get("elements") or el.get("files") or ["*element*.csv"]),
            relationship_files=list(files.get("relationships") or rel.get("files") or ["*relationship*.csv"]),
            link_files=list(files.get("links") or ln.get("files") or ["*link*.csv"]),
            element_columns=dict(el.get("columns") or {}),
            relationship_columns=dict(rel.get("columns") or {}),
            link_columns=dict(ln.get("columns") or {}),
            type_names=dict(el.get("type_names") or {}),
            rel_names=dict(rel.get("rel_names") or {}),
            type_from_filename=bool(el.get("type_from_filename", False)),
            element_defaults=dict(el.get("defaults") or {}),
            relationship_defaults=dict(rel.get("defaults") or {}),
            ignore_columns=list(el.get("ignore_columns") or []),
            lifecycle_states={str(k): str(v) for k, v in (el.get("lifecycle_states") or {}).items()},
            encoding=d.get("encoding", "utf-8-sig"),
            delimiter=str(d.get("delimiter") or ","),
        )


def load_mapping(path: str | Path) -> Mapping:
    with open(path, encoding="utf-8") as fh:
        return Mapping.from_dict(yaml.safe_load(fh) or {})


def mapping_from_text(text: str) -> Mapping:
    """A mapping written as YAML rather than held in a file — what an upload arrives as.

    YAML parsing stays here rather than in the page, so the screen and the command line read a
    mapping by the same rules.
    """
    loaded = yaml.safe_load(text or "")
    if loaded is None:
        return Mapping()
    if not isinstance(loaded, dict):
        raise ValueError("a mapping must be a YAML mapping of keys to values, not a list or a scalar")
    return Mapping.from_dict(loaded)
