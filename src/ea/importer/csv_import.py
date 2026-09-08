"""CSV ingestion: read -> map -> validate against the metamodel -> report -> load.

`import_frames` is the whole pipeline on in-memory frames (the app's upload page
uses it); `import_directory` wraps it for files on disk (the CLI uses it).
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, current_branch
from ea.importer.mapping import (
    CORE_ELEMENT_COLUMNS,
    CORE_LINK_COLUMNS,
    CORE_RELATIONSHIP_COLUMNS,
    Mapping,
    derive_current_state,
)
from ea.metamodel.registry import Registry
from ea.models import (
    CURRENT_STATES,
    TARGET_STATES,
    Element,
    Forbidden,
    ImportReport,
    Issue,
    Link,
    Relationship,
    slugify,
)
from ea.services.repository import coerce_attrs, relationship_key
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


def _read_frame(source: Any, filename: str, encoding: str | None = None) -> pd.DataFrame:
    """One CSV, read strictly: a row that does not match the header is refused, not reshaped.

    Left to itself, a row carrying more fields than the header makes the parser promote the
    first column to the index, and every field on that row shifts one place left. The file
    then loads without a word, under identifiers it never declared — the worst outcome an
    importer can have. Refusing it is the only safe answer.
    """
    kwargs: dict[str, Any] = {"dtype": str, "keep_default_na": False, "index_col": False}
    if encoding is not None:
        kwargs["encoding"] = encoding
    try:
        return pd.read_csv(source, **kwargs)
    except pd.errors.ParserError as exc:
        raise CsvShapeError(filename, " ".join(str(exc).split())) from None


def read_csv_text(text: str, filename: str) -> pd.DataFrame:
    """The same strict read, for a file that arrived as text rather than a path."""
    return _read_frame(io.StringIO(text), filename)


def _read_csv(path: Path, encoding: str) -> pd.DataFrame:
    return _read_frame(path, path.name, encoding)


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
                    out[kind].append((p.name, _read_csv(p, mapping.encoding)))
                except CsvShapeError as exc:
                    if problems is None:
                        raise
                    problems.append(exc)
    return out


def _states(
    rec: dict, mapping: Mapping, report: ImportReport, row: int, fname: str, entity: str
) -> dict[str, str]:
    """The four state fields of a row: given columns first, else the current state derived from the lifecycle text."""
    lifecycle = rec.get("lifecycle_status") or ""
    current = (rec.get("current_state") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if current and current not in CURRENT_STATES:
        report.issues.append(
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
        report.issues.append(
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
        "target_work_package": (rec.get("target_work_package") or "").strip(),
        "target_note": (rec.get("target_note") or "").strip(),
    }


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
) -> tuple[list[Element], list[Link]]:
    elements: dict[str, Element] = {}
    links: list[Link] = []
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
            eid = rec.get("id") or rec.get("key") or ""
            if not eid:
                report.issues.append(Issue("error", "missing_id", "row has no id or key", row=i, file=fname))
                report.elements_skipped += 1
                continue
            t = _resolve_type(registry, mapping, rec.get("type", ""))
            if t is None:
                report.issues.append(
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
                report.issues.append(
                    Issue("error", "missing_name", "name is required", row=i, entity=eid, file=fname)
                )
                report.elements_skipped += 1
                continue
            if eid in elements:
                report.issues.append(
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
                report.issues.append(iss)
            status = (rec.get("status") or "approved").lower()
            if status not in ("draft", "approved", "retired"):
                report.issues.append(
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
                source_system=source_system,
                source_ref=rec.get("source_ref") or eid,
                attrs=attrs,
                origin=rec.get("origin") or f"import:{source_system}",
                **_states(rec, mapping, report, i, fname, eid),
            )
            for j, url in enumerate(u for u in _SPLIT_LINKS.split(rec.get("links") or "") if u):
                report.links_read += 1
                links.append(Link(element_id=eid, url=url, label="", sort_order=j))
    return list(elements.values()), links


def build_relationships(
    registry: Registry,
    frames: list[tuple[str, pd.DataFrame]],
    mapping: Mapping,
    source_system: str,
    known: dict[str, str],
    report: ImportReport,
) -> list[Relationship]:
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
                rec.get("src_id", ""),
                rec.get("dst_id", ""),
                rec.get("rel_type", ""),
                rec.get("qualifier", "") or "",
            )
            missing = [x for x in (src, dst) if x not in known]
            if not src or not dst or missing:
                report.issues.append(
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
            attrs = {
                k: v for k, v in rec.items() if k not in CORE_RELATIONSHIP_COLUMNS and v not in ("", None)
            }
            if rt is None:
                allowed = (
                    ", ".join(r.name for r in registry.allowed_rel_types(known[src], known[dst])) or "none"
                )
                report.issues.append(
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
            issues = registry.validate_relationship(
                rt.id, known[src], known[dst], qualifier, entity=f"{src}->{dst}"
            )
            for iss in issues:
                iss.row, iss.file = i, fname
                if iss.level == "error":
                    iss.level = "warning"
                    iss.message += " — imported as draft"
                    status = "draft"
                    attrs["validation"] = iss.code
                report.issues.append(iss)
            rid = relationship_key(source_system, rt.id, src, dst, qualifier)
            if rid in rels:
                report.issues.append(
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
                origin=f"import:{source_system}",
                source_system=source_system,
                source_ref=rec.get("source_ref") or "",
                **_states(rec, mapping, report, i, fname, f"{src}->{dst}"),
            )
    return list(rels.values())


def build_links(
    frames: list[tuple[str, pd.DataFrame]], mapping: Mapping, known: dict[str, str], report: ImportReport
) -> list[Link]:
    links: list[Link] = []
    for fname, raw in frames:
        df = _rename(raw, mapping.link_columns)
        for i, row in enumerate(df.to_dict("records"), start=2):
            report.links_read += 1
            rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            eid, url = rec.get("element_id", ""), rec.get("url", "")
            if eid not in known or not url:
                report.issues.append(
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
            links.append(Link(element_id=eid, url=url, label=rec.get("label") or "", sort_order=len(links)))
    _ = CORE_LINK_COLUMNS
    return links


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
    report = ImportReport(source_system=source_system)
    elements, inline_links = build_elements(
        registry, frames.get("elements", []), mapping, source_system, report
    )
    known = {e.element_id: e.type_id for e in elements}
    # endpoints may already be in the store from an earlier import
    for _fname, raw in frames.get("relationships", []):
        df = _rename(raw, mapping.relationship_columns)
        for col in ("src_id", "dst_id"):
            if col in df.columns:
                for eid in set(df[col].astype(str).str.strip()) - set(known):
                    if eid:
                        existing = backend.get_element(eid)
                        if existing:
                            known[eid] = existing.type_id
    rels = build_relationships(
        registry, frames.get("relationships", []), mapping, source_system, known, report
    )
    links = inline_links + build_links(frames.get("links", []), mapping, known, report)
    for e in elements + rels:  # type: ignore[operator]
        wp = e.target_work_package
        if wp and wp not in known and backend.get_element(wp) is None:
            entity = e.element_id if isinstance(e, Element) else f"{e.src_id}->{e.dst_id}"
            report.issues.append(
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
    ins, upd = backend.upsert_elements(elements, actor)
    report.elements_loaded = ins + upd
    ins, upd = backend.upsert_relationships(rels, actor)
    report.relationships_loaded = ins + upd
    by_el: dict[str, list[Link]] = {}
    for ln in links:
        by_el.setdefault(ln.element_id, []).append(ln)
    for eid, lns in by_el.items():
        backend.set_links(eid, lns, actor)
        report.links_loaded += len(lns)
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
    report = import_frames(
        backend,
        registry,
        frames,
        source_system or mapping.source_system or Path(directory).name,
        mapping,
        actor,
        dry_run,
    )
    for problem in problems:
        report.issues.append(
            Issue(
                level="error",
                code="ragged_row",
                message=f"a row does not match the header this file declares: {problem.detail}",
                file=problem.filename,
            )
        )
    return report
