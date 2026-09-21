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
    group: str = ""  # the id of the AttributeGroup the attribute is read and edited under
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
class AttributeGroup:
    """A section an element's attributes are read and edited in.

    The group was free text on the attribute, so a typo made a section of its own that
    nobody could see was a mistake. A framework declares its groups here instead; an
    attribute names one by its identifier, the element page reads them in this order, and
    the metamodel screen offers the list rather than a text box.
    """

    id: str
    name: str = ""
    description: str = ""
    sort_order: int = 0
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.id, "attribute group id")
        self.name = self.name or self.id.replace("_", " ").capitalize()


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
    attribute_groups: list[AttributeGroup] = field(default_factory=list)
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


#: How a list of elements may be ordered. `relevance` needs words to rank against and
#: falls back to `name` without them; the rest are columns the store sorts on.
SORT_ORDERS = ("relevance", "name", "type", "status", "updated", "created")


@dataclass
class AttributeFilter:
    """One attribute predicate: the attribute is present, and its value matches.

    `value` empty asks only that the attribute is set to something. Matching is a
    case-insensitive substring, which is what a reader typing into a box means; an
    attribute the pack declares as a list holds its values in one string, so a
    substring finds one of them.
    """

    name: str
    value: str = ""


@dataclass
class ElementFilter:
    """What narrows a list of elements. Every field is optional and they narrow together.

    One object rather than a widening parameter list, so the store, the services, the
    page, the command line and the address bar all name the same criteria, and a new
    criterion is added in one place. A list field matches any of its values; the fields
    match all together.
    """

    text: str = ""
    type_ids: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    current_states: list[str] = field(default_factory=list)
    target_states: list[str] = field(default_factory=list)
    work_packages: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    lifecycle_statuses: list[str] = field(default_factory=list)
    attributes: list[AttributeFilter] = field(default_factory=list)
    updated_since: datetime | None = None
    updated_before: datetime | None = None
    #: Only these elements, whatever else matches — how a drill-down from another page
    #: (the Health facets) narrows the list without the store learning that page's words.
    only_ids: list[str] | None = None
    sort: str = "relevance"
    descending: bool = False

    def __post_init__(self) -> None:
        if self.sort not in SORT_ORDERS:
            raise ValueError(f"sort must be one of {SORT_ORDERS}")
        self.text = (self.text or "").strip()

    @property
    def words(self) -> list[str]:
        """The search words, lowercased. Every one of them has to match somewhere."""
        return [w for w in re.split(r"\s+", self.text.lower()) if w]

    def narrows(self) -> bool:
        """Whether anything here narrows the list at all."""
        return bool(
            self.words
            or self.type_ids
            or self.statuses
            or self.current_states
            or self.target_states
            or self.work_packages
            or self.sources
            or self.lifecycle_statuses
            or self.attributes
            or self.updated_since
            or self.updated_before
            or self.only_ids is not None
        )

    def order(self) -> str:
        """The sort actually applied: relevance needs words to rank against."""
        return "name" if self.sort == "relevance" and not self.words else self.sort


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
    #: The row as `main` held it when the branch first touched it. `None` for a row the
    #: branch added, and for a row written before the base was kept.
    base: dict[str, Any] | None = None
    #: What each side changed since that base, and where the two overlap. Only the overlap
    #: is a conflict: two people editing different fields of one element have not disagreed.
    branch_fields: list[str] = field(default_factory=list)
    main_fields: list[str] = field(default_factory=list)
    overlapping: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.entity_id}"

    @property
    def stale(self) -> bool:
        """Main moved under this row, whether or not the two disagree about a field."""
        return bool(self.main_fields)

    def merged_row(self, take: dict[str, str] | None = None) -> dict[str, Any]:
        """What main should hold: main's current row with the branch's changes laid over it.

        The branch's fields win by default, which is what merging a branch means. `take`
        names the fields to decide differently — a field mapped to `"main"` keeps main's
        value — and only ever covers overlapping fields, because nothing else is in dispute.
        """
        out = dict(self.before or {})
        for f in self.branch_fields:
            if (take or {}).get(f) == "main" and f in (self.main_fields or []):
                continue
            out[f] = (self.after or {}).get(f)
        return out


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
    #: Items the merge would not write, and why — a relationship whose end is not on main
    #: and was not ticked with it, or a conflict nobody resolved. They stay on the branch.
    held_back: list[dict[str, str]] = field(default_factory=list)
    remaining: int = 0  # rows still on the branch
    closed: bool = False

    def reasons(self) -> str:
        """What was held back, as one line a person reads."""
        return "; ".join(f"{h['key']}: {h['reason']}" for h in self.held_back)


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


#: The most issues one import report keeps. Past it the report counts rather than lists:
#: a file with a wrong header produces one issue per row, and a hundred thousand of them
#: tell a reader nothing the first two thousand did not (decision 0019).
MAX_IMPORT_ISSUES = 2_000


@dataclass
class SourceFeed:
    """A configured source: which staging tables are its, how they are read, and when it runs.

    The schedule is kept **in the zone it is written in** rather than converted to UTC. A person
    who says a feed runs at half past two means half past two where they are, and a platform
    scheduler takes a timezone alongside its expression for the same reason. Storing the zone
    means nothing has to be converted to be shown correctly, and nothing drifts when a zone's
    offset changes.

    The application does not fire the schedule — what fires it is outside, as decision 0020 has
    it. The schedule is what a trigger honours and what the screen shows; `Run now` is what the
    application itself does.
    """

    feed_id: str = ""
    name: str = ""
    source_system: str = ""
    elements_table: str = ""
    relationships_table: str = ""
    links_table: str = ""
    #: The mapping, inline, so a feed is self-contained: its columns, identity rule, prefix and
    #: deletion mode travel with it rather than pointing at a file that may change underneath.
    mapping_yaml: str = ""
    #: Where the feed writes. Empty is `main`, which is a feed nobody reviews before it lands.
    target_branch: str = ""
    #: Whether the staging tables are emptied once loaded. False for a table something else
    #: maintains, such as one replicated from a catalogue.
    clear_after: bool = True
    enabled: bool = True
    #: A cron expression as whatever triggers this feed writes them, and the zone it is in.
    schedule: str = ""
    schedule_timezone: str = ""
    last_run_at: Any = None
    last_run_status: str = ""
    last_run_summary: str = ""
    created_at: Any = None
    created_by: str = ""
    updated_at: Any = None
    updated_by: str = ""

    @property
    def writes_to_main(self) -> bool:
        return not self.target_branch


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
    #: What the load did, not just how much of it: an architect about to press Load wants to
    #: know how many rows are new and how many overwrite something that is already there.
    elements_created: int = 0
    elements_updated: int = 0
    #: Rows identical to what the branch already held, so nothing was written for them. A feed
    #: that re-sends its whole source every night is almost all of this, and saying 'updated'
    #: would make a quiet night look like a busy one.
    elements_unchanged: int = 0
    #: Rows a source said are gone. Retired, not removed: the element, its relationships
    #: and its history stay, and loading the row again undoes it.
    elements_retired: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0
    relationships_unchanged: int = 0
    relationships_retired: int = 0
    issues: list[Issue] = field(default_factory=list)
    #: Every issue found, counted by code, whether or not it was kept in `issues`.
    counts: dict[str, int] = field(default_factory=dict)
    #: How many of them were errors and warnings. `ok` and `summary()` read these, not the
    #: kept list, so both stay true when the list is cut.
    error_count: int = 0
    warning_count: int = 0
    #: True when more issues were found than the report keeps.
    truncated: bool = False
    dry_run: bool = False

    def add_issue(self, issue: Issue) -> None:
        """Record an issue: always counted, kept while there is room to keep it."""
        self.counts[issue.code] = self.counts.get(issue.code, 0) + 1
        if issue.level == "error":
            self.error_count += 1
        elif issue.level == "warning":
            self.warning_count += 1
        if len(self.issues) < MAX_IMPORT_ISSUES:
            self.issues.append(issue)
        else:
            self.truncated = True

    @property
    def errors(self) -> list[Issue]:
        """The errors this report kept. `error_count` is how many there were."""
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        """The warnings this report kept. `warning_count` is how many there were."""
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.error_count

    def _tally(self) -> str:
        """The error and warning totals, saying so when the kept list is shorter than they are."""
        out = f"{self.error_count} errors, {self.warning_count} warnings"
        if self.truncated:
            out += f" (the first {len(self.issues)} listed)"
        return out

    def summary(self) -> str:
        if self.dry_run:
            # A run that was never going to write anything must not report itself in the
            # language of one that failed to: '0/47 loaded' reads as a shortfall.
            return (
                f"source={self.source_system} checked elements {self.elements_read}"
                f" ({self.elements_skipped} would be skipped), relationships {self.relationships_read}"
                f" ({self.relationships_skipped} would be skipped), links {self.links_read};"
                f" {self._tally()}"
            )
        return (
            f"source={self.source_system} elements {self.elements_loaded}/{self.elements_read} loaded"
            f" ({self.elements_created} new, {self.elements_updated} updated,"
            f" {self.elements_unchanged} unchanged, {self.elements_retired} retired,"
            f" {self.elements_skipped} skipped), relationships"
            f" {self.relationships_loaded}/{self.relationships_read} loaded"
            f" ({self.relationships_created} new, {self.relationships_updated} updated,"
            f" {self.relationships_unchanged} unchanged, {self.relationships_skipped} skipped), links {self.links_loaded}/{self.links_read};"
            f" {self._tally()}"
        )


#: How a run started. `upload` is somebody on the Import page, `command` is `ea import`, and
#: `feed` is a configured source read from the staging schema — by its schedule's trigger or by
#: `Run now`. The list is closed: a run whose origin nobody can name is a run nobody can trust.
RUN_TRIGGERS = ("upload", "command", "feed")

#: How a run ended. `ok` and `errors` are both loads that finished — the second one found errors
#: and wrote what it could. `failed` is a run that stopped: the store refused it, the branch was
#: frozen, the mapping would not read. The distinction matters because only `failed` means the
#: counts below are not the whole of what happened.
RUN_STATUSES = ("ok", "errors", "failed")

#: The most issues one *stored* run keeps. A report keeps `MAX_IMPORT_ISSUES` for the screen
#: that is about to show it; history keeps far fewer, because a run is kept forever and a
#: hundred nightly feeds each holding two thousand issues is a table nobody meant to grow.
#: `issue_counts` stays complete either way, so the totals are never the sample's.
MAX_RUN_ISSUES = 200


@dataclass
class ImportRun:
    """One execution of an import: what it read, where it wrote, what it did, and how it went.

    An `ImportReport` (`DOBJ3.3`) is what a run *said*, held for as long as the request that
    produced it. This is what a run *was*, and it outlives that request — which is the whole
    reason it exists: a feed that runs at a quarter past two has nobody watching the screen it
    would otherwise have reported to.

    It outlives its feed, too. `feed_name` is a copy of a name the feed owns, kept here on
    purpose: a feed deleted six months from now must not take its history with it, and a
    dangling `feed_id` would leave the rows it loaded unexplained.

    **Nothing here reverses a run.** Reversal needs the before-image of every row a run
    changed, which is a different and much larger thing to store, and it is not built (`GAP19`).
    What this holds is the account of what happened, not the means to undo it.
    """

    run_id: str = ""
    source_system: str = ""
    #: One of `RUN_TRIGGERS`.
    trigger: str = "command"
    #: The feed this ran, when one did. Empty for an upload or a command.
    feed_id: str = ""
    #: The feed's name as it read at the time — kept so history survives the feed's deletion.
    feed_name: str = ""
    actor: str = ""
    #: What it wrote to: a branch's identifier, or `main`.
    branch_id: str = ""
    #: What it read: the file names of an upload, or the staging tables of a feed.
    inputs: list[str] = field(default_factory=list)
    #: The mapping the run used, as it was used. A feed stores its mapping inline so a source's
    #: columns cannot change underneath it; keeping the same text here says which version of it
    #: produced these counts.
    mapping_yaml: str = ""
    started_at: Any = None
    finished_at: Any = None
    #: One of `RUN_STATUSES`.
    status: str = ""
    #: The report's own one-line summary, kept as written so the history and the screen that
    #: first showed it cannot drift into saying different things about the same run.
    summary: str = ""
    #: Why it stopped, when it did. Empty otherwise.
    message: str = ""
    elements_created: int = 0
    elements_updated: int = 0
    elements_unchanged: int = 0
    elements_retired: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0
    relationships_unchanged: int = 0
    relationships_retired: int = 0
    links_loaded: int = 0
    error_count: int = 0
    warning_count: int = 0
    #: A bounded sample, at most `MAX_RUN_ISSUES` of them.
    issues: list[Issue] = field(default_factory=list)
    #: Every issue the run found, counted by code — complete whether or not `issues` is.
    issue_counts: dict[str, int] = field(default_factory=dict)
    #: True when the run found more issues than the sample kept.
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def wrote(self) -> int:
        """How many rows it put in the model. Zero is a quiet night, not a failure."""
        return (
            self.elements_created
            + self.elements_updated
            + self.elements_retired
            + self.relationships_created
            + self.relationships_updated
            + self.relationships_retired
            + self.links_loaded
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
    #: Every issue found, counted by code, whether or not it was kept in `issues`.
    counts: dict[str, int] = field(default_factory=dict)
    #: How many of them were errors. `ok` reads this, not the kept list.
    error_count: int = 0
    #: True when more issues were found than the report keeps (`services.metamodel.MAX_ISSUES`).
    truncated: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        """No errors anywhere — counted over everything found, not over what was kept."""
        return not self.error_count and not self.errors

    def by_code(self) -> dict[str, int]:
        out = dict(self.counts) if self.counts else {}
        if not out:
            for i in self.issues:
                out[i.code] = out.get(i.code, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    def summary(self) -> str:
        return (
            f"{self.pack_id}@{self.version} on {self.org_id}: {self.elements} elements and "
            f"{self.relationships} relationships checked; {self.total_errors} errors, "
            f"{self.total_warnings} warnings"
        ) + (f" ({len(self.issues)} listed)" if self.truncated else "")

    @property
    def total_errors(self) -> int:
        """Errors found, whether or not the report kept them."""
        return self.error_count or len(self.errors)

    @property
    def total_warnings(self) -> int:
        return (sum(self.counts.values()) - self.total_errors) if self.counts else len(self.warnings)


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
