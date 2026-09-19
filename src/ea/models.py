"""Domain model: metamodel definitions, graph content and reports.

Knows nothing about SQL, YAML or Dash. Every other layer imports from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

ANY = "ANY"
IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
# A link is published to every reader of the element that carries it, so what may be stored
# is named rather than guessed at. A `javascript:` line waiting for a click, a `data:`
# document or a `file:` path off somebody else's disk is not a link to a source.
LINK_SCHEMES = ("http://", "https://", "mailto:")

ELEMENT_STATUSES = ("draft", "approved", "retired")
ATTRIBUTE_TYPES = ("string", "text", "integer", "number", "boolean", "date", "url", "json")
# A stored definition of a pack goes through three states: a draft is edited in place, a
# published version is frozen (the content validated against it stays validated), a retired
# one is kept so a version an organisation once applied can still be read.
PACK_STATUSES = ("draft", "published", "retired")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
# What a list-valued attribute is split on when it arrives as one string (an import, a grid
# cell): the same separators the links column takes, never the comma a value may hold.
MULTI_VALUE_SPLIT = re.compile(r"\s*[|;]\s*")


def slugify(text: str) -> str:
    """A pack-style identifier from a human label: 'Logical Data Component' -> 'logical_data_component'."""
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    if not s:
        raise ValueError(f"cannot derive an identifier from {text!r}")
    if s[0].isdigit():
        s = "x" + s
    return s[:80]


def validate_identifier(value: str, what: str = "identifier") -> str:
    if not IDENT_RE.match(value or ""):
        raise ValueError(f"{what} {value!r} must match {IDENT_RE.pattern}")
    return value


def validate_version(value: str, what: str = "version") -> str:
    """A version names one stored definition of a pack: a date, a number, a word — short and safe in a file name."""
    if not VERSION_RE.match(value or ""):
        raise ValueError(f"{what} {value!r} must be letters, digits, '.', '_' or '-', up to 40 characters")
    return value


def split_multi(value: Any) -> list[Any]:
    """A list-valued attribute from whatever it arrived as: a list stays, a string is split on | or ;."""
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v not in (None, "")]
    return [v for v in MULTI_VALUE_SPLIT.split(str(value)) if v]


# ----------------------------------------------------------------- metamodel


@dataclass
class AttributeDef:
    """One attribute a framework declares, on an element type, on every element type (common),
    or on a relationship type. What the engine reads is the type and the rules; what it does
    not know goes into `properties` and comes back out of the pack unchanged."""

    name: str
    label: str = ""
    type: str = "string"
    required: bool = False
    enum: list[str] | None = None
    description: str = ""
    sensitivity: str = ""
    type_id: str | None = None  # the element type it belongs to; None = common to every element type
    rel_type_id: str | None = None  # the relationship type it belongs to, for a relationship attribute
    default: Any = None  # written onto a new element that does not set the attribute
    multiple: bool = False  # a list of values (each one of `enum` when an enum is declared)
    unit: str = ""  # shown after the label: "Cost (AUD)"
    pattern: str = ""  # a regular expression a string value must match in full
    min: float | str | None = None  # a number, or an ISO date, the value may not go under
    max: float | str | None = None
    group: str = ""  # the section of the form the attribute is shown in
    help: str = ""  # a sentence shown beside the control
    properties: dict[str, Any] = field(default_factory=dict)  # anything the framework adds; kept, never read

    def __post_init__(self) -> None:
        validate_identifier(self.name, "attribute name")
        if self.type not in ATTRIBUTE_TYPES:
            raise ValueError(f"attribute {self.name}: unknown type {self.type!r}")
        self.label = self.label or self.name.replace("_", " ").title()
        if self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(
                    f"attribute {self.name}: pattern {self.pattern!r} is not a regular expression ({exc})"
                ) from None
        if self.min is not None and self.max is not None and self.type in ("integer", "number"):
            if float(self.min) > float(self.max):
                raise ValueError(f"attribute {self.name}: min {self.min} is above max {self.max}")

    @property
    def title(self) -> str:
        """The label with its unit, the way a form heads the control."""
        return f"{self.label} ({self.unit})" if self.unit else self.label


@dataclass
class Domain:
    id: str
    name: str
    description: str = ""
    notation: dict[str, str] = field(default_factory=dict)  # default drawing convention for its types
    sort_order: int = 0
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.id, "domain id")


@dataclass
class ElementType:
    id: str
    name: str
    plural: str = ""
    supertype: str | None = None
    active: bool = True
    deactivation_reason: str = ""
    domain: str = ""
    provenance: str = ""
    prefix: str = ""
    description: str = ""
    examples: list[str] = field(default_factory=list)
    source_of_record: str = ""
    type_owner: str = ""
    instance_owner: str = ""
    attributes: list[AttributeDef] = field(default_factory=list)
    notation: dict[str, str] = field(default_factory=dict)  # glyph, stereotype, archimate, layer, shape
    sort_order: int = 0
    abstract: bool = (
        False  # groups its sub-types and carries their attributes and relationships; no element is one
    )
    properties: dict[str, Any] = field(default_factory=dict)  # anything the framework adds; kept, never read

    def __post_init__(self) -> None:
        validate_identifier(self.id, "element type id")
        self.plural = self.plural or self.name + "s"
        for a in self.attributes:
            a.type_id = self.id


@dataclass
class RelationshipType:
    id: str
    name: str
    inverse: str = ""
    source: str = ANY
    target: str = ANY
    provenance: str = ""
    qualifiers: list[str] = field(default_factory=list)
    diagrams: list[str] = field(default_factory=list)
    description: str = ""
    src_max: int | None = None
    dst_max: int | None = None
    sort_order: int = 0
    attributes: list[AttributeDef] = field(default_factory=list)  # what a relationship of this type may carry
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.id, "relationship type id")
        self.inverse = self.inverse or f"is {self.name} by"
        for a in self.attributes:
            a.rel_type_id = self.id
            a.type_id = None


@dataclass
class Pack:
    """One version of a framework: the whole definition, and how far it has come.

    A pack id names the framework; a version names one stored definition of it, whether it
    succeeds the one before or is a variant tried beside it. `derived_from` names the version
    a draft was copied from, as `<pack id>@<version>`.
    """

    id: str
    name: str
    version: str = "1"
    description: str = ""
    source: str = ""
    provenance_values: list[str] = field(default_factory=list)
    domains: list[Domain] = field(default_factory=list)
    common_attributes: list[AttributeDef] = field(default_factory=list)
    element_types: list[ElementType] = field(default_factory=list)
    relationship_types: list[RelationshipType] = field(default_factory=list)
    status: str = "draft"
    derived_from: str = ""
    notes: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.id, "pack id")
        self.version = validate_version(str(self.version or "1"), f"pack {self.id}: version")
        if self.status not in PACK_STATUSES:
            raise ValueError(f"pack {self.id}: status must be one of {PACK_STATUSES}")

    @property
    def ref(self) -> str:
        """`<pack id>@<version>`: how a version is named wherever one is picked."""
        return f"{self.id}@{self.version}"


def split_pack_ref(ref: str) -> tuple[str, str]:
    """`higher_education@2026-08-11` -> (pack id, version); a bare pack id has no version."""
    pack_id, _, version = (ref or "").strip().partition("@")
    return pack_id.strip(), version.strip()


@dataclass
class PackVersion:
    """A stored version of a pack, as the store lists it: the header, its lifecycle, and who applies it."""

    pack_id: str
    version: str
    name: str = ""
    status: str = "draft"
    derived_from: str = ""
    notes: str = ""
    loaded_at: datetime | None = None
    created_by: str = ""
    created_at: datetime | None = None
    published_by: str = ""
    published_at: datetime | None = None
    applied_by: list[str] = field(default_factory=list)  # the organisations that apply it

    @property
    def ref(self) -> str:
        return f"{self.pack_id}@{self.version}"


@dataclass
class Organisation:
    """The enterprise whose architecture a body of content describes.

    Every element, relationship, link, branch, review and proposal belongs to one; each applies
    one version of one pack; one is the default the application opens. Another organisation
    is where a metamodel version is tried on a copy of the content before it is applied to
    the default (decision 0014).
    """

    org_id: str
    name: str
    description: str = ""
    pack_id: str = ""
    pack_version: str = ""
    is_default: bool = False
    copied_from: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    elements: int = 0  # filled by list_organisations
    relationships: int = 0
    branches: int = 0

    @property
    def pack_ref(self) -> str:
        return f"{self.pack_id}@{self.pack_version}" if self.pack_id else ""


# ------------------------------------------------------------------- content


@dataclass
class Link:
    element_id: str
    url: str
    label: str = ""
    link_id: str = ""
    sort_order: int = 0


# What is true of an artefact today, and what the organisation intends for it. Fixed and small
# on purpose: every framework needs them, and the views, the importer and the agent read them.
CURRENT_STATES = ["proposed", "planned", "in_implementation", "live", "retired", "non_existent"]
TARGET_STATES = ["undecided", "keep", "new", "change", "decommission", "merge"]


def _check_states(what: str, current_state: str, target_state: str) -> None:
    if current_state not in CURRENT_STATES:
        raise ValueError(f"{what}: current_state must be one of {CURRENT_STATES}")
    if target_state not in TARGET_STATES:
        raise ValueError(f"{what}: target_state must be one of {TARGET_STATES}")


@dataclass
class Element:
    element_id: str
    type_id: str
    name: str
    key: str = ""
    description_md: str = ""
    status: str = "draft"
    lifecycle_status: str = ""
    source_system: str = ""
    source_ref: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)
    origin: str = ""
    version: int = 1
    created_at: datetime | None = None
    created_by: str = ""
    updated_at: datetime | None = None
    updated_by: str = ""
    links: list[Link] = field(default_factory=list)
    current_state: str = "live"
    target_state: str = "undecided"
    target_work_package: str = ""
    target_note: str = ""

    def __post_init__(self) -> None:
        if self.status not in ELEMENT_STATUSES:
            raise ValueError(f"element {self.element_id}: status must be one of {ELEMENT_STATUSES}")
        self.current_state = self.current_state or "live"
        self.target_state = self.target_state or "undecided"
        _check_states(f"element {self.element_id}", self.current_state, self.target_state)


@dataclass
class Relationship:
    relationship_id: str
    rel_type_id: str
    src_id: str
    dst_id: str
    qualifier: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)
    status: str = "draft"
    origin: str = ""
    source_system: str = ""
    source_ref: str = ""
    version: int = 1
    created_at: datetime | None = None
    created_by: str = ""
    updated_at: datetime | None = None
    updated_by: str = ""
    current_state: str = "live"
    target_state: str = "undecided"
    target_work_package: str = ""
    target_note: str = ""

    def __post_init__(self) -> None:
        self.current_state = self.current_state or "live"
        self.target_state = self.target_state or "undecided"
        _check_states(f"relationship {self.relationship_id}", self.current_state, self.target_state)


BRANCH_STATUSES = ["open", "in_review", "approved", "merged", "abandoned"]
OPEN_STATUSES = ("open", "in_review", "approved")  # a branch that can still be merged or abandoned


@dataclass
class Branch:
    branch_id: str
    name: str
    description: str = ""
    work_package: str = ""
    status: str = "open"
    created_by: str = ""
    created_at: datetime | None = None
    closed_by: str = ""
    closed_at: datetime | None = None
    changes: int = 0  # rows on the overlay, filled by list_branches


@dataclass
class ChangeItem:
    """One row of a branch's change set against `main`."""

    kind: str  # element | relationship
    entity_id: str
    label: str
    change: str  # added | changed | deleted
    base_version: int
    main_version: int | None
    conflict: bool
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    fields_changed: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.entity_id}"


@dataclass
class ChangeSet:
    branch: Branch
    items: list[ChangeItem] = field(default_factory=list)

    @property
    def conflicts(self) -> list[ChangeItem]:
        return [i for i in self.items if i.conflict]

    def counts(self) -> dict[str, int]:
        out = {"added": 0, "changed": 0, "deleted": 0, "conflicts": 0}
        for i in self.items:
            out[i.change] += 1
            if i.conflict:
                out["conflicts"] += 1
        return out


@dataclass
class MergeResult:
    branch_id: str
    applied: list[str] = field(default_factory=list)  # item keys written to main
    dropped: list[str] = field(default_factory=list)  # conflicts resolved for main: removed from the branch
    remaining: int = 0  # rows still on the branch
    closed: bool = False


@dataclass
class Proposal:
    """What an architect handed in, what was derived from it, and where it went."""

    proposal_id: str
    branch_id: str
    title: str
    sources: list[dict[str, Any]] = field(default_factory=list)  # {kind: text|file|link, name, chars}
    result: dict[str, Any] = field(default_factory=dict)  # the change set as applied
    pushback: list[str] = field(default_factory=list)
    status: str = "applied"  # analysed | applied
    created_by: str = ""
    created_at: datetime | None = None


@dataclass
class Review:
    """One reviewer's decision on a branch, for the element types they cover."""

    review_id: str
    branch_id: str
    reviewer: str
    decision: str  # approve | send_back
    type_ids: list[str] = field(default_factory=list)
    comment: str = ""
    decided_at: datetime | None = None


ROLES = ("reader", "reviewer", "architect", "admin", "agent")


@dataclass
class User:
    username: str
    display_name: str = ""
    groups: list[str] = field(default_factory=list)
    role: str = "reader"


class Forbidden(Exception):
    """The role of the request may not do this."""


# ------------------------------------------------------------------- reports


@dataclass
class Issue:
    level: str  # error | warning | info
    code: str
    message: str
    row: int | None = None
    entity: str | None = None
    file: str | None = None

    def __str__(self) -> str:
        where = " ".join(
            p for p in (self.file, f"row {self.row}" if self.row is not None else "", self.entity or "") if p
        )
        return f"[{self.level}] {self.code}: {self.message}" + (f" ({where})" if where else "")


@dataclass
class ImportReport:
    source_system: str
    elements_read: int = 0
    relationships_read: int = 0
    links_read: int = 0
    elements_loaded: int = 0
    relationships_loaded: int = 0
    links_loaded: int = 0
    elements_skipped: int = 0
    relationships_skipped: int = 0
    issues: list[Issue] = field(default_factory=list)
    dry_run: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        if self.dry_run:
            # A run that was never going to write anything must not report itself in the
            # language of one that failed to: '0/47 loaded' reads as a shortfall.
            return (
                f"source={self.source_system} checked elements {self.elements_read}"
                f" ({self.elements_skipped} would be skipped), relationships {self.relationships_read}"
                f" ({self.relationships_skipped} would be skipped), links {self.links_read};"
                f" {len(self.errors)} errors, {len(self.warnings)} warnings"
            )
        return (
            f"source={self.source_system} elements {self.elements_loaded}/{self.elements_read} loaded"
            f" ({self.elements_skipped} skipped), relationships {self.relationships_loaded}/{self.relationships_read}"
            f" loaded ({self.relationships_skipped} skipped), links {self.links_loaded}/{self.links_read};"
            f" {len(self.errors)} errors, {len(self.warnings)} warnings"
        )


@dataclass
class CompatibilityReport:
    """What an organisation's content would say under a metamodel version: every element and
    relationship of its main validated against the version, before the version is applied."""

    org_id: str
    pack_id: str
    version: str
    elements: int = 0
    relationships: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def by_code(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.issues:
            out[i.code] = out.get(i.code, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    def summary(self) -> str:
        return (
            f"{self.pack_id}@{self.version} on {self.org_id}: {self.elements} elements and "
            f"{self.relationships} relationships checked; {len(self.errors)} errors, {len(self.warnings)} warnings"
        )


class ConflictError(Exception):
    """Optimistic-concurrency conflict: the row changed since it was read."""


class NotFoundError(Exception):
    """Nothing carries the identifier that was asked for.

    It reads as a sentence because it is shown to people: on the command line it is the
    last line of the failure, and in a bulk edit it is the reason beside the row that was
    refused. An identifier on its own answers nothing.
    """

    def __init__(self, identifier: str, kind: str = "element") -> None:
        super().__init__(f"no {kind} with id {identifier}")
        self.identifier = identifier
        self.kind = kind


class ValidationError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))
