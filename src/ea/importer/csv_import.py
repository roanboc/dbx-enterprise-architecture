"""CSV ingestion: read -> map -> validate against the metamodel -> report -> load.

`import_frames` is the whole pipeline on in-memory frames (the app's upload page
uses it); `import_directory` wraps it for files on disk (the CLI uses it).
"""

from __future__ import annotations

import io
import re
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, current_branch
from ea.importer.mapping import (
    CORE_ELEMENT_COLUMNS,
    CORE_RELATIONSHIP_COLUMNS,
    DELETION_MODES,
    OPERATIONS,
    Mapping,
    derive_current_state,
)
from ea.importer.runs import recorded
from ea.metamodel.registry import Registry
from ea.models import (
    CURRENT_STATES,
    LINK_SCHEMES,
    TARGET_STATES,
    Element,
    Forbidden,
    ImportReport,
    Issue,
    Link,
    Relationship,
    slugify,
)
from ea.services.repository import coerce_attrs, coerce_relationship_attrs, relationship_key
from ea.services.roles import require

_SPLIT_LINKS = re.compile(r"\s*[|;]\s*")


def _norm_col(name: str) -> str:
    return slugify(str(name))


class CsvShapeError(ValueError):
    """A file whose rows do not match the header it declares."""

    def __init__(self, filename: str, detail: str) -> None:
        super().__init__(f"{filename}: {detail}")
        self.filename = filename
        self.detail = detail


#: Separators worth naming when a file parses as a single column: the list separator a
#: spreadsheet writes outside the English-speaking world, and a tab.
_OTHER_DELIMITERS = {";": "a semicolon", "\t": "a tab", "|": "a pipe"}


def _wrong_delimiter(frame: pd.DataFrame, delimiter: str) -> str:
    """The delimiter a one-column frame was really written with, described, or empty.

    Read with the wrong separator, a perfectly good file parses as one column whose name is
    the whole header line. Every row then lacks an id, and the importer blames the source's
    id column for what is a separator the reader was never told about.
    """
    if len(frame.columns) != 1:
        return ""
    header = str(frame.columns[0])
    for sep, name in _OTHER_DELIMITERS.items():
        if sep != delimiter and sep in header:
            return name
    return ""


def _read_frame(
    source: Any, filename: str, encoding: str | None = None, delimiter: str = ","
) -> pd.DataFrame:
    """One CSV, read strictly: a row that does not match the header is refused, not reshaped.

    Left to itself, a row carrying more fields than the header makes the parser promote the
    first column to the index, and every field on that row shifts one place left. The file
    then loads without a word, under identifiers it never declared — the worst outcome an
    importer can have. Refusing it is the only safe answer.
    """
    kwargs: dict[str, Any] = {
        "dtype": str,
        "keep_default_na": False,
        "index_col": False,
        "sep": delimiter,
    }
    if encoding is not None:
        kwargs["encoding"] = encoding
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", pd.errors.ParserWarning)
            frame = pd.read_csv(source, **kwargs)
    except pd.errors.EmptyDataError:
        raise CsvShapeError(filename, "the file is empty: it has no header row to read") from None
    except pd.errors.ParserError as exc:
        raise CsvShapeError(filename, " ".join(str(exc).split())) from None
    # A surplus field is a warning, not an error: the parser keeps the fields the header
    # declares and drops the rest. Dropping part of a row silently is the same failure as
    # shifting it, so the file is refused here too.
    ragged = [w for w in caught if issubclass(w.category, pd.errors.ParserWarning)]
    if ragged:
        raise CsvShapeError(filename, " ".join(str(ragged[0].message).split()))
    other = _wrong_delimiter(frame, delimiter)
    if other:
        raise CsvShapeError(
            filename,
            f"the whole header read as one column, so this file is separated by {other}, "
            f"not by {_OTHER_DELIMITERS.get(delimiter, 'a comma')}; "
            "set `delimiter` in the mapping YAML",
        )
    return frame


def read_csv_text(text: str, filename: str, delimiter: str = ",") -> pd.DataFrame:
    """The same strict read, for a file that arrived as text rather than a path."""
    return _read_frame(io.StringIO(text), filename, delimiter=delimiter)


def _read_csv(path: Path, encoding: str, delimiter: str = ",") -> pd.DataFrame:
    return _read_frame(path, path.name, encoding, delimiter)


def _rename(df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    """Apply the mapping's renames (exact header match first, then case-insensitive), then normalise the rest."""
    lower = {str(c).strip().lower(): c for c in df.columns}
    renames: dict[str, str] = {}
    for src, dst in columns.items():
        if src in df.columns:
            renames[src] = dst
        elif src.strip().lower() in lower:
            renames[lower[src.strip().lower()]] = dst
    df = df.rename(columns=renames)
    return df.rename(columns={c: _norm_col(c) for c in df.columns if c not in renames.values()})


def read_directory(
    directory: str | Path,
    mapping: Mapping | None = None,
    problems: list[CsvShapeError] | None = None,
) -> dict[str, list[tuple[str, pd.DataFrame]]]:
    """Frames per kind, tagged with the file they came from.

    A file whose rows do not match its header is collected into `problems` and left out,
    so one malformed file does not stop the rest; with no list to collect into, it raises.
    """
    mapping = mapping or Mapping()
    d = Path(directory)
    if not d.exists():
        raise FileNotFoundError(str(d))
    out: dict[str, list[tuple[str, pd.DataFrame]]] = {"elements": [], "relationships": [], "links": []}
    seen: set[Path] = set()
    for kind, patterns in (
        ("relationships", mapping.relationship_files),
        ("links", mapping.link_files),
        ("elements", mapping.element_files),
    ):
        for pat in patterns:
            for p in sorted(d.glob(pat)):
                if p in seen or not p.is_file():
                    continue
                seen.add(p)
                try:
                    out[kind].append((p.name, _read_csv(p, mapping.encoding, mapping.delimiter)))
                except CsvShapeError as exc:
                    if problems is None:
                        raise
                    problems.append(exc)
    return out


def _states(
    rec: dict,
    mapping: Mapping,
    report: ImportReport,
    row: int,
    fname: str,
    entity: str,
    by_key: dict[str, str] | None = None,
) -> dict[str, str]:
    """The four state fields of a row: given columns first, else the current state derived from the lifecycle text."""
    lifecycle = rec.get("lifecycle_status") or ""
    current = (rec.get("current_state") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if current and current not in CURRENT_STATES:
        report.add_issue(
            Issue(
                "warning",
                "unknown_current_state",
                f"current_state {current!r} not recognised; derived from the lifecycle text instead",
                row=row,
                entity=entity,
                file=fname,
            )
        )
        current = ""
    if not current:
        current = derive_current_state(lifecycle, mapping.lifecycle_states)
    target = (rec.get("target_state") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if target and target not in TARGET_STATES:
        report.add_issue(
            Issue(
                "warning",
                "unknown_target_state",
                f"target_state {target!r} not recognised; using 'undecided'",
                row=row,
                entity=entity,
                file=fname,
            )
        )
        target = ""
    return {
        "current_state": current,
        "target_state": target or "undecided",
        "target_work_package": element_ref(rec.get("target_work_package") or "", mapping, by_key or {}),
        "target_note": (rec.get("target_note") or "").strip(),
    }


#: What a long number looks like after a spreadsheet has opened and saved a file: an
#: identifier turned into scientific notation. It is the one spreadsheet damage that can be
#: recognised for certain, because no source issues an identifier in this shape.
_SCIENTIFIC = re.compile(r"^-?\d+(\.\d+)?[eE][+-]?\d+$")


def spreadsheet_damaged(identifier: str) -> bool:
    """Whether an identifier carries the mark of having been through a spreadsheet.

    Loading it would create an element under a name its source never issued, and quietly
    leave the real one untouched — so it is worth a word even though the row is otherwise
    perfectly well formed. Leading zeros lost from an identifier cannot be recognised this
    way: `7` is a legitimate identifier, and nothing in the file says it was once `007`.
    """
    return bool(_SCIENTIFIC.match((identifier or "").strip()))


MATCH_KEYS = ("id", "key")


def element_ref(raw: str, mapping: Mapping, by_key: dict[str, str]) -> str:
    """One identifier as written by the source, as the element id the store uses.

    Every identifier a source brings goes through here — the elements it declares, the
    endpoints of its relationships, the owners of its links, the work packages it names — so
    they cannot disagree about what a row is called.

    Merging on `key`, an element the store already holds under that key keeps the identity it
    was given; anything new takes the prefix and the key. Merging on `id`, which is the
    default, the prefix is all that is added.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    if mapping.match_on == "key":
        return by_key.get(raw) or f"{mapping.id_prefix}{raw}"
    return f"{mapping.id_prefix}{raw}"


def keys_in(frames: dict[str, list[tuple[str, pd.DataFrame]]], mapping: Mapping) -> set[str]:
    """Every identifier the source's files mention, for one look-up against the store."""
    out: set[str] = set()
    for kind, columns, wanted in (
        ("elements", mapping.element_columns, ("key", "id", "target_work_package")),
        ("relationships", mapping.relationship_columns, ("src_id", "dst_id", "target_work_package")),
        ("links", mapping.link_columns, ("element_id",)),
    ):
        for _fname, raw in frames.get(kind, []):
            df = _rename(raw, columns)
            for col in wanted:
                if col in df.columns:
                    out |= {v for v in df[col].astype(str).str.strip() if v}
    return out


def _operation(rec: dict, report: ImportReport, row: int, fname: str, entity: str) -> str:
    """What the row says it is doing: `upsert` (the default) or `delete`."""
    op = (rec.get("operation") or "upsert").strip().lower()
    if op not in OPERATIONS:
        report.add_issue(
            Issue(
                "warning",
                "unknown_operation",
                f"operation {op!r} not recognised; the row was loaded as content",
                row=row,
                entity=entity,
                file=fname,
            )
        )
        return "upsert"
    return op


def _resolve_type(registry: Registry, mapping: Mapping, label: str):
    if label in mapping.type_names:
        return registry.get_type(mapping.type_names[label])
    return registry.resolve_type(label)


def build_elements(
    registry: Registry,
    frames: list[tuple[str, pd.DataFrame]],
    mapping: Mapping,
    source_system: str,
    report: ImportReport,
    by_key: dict[str, str] | None = None,
) -> tuple[list[Element], list[Link], list[tuple[str, int, str]]]:
    by_key = by_key or {}
    elements: dict[str, Element] = {}
    links: list[Link] = []
    deletions: list[tuple[str, int, str]] = []
    for fname, raw in frames:
        df = _rename(raw, mapping.element_columns)
        if mapping.type_from_filename and "type" not in df.columns:
            df["type"] = Path(fname).stem
        for i, row in enumerate(df.to_dict("records"), start=2):
            report.elements_read += 1
            rec = {
                k: (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
                if k not in mapping.ignore_columns
            }
            for k, v in mapping.element_defaults.items():
                rec.setdefault(k, v)
                if rec.get(k) in ("", None):
                    rec[k] = v
            source_ident = (
                rec.get("key") or "" if mapping.match_on == "key" else rec.get("id") or rec.get("key") or ""
            )
            if spreadsheet_damaged(source_ident):
                report.add_issue(
                    Issue(
                        "warning",
                        "suspect_identifier",
                        f"identifier {source_ident!r} is in scientific notation, which is what a "
                        "spreadsheet does to a long number: the row would load under an identifier "
                        "its source never issued. Format the column as text before saving",
                        row=i,
                        entity=source_ident,
                        file=fname,
                    )
                )
            eid = element_ref(source_ident, mapping, by_key)
            if not eid:
                report.add_issue(
                    Issue(
                        "error",
                        "missing_key" if mapping.match_on == "key" else "missing_id",
                        "row has no key, and this mapping merges on the key"
                        if mapping.match_on == "key"
                        else "row has no id or key",
                        row=i,
                        file=fname,
                    )
                )
                report.elements_skipped += 1
                continue
            if _operation(rec, report, i, fname, eid) == "delete":
                # A source deleting a row sends the identifier and little else — it is saying
                # the thing is gone, not describing it. Requiring a type and a name here would
                # refuse the one row shape a deletion naturally has.
                deletions.append((eid, i, fname))
                continue
            t = _resolve_type(registry, mapping, rec.get("type", ""))
            if t is None:
                report.add_issue(
                    Issue(
                        "error",
                        "unknown_type",
                        f"unknown element type {rec.get('type')!r}",
                        row=i,
                        entity=eid,
                        file=fname,
                    )
                )
                report.elements_skipped += 1
                continue
            name = rec.get("name") or ""
            if not name:
                report.add_issue(
                    Issue("error", "missing_name", "name is required", row=i, entity=eid, file=fname)
                )
                report.elements_skipped += 1
                continue
            if eid in elements:
                report.add_issue(
                    Issue(
                        "warning",
                        "duplicate_id",
                        f"id {eid!r} appears more than once; last row wins",
                        row=i,
                        entity=eid,
                        file=fname,
                    )
                )
            raw_attrs = {
                k: v for k, v in rec.items() if k not in CORE_ELEMENT_COLUMNS and v not in ("", None)
            }
            attrs = coerce_attrs(registry, t.id, raw_attrs)
            for iss in registry.validate_element(t.id, attrs, entity=eid):
                iss.row, iss.file = i, fname
                if iss.code == "extra_attribute":
                    continue  # extras are kept; the pack can adopt them later
                report.add_issue(iss)
            status = (rec.get("status") or "approved").lower()
            if status not in ("draft", "approved", "retired"):
                report.add_issue(
                    Issue(
                        "warning",
                        "unknown_status",
                        f"status {status!r} not recognised; using 'approved'",
                        row=i,
                        entity=eid,
                        file=fname,
                    )
                )
                status = "approved"
            elements[eid] = Element(
                element_id=eid,
                type_id=t.id,
                name=name,
                key=rec.get("key") or "",
                description_md=rec.get("description") or "",
                status=status,
                lifecycle_status=rec.get("lifecycle_status") or "",
                source_system=rec.get("source_system") or source_system,
                source_ref=rec.get("source_ref") or source_ident,
                attrs=attrs,
                origin=rec.get("origin") or f"import:{rec.get('source_system') or source_system}",
                **_states(rec, mapping, report, i, fname, eid, by_key),
            )
            for j, url in enumerate(u for u in _SPLIT_LINKS.split(rec.get("links") or "") if u):
                report.links_read += 1
                links.append(Link(element_id=eid, url=url, label="", sort_order=j))
    return list(elements.values()), links, deletions


def build_relationships(
    registry: Registry,
    frames: list[tuple[str, pd.DataFrame]],
    mapping: Mapping,
    source_system: str,
    known: dict[str, str],
    report: ImportReport,
    by_key: dict[str, str] | None = None,
) -> list[Relationship]:
    by_key = by_key or {}
    rels: dict[str, Relationship] = {}
    for fname, raw in frames:
        df = _rename(raw, mapping.relationship_columns)
        for i, row in enumerate(df.to_dict("records"), start=2):
            report.relationships_read += 1
            rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            for k, v in mapping.relationship_defaults.items():
                if rec.get(k) in ("", None):
                    rec[k] = v
            src, dst, label, qualifier = (
                element_ref(rec.get("src_id", ""), mapping, by_key),
                element_ref(rec.get("dst_id", ""), mapping, by_key),
                rec.get("rel_type", ""),
                rec.get("qualifier", "") or "",
            )
            missing = [x for x in (src, dst) if x not in known]
            if not src or not dst or missing:
                report.add_issue(
                    Issue(
                        "error",
                        "dangling_relationship",
                        f"endpoint(s) not found: {missing or [src, dst]}",
                        row=i,
                        file=fname,
                        entity=f"{src}->{dst}",
                    )
                )
                report.relationships_skipped += 1
                continue
            label = mapping.rel_names.get(label, label)
            rt = registry.resolve_rel_type(label, known[src], known[dst])
            status = (rec.get("status") or "approved").lower()
            if _operation(rec, report, i, fname, f"{src}->{dst}") == "delete":
                # An edge's identity is derived from its ends and its type, so a delete row
                # has to carry them anyway — there is nothing to look up, only a state to set.
                status = "retired"
                report.relationships_retired += 1
            attrs = {
                k: v for k, v in rec.items() if k not in CORE_RELATIONSHIP_COLUMNS and v not in ("", None)
            }
            if rt is None:
                allowed = (
                    ", ".join(r.name for r in registry.allowed_rel_types(known[src], known[dst])) or "none"
                )
                report.add_issue(
                    Issue(
                        "error",
                        "unknown_relationship_type",
                        f"no relationship {label!r} from {known[src]} to {known[dst]} (allowed: {allowed})",
                        row=i,
                        file=fname,
                        entity=f"{src}->{dst}",
                    )
                )
                report.relationships_skipped += 1
                continue
            attrs = coerce_relationship_attrs(registry, rt.id, attrs)
            issues = registry.validate_relationship(
                rt.id, known[src], known[dst], qualifier, entity=f"{src}->{dst}", attrs=attrs
            )
            for iss in issues:
                iss.row, iss.file = i, fname
                if iss.code == "extra_attribute":
                    continue  # extras are kept on the edge as they are on an element
                if iss.level == "error":
                    iss.level = "warning"
                    iss.message += " — imported as draft"
                    status = "draft"
                    attrs["validation"] = iss.code
                report.add_issue(iss)
            rsource = rec.get("source_system") or source_system
            rid = relationship_key(rsource, rt.id, src, dst, qualifier)
            if rid in rels:
                report.add_issue(
                    Issue(
                        "info",
                        "duplicate_relationship",
                        "same edge appears more than once; kept once",
                        row=i,
                        file=fname,
                        entity=f"{src}->{dst}",
                    )
                )
                continue
            rels[rid] = Relationship(
                relationship_id=rid,
                rel_type_id=rt.id,
                src_id=src,
                dst_id=dst,
                qualifier=qualifier,
                attrs=attrs,
                status=status,
                origin=f"import:{rsource}",
                source_system=rsource,
                source_ref=rec.get("source_ref") or "",
                **_states(rec, mapping, report, i, fname, f"{src}->{dst}", by_key),
            )
    return list(rels.values())


def build_links(
    frames: list[tuple[str, pd.DataFrame]],
    mapping: Mapping,
    known: dict[str, str],
    report: ImportReport,
    backend: DatabaseBackend | None = None,
    by_key: dict[str, str] | None = None,
) -> list[Link]:
    """Links for elements this import brought, and for elements the model already holds.

    A links file is routinely loaded on its own — a second pass adding documentation to
    elements imported last week. Knowing only what came in the same upload would call
    every one of those unknown and drop the file.
    """
    rows: list[tuple[str, int, str, str, str]] = []
    for fname, raw in frames:
        df = _rename(raw, mapping.link_columns)
        for i, row in enumerate(df.to_dict("records"), start=2):
            report.links_read += 1
            rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            rows.append(
                (
                    fname,
                    i,
                    element_ref(rec.get("element_id", ""), mapping, by_key or {}),
                    rec.get("url", ""),
                    rec.get("label") or "",
                )
            )
    # Everything the store might already hold, asked once rather than once per row: a links
    # file naming ten thousand elements used to be ten thousand round trips (decision 0019).
    unknown = {eid for _f, _i, eid, _u, _l in rows if eid and eid not in known}
    in_store: set[str] = set()
    if unknown and backend is not None:
        in_store = {e.element_id for e in backend.elements_by_ids(sorted(unknown))}
    links: list[Link] = []
    order: dict[str, int] = {}
    for fname, i, eid, url, label in rows:
        if not (eid and (eid in known or eid in in_store)) or not url:
            report.add_issue(
                Issue(
                    "warning",
                    "dangling_link",
                    f"link for unknown element {eid!r} or empty url",
                    row=i,
                    file=fname,
                    entity=eid,
                )
            )
            continue
        if not url.lower().startswith(LINK_SCHEMES):
            # The element page refuses the same line for the same reason: a `javascript:`
            # line waiting for a click is not a link to a source.
            report.add_issue(
                Issue(
                    "warning",
                    "bad_link",
                    f"link for {eid!r} refused: {url!r} is not an http, https or mailto address",
                    row=i,
                    file=fname,
                    entity=eid,
                )
            )
            continue
        order[eid] = order.get(eid, -1) + 1
        links.append(Link(element_id=eid, url=url, label=label, sort_order=order[eid]))
    return links


def _one_per_url(links: list[Link]) -> list[Link]:
    """One link per URL, in the order they arrived, keeping the one that carries a label.

    The same URL reaches an element twice whenever a source states it both in the elements
    file's `links` column and in the links file — which is exactly what an export of this
    repository's own content does, since it writes both. Two identical rows is never what
    either file meant.
    """
    out: dict[str, Link] = {}
    for ln in links:
        kept = out.get(ln.url)
        if kept is None:
            out[ln.url] = ln
        elif not (kept.label or "") and (ln.label or ""):
            kept.label = ln.label
    for i, ln in enumerate(out.values()):
        ln.sort_order = i
    return list(out.values())


def _write_links(
    backend: DatabaseBackend, links: list[Link], imported: set[str], actor: str, report: ImportReport
) -> None:
    """Land the import's links, adding to an element this import did not itself bring.

    `set_links` replaces an element's links wholesale, which is right for an element whose own
    row was in this import: that row declares what its links are. It is wrong for a links file
    loaded on its own, which this module documents as a second pass adding documentation — a
    one-row file would silently delete everything else the element had. So that case merges:
    what is stored stays, a URL sent again may carry a new label, and the rest is appended.
    """
    by_el: dict[str, list[Link]] = {}
    for ln in links:
        by_el.setdefault(ln.element_id, []).append(ln)
    for eid, lns in by_el.items():
        lns = _one_per_url(lns)
        to_write = lns
        if eid not in imported:
            fresh = {ln.url: ln for ln in lns}
            to_write = [fresh.pop(ln.url, ln) for ln in backend.get_links(eid)]
            to_write.extend(fresh.values())
        backend.set_links(eid, to_write, actor)
        report.links_loaded += len(lns)


def _identities_by_key(
    backend: DatabaseBackend,
    frames: dict[str, list[tuple[str, pd.DataFrame]]],
    mapping: Mapping,
    report: ImportReport,
) -> dict[str, str]:
    """Key -> the element id the store already gave it, for a mapping that merges on the key.

    One read for every identifier the source's files mention rather than one per row. A key is
    not the store's identity and nothing makes it unique, so a key that names two elements is
    reported and the first by identifier is taken — silently picking one is how an import
    rewrites the wrong element.
    """
    if mapping.match_on != "key":
        return {}
    found: dict[str, list[str]] = {}
    for e in backend.elements_by_keys(sorted(keys_in(frames, mapping))):
        if e.key:
            found.setdefault(e.key, []).append(e.element_id)
    out: dict[str, str] = {}
    for key, ids in found.items():
        ids.sort()
        out[key] = ids[0]
        if len(ids) > 1:
            report.add_issue(
                Issue(
                    "warning",
                    "ambiguous_key",
                    f"key {key!r} names {len(ids)} elements ({', '.join(ids)}); merged onto {ids[0]}",
                    entity=ids[0],
                )
            )
    return out


def _retire(
    backend: DatabaseBackend, deletions: list[tuple[str, int, str]], report: ImportReport
) -> list[Element]:
    """The elements a source said are gone, read back and marked retired.

    Retiring rather than removing is what a source is allowed to do today: the element, its
    relationships and its history stay, and loading the row again undoes it. The rows go back
    through the same upsert as everything else, so they are versioned and logged like any
    other change rather than through a path of their own.
    """
    if not deletions:
        return []
    wanted = {eid for eid, _row, _file in deletions}
    held = {e.element_id: e for e in backend.elements_by_ids(sorted(wanted))}
    out: list[Element] = []
    for eid, row, fname in deletions:
        existing = held.get(eid)
        if existing is None:
            report.add_issue(
                Issue(
                    "warning",
                    "delete_unknown",
                    f"the row says {eid!r} is deleted, but the model does not hold it",
                    row=row,
                    entity=eid,
                    file=fname,
                )
            )
            continue
        if existing.status == "retired":
            continue  # already gone; nothing to write, and nothing to report as a change
        existing.status = "retired"
        out.append(existing)
        report.elements_retired += 1
    return out


def import_frames(
    backend: DatabaseBackend,
    registry: Registry,
    frames: dict[str, list[tuple[str, pd.DataFrame]]],
    source_system: str,
    mapping: Mapping | None = None,
    actor: str = "import",
    dry_run: bool = False,
) -> ImportReport:
    mapping = mapping or Mapping()
    source_system = source_system or mapping.source_system or "import"
    report = ImportReport(source_system=source_system, dry_run=dry_run)
    if mapping.match_on not in MATCH_KEYS:
        raise ValueError(f"match_on must be one of {MATCH_KEYS}, not {mapping.match_on!r}")
    if mapping.deletion_mode not in DELETION_MODES:
        raise ValueError(
            f"deletion_mode must be one of {DELETION_MODES}, not {mapping.deletion_mode!r}: "
            "removing a row outright waits on what should happen to a relationship whose "
            "endpoint went with it"
        )
    by_key = _identities_by_key(backend, frames, mapping, report)
    elements, inline_links, deletions = build_elements(
        registry, frames.get("elements", []), mapping, source_system, report, by_key
    )
    elements += _retire(backend, deletions, report)
    known = {e.element_id: e.type_id for e in elements}
    # Endpoints may already be in the store from an earlier import. Every one of them is asked
    # for in one read rather than one apiece (decision 0019).
    wanted: set[str] = set()
    for _fname, raw in frames.get("relationships", []):
        df = _rename(raw, mapping.relationship_columns)
        for col in ("src_id", "dst_id"):
            if col in df.columns:
                wanted |= {e for e in set(df[col].astype(str).str.strip()) - set(known) if e}
    for existing in backend.elements_by_ids(sorted(wanted)) if wanted else []:
        known[existing.element_id] = existing.type_id
    rels = build_relationships(
        registry, frames.get("relationships", []), mapping, source_system, known, report, by_key
    )
    links = inline_links + build_links(frames.get("links", []), mapping, known, report, backend, by_key)
    packages = {e.target_work_package for e in elements + rels if e.target_work_package}  # type: ignore[operator]
    unresolved = {w for w in packages if w not in known}
    if unresolved:
        unresolved -= {e.element_id for e in backend.elements_by_ids(sorted(unresolved))}
    for e in elements + rels:  # type: ignore[operator]
        wp = e.target_work_package
        if wp and wp in unresolved:
            entity = e.element_id if isinstance(e, Element) else f"{e.src_id}->{e.dst_id}"
            report.add_issue(
                Issue(
                    "warning",
                    "unknown_work_package",
                    f"target_work_package {wp!r} is not an element; kept as written",
                    entity=entity,
                )
            )
    if dry_run:
        return report
    require("import", what="load content")
    if current_branch() == MAIN:
        require("edit_main", what="load onto main; load onto a branch")
    b = backend.get_branch(current_branch()) if current_branch() != MAIN else None
    if b is not None and b.status in ("in_review", "approved"):
        raise Forbidden(
            f"branch {b.branch_id} is {b.status.replace('_', ' ')}: frozen until the review is decided"
        )
    report.elements_created, report.elements_updated, report.elements_unchanged = backend.upsert_elements(
        elements, actor
    )
    report.elements_loaded = report.elements_created + report.elements_updated + report.elements_unchanged
    (
        report.relationships_created,
        report.relationships_updated,
        report.relationships_unchanged,
    ) = backend.upsert_relationships(rels, actor)
    report.relationships_loaded = (
        report.relationships_created + report.relationships_updated + report.relationships_unchanged
    )
    _write_links(backend, links, set(known) & {e.element_id for e in elements}, actor, report)
    return report


def import_directory(
    backend: DatabaseBackend,
    registry: Registry,
    directory: str | Path,
    source_system: str = "",
    mapping: Mapping | None = None,
    actor: str = "import",
    dry_run: bool = False,
) -> ImportReport:
    mapping = mapping or Mapping()
    problems: list[CsvShapeError] = []
    frames = read_directory(directory, mapping, problems)
    if not any(frames.values()) and not problems:
        raise FileNotFoundError(f"no CSV files matched in {directory}")
    source = source_system or mapping.source_system or Path(directory).name
    # The run is recorded around the whole of it rather than around `import_frames`, because a
    # file this directory held and could not read is part of what the run was.
    with recorded(
        backend,
        trigger="command",
        actor=actor,
        source_system=source,
        inputs=_file_names(frames, problems),
        dry_run=dry_run,
    ) as run:
        report = import_frames(backend, registry, frames, source, mapping, actor, dry_run)
        for problem in problems:
            report.add_issue(
                Issue(
                    level="error",
                    code="ragged_row",
                    message=f"a row does not match the header this file declares: {problem.detail}",
                    file=problem.filename,
                )
            )
        run.report = report
    return report


def _file_names(
    frames: dict[str, list[tuple[str, pd.DataFrame]]], problems: list[CsvShapeError]
) -> list[str]:
    """Every file the import touched, read or refused, each named once."""
    names = {fname for pairs in frames.values() for fname, _ in pairs}
    names |= {p.filename for p in problems}
    return sorted(names)
