"""The store on SQL, once: every read and write the engines share.

One schema, two engines (decision 0002). Everything the repository asks of a
SQL store — the overlay a branch lays over `main`, the optimistic concurrency,
the change log, the diff and the merge — is written here against the portable
DDL of `sql.py`. An engine (`duckdb_backend.py`, `databricks_backend.py`) adds
only what differs: how to connect, how to run a statement, how to land many
rows at once, and how to spell a type.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, current_branch, validate_branch_id
from ea.backend.sql import (
    DDL,
    ELEMENT_COLUMNS,
    RELATIONSHIP_COLUMNS,
    TRACE_IN_SQL,
    TRACE_OUT_SQL,
    table_columns,
)
from ea.metamodel.loader import pack_from_dict
from ea.models import (
    OPEN_STATUSES,
    Branch,
    ChangeItem,
    ChangeSet,
    ConflictError,
    Element,
    Link,
    MergeResult,
    NotFoundError,
    Pack,
    Proposal,
    Relationship,
    Review,
)

_READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|attach|copy|export|import|pragma|call|"
    r"install|load|grant|revoke|vacuum|optimize|restore|refresh|msck)\b",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        out = json.loads(value)
        return out if isinstance(out, dict) else {}
    except (TypeError, ValueError):
        return {}


def new_id(prefix: str = "") -> str:
    return (prefix + "-" if prefix else "") + uuid.uuid4().hex[:12]


def chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class SqlBackend(DatabaseBackend):
    """The repository contract on any SQL engine that runs the portable DDL.

    An engine implements the hooks in the first section; everything below them
    is shared, so the DuckDB suite is the acceptance suite of every engine.
    """

    #: how many identifiers one `IN (...)` list may carry (a parameter marker each)
    IN_CHUNK = 500
    #: the engine's spelling of the DDL's VARCHAR, for the casts inside the trace query
    STRING_TYPE = "VARCHAR"

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------ engine hooks
    def _execute(self, sql: str, params: list[Any] | None = None) -> None:
        raise NotImplementedError

    def _fetch_all(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        raise NotImplementedError

    def _fetch_df(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        raise NotImplementedError

    def _insert_rows(self, table: str, rows: list[list[Any]]) -> None:
        """Append rows given positionally, in the table's column order."""
        raise NotImplementedError

    def _replace_rows(self, table: str, columns: list[str], rows: list[list[Any]], keys: list[str]) -> None:
        """Land rows by key: a row whose key exists is replaced, any other is appended."""
        raise NotImplementedError

    def _create_table(self, ddl: str) -> None:
        self._execute(ddl)

    def _add_missing_columns(self) -> None:
        """Bring a store created by an earlier version up to the DDL (the MIGRATIONS list)."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    # ---------------------------------------------------------------- helpers
    def _log(
        self,
        kind: str,
        entity_id: str,
        op: str,
        actor: str,
        before: Any,
        after: Any,
        version: int | None,
        branch: str | None = None,
    ) -> None:
        self._execute(
            "INSERT INTO change_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_id("chg"),
                kind,
                entity_id,
                op,
                actor,
                _now(),
                _dumps(before) if before else None,
                _dumps(after) if after else None,
                version,
                branch if branch is not None else current_branch(),
            ],
        )

    @staticmethod
    def _marks(items: Iterable[Any]) -> str:
        return ", ".join("?" for _ in items)

    @staticmethod
    def _page(limit: int, offset: int = 0) -> str:
        """LIMIT and OFFSET inline: integers the code chose, never the reader's text."""
        return f" LIMIT {int(limit)}" + (f" OFFSET {int(offset)}" if offset else "")

    # ------------------------------------------------------------ branch overlay
    @staticmethod
    def _q(branch: str) -> str:
        """A branch id as a SQL literal; ids are validated so this is safe."""
        return "'" + validate_branch_id(branch).replace("'", "''") + "'"

    def _el(self, branch: str | None = None) -> str:
        """The element source for the branch: the table on main, the overlay elsewhere."""
        b = branch or current_branch()
        if b == MAIN:
            return "element"
        cols = ", ".join(ELEMENT_COLUMNS)
        return (
            f"(SELECT {cols} FROM element WHERE element_id NOT IN "
            f"(SELECT element_id FROM branch_element WHERE branch_id = {self._q(b)}) "
            f"UNION ALL SELECT {cols} FROM branch_element WHERE branch_id = {self._q(b)} AND op = 'upsert')"
        )

    def _rel(self, branch: str | None = None) -> str:
        b = branch or current_branch()
        if b == MAIN:
            return "relationship"
        cols = ", ".join(RELATIONSHIP_COLUMNS)
        return (
            f"(SELECT {cols} FROM relationship WHERE relationship_id NOT IN "
            f"(SELECT relationship_id FROM branch_relationship WHERE branch_id = {self._q(b)}) "
            f"UNION ALL SELECT {cols} FROM branch_relationship WHERE branch_id = {self._q(b)} AND op = 'upsert')"
        )

    def _branch_element_row(self, branch: str, element_id: str) -> tuple[int, str] | None:
        rows = self._fetch_all(
            "SELECT base_version, op FROM branch_element WHERE branch_id = ? AND element_id = ?",
            [branch, element_id],
        )
        return (int(rows[0][0]), rows[0][1]) if rows else None

    def _branch_rel_row(self, branch: str, relationship_id: str) -> tuple[int, str] | None:
        rows = self._fetch_all(
            "SELECT base_version, op FROM branch_relationship WHERE branch_id = ? AND relationship_id = ?",
            [branch, relationship_id],
        )
        return (int(rows[0][0]), rows[0][1]) if rows else None

    def _main_element_version(self, element_id: str) -> int | None:
        rows = self._fetch_all("SELECT _version FROM element WHERE element_id = ?", [element_id])
        return int(rows[0][0]) if rows else None

    def _main_rel_version(self, relationship_id: str) -> int | None:
        rows = self._fetch_all(
            "SELECT _version FROM relationship WHERE relationship_id = ?", [relationship_id]
        )
        return int(rows[0][0]) if rows else None

    def _write_branch_element(self, branch: str, e: Element, base_version: int, op: str = "upsert") -> None:
        with self._lock:
            first_time = self._branch_element_row(branch, e.element_id) is None
            self._execute(
                "DELETE FROM branch_element WHERE branch_id = ? AND element_id = ?", [branch, e.element_id]
            )
            self._insert_rows("branch_element", [self._element_values(e) + [branch, base_version, op]])
            if first_time and base_version > 0:
                self._copy_main_links(branch, [e.element_id])

    def _copy_main_links(self, branch: str, element_ids: list[str]) -> None:
        """An element's links follow it onto the branch the first time it is written there, so a
        change to the element alone never reads as a change to its links."""
        for chunk in chunks(element_ids, self.IN_CHUNK):
            self._execute(
                f"INSERT INTO branch_link SELECT link_id, element_id, url, label, sort_order, ? FROM element_link "
                f"WHERE element_id IN ({self._marks(chunk)}) AND element_id NOT IN "
                f"(SELECT element_id FROM branch_link WHERE branch_id = ?)",
                [branch, *chunk, branch],
            )

    def _write_branch_rel(self, branch: str, r: Relationship, base_version: int, op: str = "upsert") -> None:
        with self._lock:
            self._execute(
                "DELETE FROM branch_relationship WHERE branch_id = ? AND relationship_id = ?",
                [branch, r.relationship_id],
            )
            self._insert_rows("branch_relationship", [self._rel_values(r) + [branch, base_version, op]])

    # ---------------------------------------------------------- lifecycle
    def init_schema(self) -> None:
        with self._lock:
            for ddl in DDL.values():
                self._create_table(ddl)
            self._add_missing_columns()

    # ---------------------------------------------------------- metamodel
    def save_pack(self, pack: Pack) -> None:
        attribute_rows: list[list[Any]] = []
        for i, a in enumerate(pack.common_attributes):
            attribute_rows.append(
                [
                    pack.id,
                    None,
                    a.name,
                    a.label,
                    a.type,
                    a.required,
                    json.dumps(a.enum) if a.enum else None,
                    a.description,
                    a.sensitivity,
                    i,
                ]
            )
        type_rows: list[list[Any]] = []
        for t in pack.element_types:
            type_rows.append(
                [
                    pack.id,
                    t.id,
                    t.name,
                    t.plural,
                    t.supertype,
                    t.active,
                    t.deactivation_reason,
                    t.domain,
                    t.provenance,
                    t.prefix,
                    t.description,
                    json.dumps(t.examples),
                    t.source_of_record,
                    t.type_owner,
                    t.instance_owner,
                    t.sort_order,
                    json.dumps(t.notation),
                ]
            )
            for i, a in enumerate(t.attributes):
                attribute_rows.append(
                    [
                        pack.id,
                        t.id,
                        a.name,
                        a.label,
                        a.type,
                        a.required,
                        json.dumps(a.enum) if a.enum else None,
                        a.description,
                        a.sensitivity,
                        i,
                    ]
                )
        rel_rows = [
            [
                pack.id,
                r.id,
                r.name,
                r.inverse,
                r.source,
                r.target,
                r.provenance,
                json.dumps(r.qualifiers),
                json.dumps(r.diagrams),
                r.description,
                r.src_max,
                r.dst_max,
                r.sort_order,
            ]
            for r in pack.relationship_types
        ]
        domain_rows = [
            [pack.id, d.id, d.name, d.description, d.sort_order, json.dumps(d.notation)] for d in pack.domains
        ]
        with self._lock:
            for t in (
                "meta_pack",
                "meta_domain",
                "meta_element_type",
                "meta_attribute",
                "meta_relationship_type",
            ):
                self._execute(f"DELETE FROM {t} WHERE pack_id = ?", [pack.id])
            self._insert_rows(
                "meta_pack",
                [
                    [
                        pack.id,
                        pack.name,
                        pack.version,
                        pack.description,
                        pack.source,
                        json.dumps(pack.provenance_values),
                        _now(),
                    ]
                ],
            )
            self._insert_rows("meta_domain", domain_rows)
            self._insert_rows("meta_element_type", type_rows)
            self._insert_rows("meta_attribute", attribute_rows)
            self._insert_rows("meta_relationship_type", rel_rows)

    def load_pack(self, pack_id: str) -> Pack | None:
        rows = self._fetch_all(
            "SELECT pack_id, name, version, description, source, provenance_values FROM meta_pack WHERE pack_id = ?",
            [pack_id],
        )
        if not rows:
            return None
        pid, name, version, description, source, prov = rows[0]
        domains = [
            {"id": d, "name": n, "description": desc, "notation": json.loads(notation or "{}")}
            for d, n, desc, notation in self._fetch_all(
                "SELECT domain_id, name, description, notation FROM meta_domain WHERE pack_id = ? ORDER BY sort_order",
                [pid],
            )
        ]
        attrs = self._fetch_all(
            "SELECT type_id, name, label, datatype, required, enum_values, description, sensitivity FROM meta_attribute WHERE pack_id = ? ORDER BY sort_order",
            [pid],
        )

        def attr_dict(row: tuple) -> dict[str, Any]:
            _, aname, label, dtype, required, enum_values, adesc, sens = row
            d: dict[str, Any] = {
                "name": aname,
                "label": label,
                "type": dtype,
                "required": bool(required),
                "description": adesc,
                "sensitivity": sens,
            }
            if enum_values:
                d["enum"] = json.loads(enum_values)
            return d

        common = [attr_dict(a) for a in attrs if a[0] is None]
        element_types = []
        for row in self._fetch_all(
            "SELECT type_id, name, plural, supertype_id, active, deactivation_reason, domain_id, provenance, prefix, description, examples, source_of_record, type_owner, instance_owner, notation FROM meta_element_type WHERE pack_id = ? ORDER BY sort_order",
            [pid],
        ):
            tid = row[0]
            element_types.append(
                {
                    "id": tid,
                    "name": row[1],
                    "plural": row[2],
                    "supertype": row[3],
                    "active": bool(row[4]),
                    "deactivation_reason": row[5],
                    "domain": row[6],
                    "provenance": row[7],
                    "prefix": row[8],
                    "description": row[9],
                    "examples": json.loads(row[10] or "[]"),
                    "source_of_record": row[11],
                    "type_owner": row[12],
                    "instance_owner": row[13],
                    "notation": json.loads(row[14] or "{}"),
                    "attributes": [attr_dict(a) for a in attrs if a[0] == tid],
                }
            )
        relationship_types = [
            {
                "id": r[0],
                "name": r[1],
                "inverse": r[2],
                "source": r[3],
                "target": r[4],
                "provenance": r[5],
                "qualifiers": json.loads(r[6] or "[]"),
                "diagrams": json.loads(r[7] or "[]"),
                "description": r[8],
                "src_max": r[9],
                "dst_max": r[10],
            }
            for r in self._fetch_all(
                "SELECT rel_type_id, name, inverse_name, source_type_id, target_type_id, provenance, qualifiers, diagrams, description, src_max, dst_max FROM meta_relationship_type WHERE pack_id = ? ORDER BY sort_order",
                [pid],
            )
        ]
        return pack_from_dict(
            {
                "pack": {
                    "id": pid,
                    "name": name,
                    "version": version,
                    "description": description,
                    "source": source,
                    "provenance_values": json.loads(prov or "[]"),
                },
                "domains": domains,
                "common_attributes": common,
                "element_types": element_types,
                "relationship_types": relationship_types,
            }
        )

    def list_packs(self) -> list[dict[str, Any]]:
        df = self._fetch_df("SELECT pack_id, name, version, loaded_at FROM meta_pack ORDER BY loaded_at DESC")
        return df.to_dict("records")

    # ----------------------------------------------------------- elements
    @staticmethod
    def _row_to_element(row: tuple) -> Element:
        d = dict(zip(ELEMENT_COLUMNS, row, strict=True))
        return Element(
            element_id=d["element_id"],
            type_id=d["type_id"],
            key=d["key"] or "",
            name=d["name"],
            description_md=d["description_md"] or "",
            status=d["status"],
            lifecycle_status=d["lifecycle_status"] or "",
            source_system=d["source_system"] or "",
            source_ref=d["source_ref"] or "",
            external_ids=_loads(d["external_ids"]),
            attrs=_loads(d["attrs"]),
            origin=d["origin"] or "",
            version=int(d["_version"]),
            created_at=d["created_at"],
            created_by=d["created_by"] or "",
            updated_at=d["updated_at"],
            updated_by=d["updated_by"] or "",
            current_state=d.get("current_state") or "live",
            target_state=d.get("target_state") or "undecided",
            target_work_package=d.get("target_work_package") or "",
            target_note=d.get("target_note") or "",
        )

    def _element_values(self, e: Element) -> list[Any]:
        return [
            e.element_id,
            e.type_id,
            e.key or None,
            e.name,
            e.description_md or None,
            e.status,
            e.lifecycle_status or None,
            e.source_system or None,
            e.source_ref or None,
            _dumps(e.external_ids),
            _dumps(e.attrs),
            e.origin or None,
            e.version,
            e.created_at,
            e.created_by or None,
            e.updated_at,
            e.updated_by or None,
            e.current_state,
            e.target_state,
            e.target_work_package or None,
            e.target_note or None,
        ]

    def get_element(self, element_id: str) -> Element | None:
        rows = self._fetch_all(
            f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM {self._el()} AS el WHERE element_id = ?", [element_id]
        )
        if not rows:
            return None
        e = self._row_to_element(rows[0])
        e.links = self.get_links(element_id)
        return e

    def _where(
        self, text: str | None, type_id: str | list[str] | None, status: str | None
    ) -> tuple[str, list[Any]]:
        clauses, params = [], []
        for word in (text or "").split():  # every word must match somewhere
            like = f"%{word}%"
            clauses.append(
                "(name ILIKE ? OR key ILIKE ? OR element_id ILIKE ? OR description_md ILIKE ? OR attrs ILIKE ?)"
            )
            params += [like] * 5
        if type_id:
            ids = [type_id] if isinstance(type_id, str) else list(type_id)
            clauses.append(f"type_id IN ({self._marks(ids)})")
            params += ids
        if status:
            clauses.append("status = ?")
            params.append(status)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def find_elements(
        self, text=None, type_id=None, status=None, limit: int = 200, offset: int = 0
    ) -> list[Element]:
        where, params = self._where(text, type_id, status)
        rows = self._fetch_all(
            f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM {self._el()} AS el{where} ORDER BY name, element_id"
            + self._page(limit, offset),
            params,
        )
        return [self._row_to_element(r) for r in rows]

    def count_elements(self, type_id=None, text=None, status=None) -> int:
        where, params = self._where(text, type_id, status)
        return int(self._fetch_all(f"SELECT COUNT(*) FROM {self._el()} AS el{where}", params)[0][0])

    def linked_element_ids(self) -> list[str]:
        """Ids of the elements that carry at least one link, on the current branch."""
        branch = current_branch()
        if branch == MAIN:
            rows = self._fetch_all("SELECT DISTINCT element_id FROM element_link")
        else:
            rows = self._fetch_all(
                "SELECT DISTINCT element_id FROM element_link WHERE element_id NOT IN "
                "(SELECT element_id FROM branch_element WHERE branch_id = ?) "
                "UNION SELECT DISTINCT element_id FROM branch_link WHERE branch_id = ?",
                [branch, branch],
            )
        return [r[0] for r in rows]

    def count_by_type(self) -> dict[str, int]:
        return {
            t: int(n)
            for t, n in self._fetch_all(
                f"SELECT type_id, COUNT(*) FROM {self._el()} AS el GROUP BY type_id ORDER BY 2 DESC"
            )
        }

    def insert_element(self, element: Element, actor: str) -> Element:
        if self.get_element(element.element_id):
            raise ConflictError(f"element {element.element_id} already exists")
        now = _now()
        element.version = 1
        element.created_at, element.created_by, element.updated_at, element.updated_by = (
            now,
            actor,
            now,
            actor,
        )
        branch = current_branch()
        with self._lock:
            if branch == MAIN:
                self._insert_rows("element", [self._element_values(element)])
            else:
                self._write_branch_element(branch, element, base_version=0)
            self._log("element", element.element_id, "insert", actor, None, self._public(element), 1)
        return element

    def update_element(self, element: Element, actor: str, expected_version: int | None = None) -> Element:
        current = self.get_element(element.element_id)
        if current is None:
            raise NotFoundError(element.element_id)
        expected = expected_version if expected_version is not None else element.version
        if current.version != expected:
            raise ConflictError(
                # To the minute: the row's raw timestamp carries microseconds, which say
                # nothing to the person being refused.
                f"element {element.element_id} changed by {current.updated_by} at "
                f"{str(current.updated_at)[:16]} (version {current.version}, you had {expected})"
            )
        element.version = current.version + 1
        element.created_at, element.created_by = current.created_at, current.created_by
        element.updated_at, element.updated_by = _now(), actor
        branch = current_branch()
        with self._lock:
            if branch == MAIN:
                self._execute(
                    "UPDATE element SET type_id=?, key=?, name=?, description_md=?, status=?, lifecycle_status=?, source_system=?, "
                    "source_ref=?, external_ids=?, attrs=?, origin=?, _version=?, updated_at=?, updated_by=?, "
                    "current_state=?, target_state=?, target_work_package=?, target_note=? WHERE element_id=? AND _version=?",
                    [
                        element.type_id,
                        element.key or None,
                        element.name,
                        element.description_md or None,
                        element.status,
                        element.lifecycle_status or None,
                        element.source_system or None,
                        element.source_ref or None,
                        _dumps(element.external_ids),
                        _dumps(element.attrs),
                        element.origin or None,
                        element.version,
                        element.updated_at,
                        element.updated_by,
                        element.current_state,
                        element.target_state,
                        element.target_work_package or None,
                        element.target_note or None,
                        element.element_id,
                        current.version,
                    ],
                )
            else:
                existing = self._branch_element_row(branch, element.element_id)
                base = existing[0] if existing else (self._main_element_version(element.element_id) or 0)
                self._write_branch_element(branch, element, base_version=base)
            self._log(
                "element",
                element.element_id,
                "update",
                actor,
                self._public(current),
                self._public(element),
                element.version,
            )
        return element

    @staticmethod
    def _public(e: Element | Relationship) -> dict[str, Any]:
        d = dict(vars(e))
        d.pop("links", None)
        for k in ("created_at", "updated_at"):
            d[k] = str(d[k]) if d.get(k) else None
        return d

    def _existing_rows(self, source: str, key: str, ids: list[str]) -> dict[str, tuple]:
        """key -> (created_at, created_by, version) for the ids the current branch already holds."""
        out: dict[str, tuple] = {}
        for chunk in chunks(ids, self.IN_CHUNK):
            for row_id, created_at, created_by, version in self._fetch_all(
                f"SELECT {key}, created_at, created_by, _version FROM {source} AS x WHERE {key} IN ({self._marks(chunk)})",
                chunk,
            ):
                out[row_id] = (created_at, created_by, version)
        return out

    def _versions(self, table: str, key: str, column: str, ids: list[str], branch: str | None = None) -> dict:
        out: dict[str, int] = {}
        for chunk in chunks(ids, self.IN_CHUNK):
            where = f"{key} IN ({self._marks(chunk)})"
            params: list[Any] = list(chunk)
            if branch is not None:
                where = f"branch_id = ? AND {where}"
                params = [branch, *chunk]
            for row_id, v in self._fetch_all(f"SELECT {key}, {column} FROM {table} WHERE {where}", params):
                out[row_id] = int(v)
        return out

    def upsert_elements(self, elements: list[Element], actor: str) -> tuple[int, int]:
        if not elements:
            return 0, 0
        now = _now()
        branch = current_branch()
        ids = [e.element_id for e in elements]
        existing = self._existing_rows(self._el(), "element_id", ids)
        unchanged = self._unchanged_elements(elements, list(existing))
        rows = []
        for e in elements:
            if e.element_id in unchanged:
                continue
            if e.element_id in existing:
                created_at, created_by, version = existing[e.element_id]
                e.created_at, e.created_by, e.version = created_at, created_by, int(version) + 1
            else:
                e.created_at, e.created_by, e.version = now, actor, 1
            e.updated_at, e.updated_by = now, actor
            rows.append(self._element_values(e))
        inserted = len(elements) - len(existing)
        if not rows:
            return inserted, len(existing)
        elements = [e for e in elements if e.element_id not in unchanged]
        ids = [e.element_id for e in elements]
        with self._lock:
            if branch == MAIN:
                self._replace_rows("element", ELEMENT_COLUMNS, rows, ["element_id"])
            else:
                branch_rows = self._versions("branch_element", "element_id", "base_version", ids, branch)
                main_versions = self._versions("element", "element_id", "_version", ids)
                extra = [
                    [branch, branch_rows.get(e.element_id, main_versions.get(e.element_id, 0)), "upsert"]
                    for e in elements
                ]
                self._replace_rows(
                    "branch_element",
                    ELEMENT_COLUMNS + ["branch_id", "base_version", "op"],
                    [r + x for r, x in zip(rows, extra, strict=True)],
                    ["branch_id", "element_id"],
                )
                self._copy_main_links(branch, [eid for eid in main_versions if eid not in branch_rows])
            self._log(
                "import",
                actor,
                "upsert_elements",
                actor,
                None,
                {
                    "inserted": inserted,
                    "updated": len(existing) - len(unchanged),
                    "unchanged": len(unchanged),
                },
                None,
            )
        return inserted, len(existing)

    _AUDIT_FIELDS = ("version", "created_at", "created_by", "updated_at", "updated_by")

    def _unchanged_elements(self, elements: list[Element], existing_ids: list[str]) -> set[str]:
        """Ids of incoming elements identical to what the current branch already holds (audit fields aside)."""
        if not existing_ids:
            return set()
        current: dict[str, dict[str, Any]] = {}
        for chunk in chunks(existing_ids, self.IN_CHUNK):
            for row in self._fetch_all(
                f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM {self._el()} AS el WHERE element_id IN ({self._marks(chunk)})",
                chunk,
            ):
                e = self._row_to_element(row)
                current[e.element_id] = self._content(e)
        return {e.element_id for e in elements if current.get(e.element_id) == self._content(e)}

    def _unchanged_rels(self, rels: list[Relationship], existing_ids: list[str]) -> set[str]:
        if not existing_ids:
            return set()
        current: dict[str, dict[str, Any]] = {}
        for chunk in chunks(existing_ids, self.IN_CHUNK):
            for row in self._fetch_all(
                f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl WHERE relationship_id IN ({self._marks(chunk)})",
                chunk,
            ):
                r = self._row_to_rel(row)
                current[r.relationship_id] = self._content(r)
        return {r.relationship_id for r in rels if current.get(r.relationship_id) == self._content(r)}

    def _content(self, e: Element | Relationship) -> dict[str, Any]:
        d = self._public(e)
        for k in self._AUDIT_FIELDS:
            d.pop(k, None)
        return d

    def set_links(self, element_id: str, links: list[Link], actor: str) -> list[Link]:
        branch = current_branch()
        with self._lock:
            if branch == MAIN:
                table, extra = "element_link", []
                self._execute("DELETE FROM element_link WHERE element_id = ?", [element_id])
            else:
                if self._branch_element_row(branch, element_id) is None:
                    main = self.get_element(element_id)  # links alone still need the element on the branch
                    if main is None:
                        return []
                    if [(ln.url, ln.label or "") for ln in links] == [
                        (ln.url, ln.label or "") for ln in self._main_links(element_id)
                    ]:
                        return self._main_links(element_id)  # nothing changes: nothing lands on the branch
                    self._write_branch_element(branch, main, base_version=main.version)
                table, extra = "branch_link", [branch]
                self._execute(
                    "DELETE FROM branch_link WHERE branch_id = ? AND element_id = ?", [branch, element_id]
                )
            out, rows = [], []
            for i, ln in enumerate(links):
                ln.link_id = ln.link_id or new_id("lnk")
                ln.element_id, ln.sort_order = element_id, i
                rows.append([ln.link_id, element_id, ln.url, ln.label or None, i] + extra)
                out.append(ln)
            self._insert_rows(table, rows)
        return out

    def get_links(self, element_id: str) -> list[Link]:
        branch = current_branch()
        if branch != MAIN and self._branch_element_row(branch, element_id) is not None:
            rows = self._fetch_all(
                "SELECT link_id, url, label, sort_order FROM branch_link WHERE branch_id = ? AND element_id = ? ORDER BY sort_order",
                [branch, element_id],
            )
        else:
            rows = self._fetch_all(
                "SELECT link_id, url, label, sort_order FROM element_link WHERE element_id = ? ORDER BY sort_order",
                [element_id],
            )
        return [
            Link(element_id=element_id, url=u, label=lb or "", link_id=lid, sort_order=so)
            for lid, u, lb, so in rows
        ]

    # ------------------------------------------------------ relationships
    @staticmethod
    def _row_to_rel(row: tuple) -> Relationship:
        d = dict(zip(RELATIONSHIP_COLUMNS, row, strict=True))
        return Relationship(
            relationship_id=d["relationship_id"],
            rel_type_id=d["rel_type_id"],
            src_id=d["src_id"],
            dst_id=d["dst_id"],
            qualifier=d["qualifier"] or "",
            attrs=_loads(d["attrs"]),
            status=d["status"],
            origin=d["origin"] or "",
            source_system=d["source_system"] or "",
            source_ref=d["source_ref"] or "",
            version=int(d["_version"]),
            created_at=d["created_at"],
            created_by=d["created_by"] or "",
            updated_at=d["updated_at"],
            updated_by=d["updated_by"] or "",
            current_state=d.get("current_state") or "live",
            target_state=d.get("target_state") or "undecided",
            target_work_package=d.get("target_work_package") or "",
            target_note=d.get("target_note") or "",
        )

    @staticmethod
    def _rel_values(r: Relationship) -> list[Any]:
        return [
            r.relationship_id,
            r.rel_type_id,
            r.src_id,
            r.dst_id,
            r.qualifier or None,
            _dumps(r.attrs),
            r.status,
            r.origin or None,
            r.source_system or None,
            r.source_ref or None,
            r.version,
            r.created_at,
            r.created_by or None,
            r.updated_at,
            r.updated_by or None,
            r.current_state,
            r.target_state,
            r.target_work_package or None,
            r.target_note or None,
        ]

    def get_relationship(self, relationship_id: str) -> Relationship | None:
        rows = self._fetch_all(
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl WHERE relationship_id = ?",
            [relationship_id],
        )
        return self._row_to_rel(rows[0]) if rows else None

    def relationships_of(self, element_id: str, direction: str = "both") -> list[Relationship]:
        cond = {"out": "src_id = ?", "in": "dst_id = ?", "both": "(src_id = ? OR dst_id = ?)"}[direction]
        params = [element_id] if direction != "both" else [element_id, element_id]
        rows = self._fetch_all(
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl WHERE {cond} AND status <> 'retired' ORDER BY rel_type_id, src_id, dst_id",
            params,
        )
        return [self._row_to_rel(r) for r in rows]

    def find_relationships(self, rel_type_id: str | None = None, limit: int = 500) -> list[Relationship]:
        where = " WHERE rel_type_id = ?" if rel_type_id else ""
        rows = self._fetch_all(
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl{where} ORDER BY rel_type_id, src_id, dst_id"
            + self._page(limit),
            [rel_type_id] if rel_type_id else [],
        )
        return [self._row_to_rel(r) for r in rows]

    def count_relationships(self, rel_type_id: str | None = None) -> int:
        where = " WHERE rel_type_id = ?" if rel_type_id else ""
        return int(
            self._fetch_all(
                f"SELECT COUNT(*) FROM {self._rel()} AS rl{where}", [rel_type_id] if rel_type_id else []
            )[0][0]
        )

    def count_by_rel_type(self) -> dict[str, int]:
        return {
            t: int(n)
            for t, n in self._fetch_all(
                f"SELECT rel_type_id, COUNT(*) FROM {self._rel()} AS rl GROUP BY rel_type_id ORDER BY 2 DESC"
            )
        }

    def insert_relationship(self, rel: Relationship, actor: str) -> Relationship:
        if self.get_relationship(rel.relationship_id):
            raise ConflictError(f"relationship {rel.relationship_id} already exists")
        now = _now()
        rel.version = 1
        rel.created_at, rel.created_by, rel.updated_at, rel.updated_by = now, actor, now, actor
        branch = current_branch()
        with self._lock:
            if branch == MAIN:
                self._insert_rows("relationship", [self._rel_values(rel)])
            else:
                self._write_branch_rel(branch, rel, base_version=0)
            self._log("relationship", rel.relationship_id, "insert", actor, None, self._public(rel), 1)
        return rel

    def update_relationship(
        self, rel: Relationship, actor: str, expected_version: int | None = None
    ) -> Relationship:
        current = self.get_relationship(rel.relationship_id)
        if current is None:
            raise NotFoundError(rel.relationship_id, "relationship")
        expected = expected_version if expected_version is not None else rel.version
        if current.version != expected:
            raise ConflictError(
                f"relationship {rel.relationship_id} changed by {current.updated_by} at "
                f"{str(current.updated_at)[:16]}"
            )
        rel.version = current.version + 1
        rel.created_at, rel.created_by = current.created_at, current.created_by
        rel.updated_at, rel.updated_by = _now(), actor
        branch = current_branch()
        with self._lock:
            if branch == MAIN:
                self._execute(
                    "UPDATE relationship SET rel_type_id=?, src_id=?, dst_id=?, qualifier=?, attrs=?, status=?, origin=?, source_system=?, "
                    "source_ref=?, _version=?, updated_at=?, updated_by=?, current_state=?, target_state=?, target_work_package=?, target_note=? "
                    "WHERE relationship_id=? AND _version=?",
                    [
                        rel.rel_type_id,
                        rel.src_id,
                        rel.dst_id,
                        rel.qualifier or None,
                        _dumps(rel.attrs),
                        rel.status,
                        rel.origin or None,
                        rel.source_system or None,
                        rel.source_ref or None,
                        rel.version,
                        rel.updated_at,
                        rel.updated_by,
                        rel.current_state,
                        rel.target_state,
                        rel.target_work_package or None,
                        rel.target_note or None,
                        rel.relationship_id,
                        current.version,
                    ],
                )
            else:
                existing = self._branch_rel_row(branch, rel.relationship_id)
                base = existing[0] if existing else (self._main_rel_version(rel.relationship_id) or 0)
                self._write_branch_rel(branch, rel, base_version=base)
            self._log(
                "relationship",
                rel.relationship_id,
                "update",
                actor,
                self._public(current),
                self._public(rel),
                rel.version,
            )
        return rel

    def delete_relationship(self, relationship_id: str, actor: str) -> None:
        current = self.get_relationship(relationship_id)
        if current is None:
            raise NotFoundError(relationship_id, "relationship")
        branch = current_branch()
        with self._lock:
            if branch == MAIN:
                self._execute("DELETE FROM relationship WHERE relationship_id = ?", [relationship_id])
            else:
                main_version = self._main_rel_version(relationship_id)
                if main_version is None:  # only ever existed on the branch: just drop it
                    self._execute(
                        "DELETE FROM branch_relationship WHERE branch_id = ? AND relationship_id = ?",
                        [branch, relationship_id],
                    )
                else:
                    existing = self._branch_rel_row(branch, relationship_id)
                    self._write_branch_rel(
                        branch, current, existing[0] if existing else main_version, op="delete"
                    )
            self._log(
                "relationship", relationship_id, "delete", actor, self._public(current), None, current.version
            )

    def upsert_relationships(self, rels: list[Relationship], actor: str) -> tuple[int, int]:
        if not rels:
            return 0, 0
        now = _now()
        branch = current_branch()
        ids = [r.relationship_id for r in rels]
        existing = self._existing_rows(self._rel(), "relationship_id", ids)
        unchanged = self._unchanged_rels(rels, list(existing))
        rows = []
        for r in rels:
            if r.relationship_id in unchanged:
                continue
            if r.relationship_id in existing:
                created_at, created_by, version = existing[r.relationship_id]
                r.created_at, r.created_by, r.version = created_at, created_by, int(version) + 1
            else:
                r.created_at, r.created_by, r.version = now, actor, 1
            r.updated_at, r.updated_by = now, actor
            rows.append(self._rel_values(r))
        inserted = len(rels) - len(existing)
        if not rows:
            return inserted, len(existing)
        rels = [r for r in rels if r.relationship_id not in unchanged]
        ids = [r.relationship_id for r in rels]
        with self._lock:
            if branch == MAIN:
                self._replace_rows("relationship", RELATIONSHIP_COLUMNS, rows, ["relationship_id"])
            else:
                branch_rows = self._versions(
                    "branch_relationship", "relationship_id", "base_version", ids, branch
                )
                main_versions = self._versions("relationship", "relationship_id", "_version", ids)
                extra = [
                    [
                        branch,
                        branch_rows.get(r.relationship_id, main_versions.get(r.relationship_id, 0)),
                        "upsert",
                    ]
                    for r in rels
                ]
                self._replace_rows(
                    "branch_relationship",
                    RELATIONSHIP_COLUMNS + ["branch_id", "base_version", "op"],
                    [r + x for r, x in zip(rows, extra, strict=True)],
                    ["branch_id", "relationship_id"],
                )
            self._log(
                "import",
                actor,
                "upsert_relationships",
                actor,
                None,
                {
                    "inserted": inserted,
                    "updated": len(existing) - len(unchanged),
                    "unchanged": len(unchanged),
                },
                None,
            )
        return inserted, len(existing)

    # -------------------------------------------------------------- graph
    def _trace_sql(self, direction: str) -> str:
        template = TRACE_OUT_SQL if direction == "out" else TRACE_IN_SQL
        return template.replace("{rel}", self._rel()).replace("{string}", self.STRING_TYPE)

    def _trace_frame(self, element_id: str, direction: str, max_depth: int) -> pd.DataFrame:
        """The reachable nodes with depth, node path and relationship-type path, as the engine computes them."""
        return self._fetch_df(self._trace_sql(direction), [element_id, element_id, element_id, max_depth])

    def _trace_in_process(self, element_id: str, direction: str, max_depth: int) -> pd.DataFrame:
        """The same walk as the recursive query, done here over the edges of the current branch.

        Breadth first, so the first arrival at a node is at its least depth; neighbours are taken
        in identifier order so the path recorded for a tie is the same on every run.
        """
        adjacent: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in self.edges_frame().itertuples(index=False):
            if direction == "out":
                adjacent[row.src_id].append((row.dst_id, row.rel_type_id))
            else:
                adjacent[row.dst_id].append((row.src_id, row.rel_type_id))
        sep = ">" if direction == "out" else "<"
        seen = {element_id}
        frontier: list[tuple[str, str, str]] = [(element_id, element_id, "")]
        out: list[tuple[str, int, str, str]] = []
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            next_frontier: list[tuple[str, str, str]] = []
            for node, path, rel_path in frontier:
                for neighbour, rel_type in sorted(adjacent.get(node, [])):
                    if neighbour in seen:
                        continue
                    seen.add(neighbour)
                    new_path = f"{path}{sep}{neighbour}"
                    new_rel_path = rel_type if not rel_path else f"{rel_path}{sep}{rel_type}"
                    out.append((neighbour, depth, new_path, new_rel_path))
                    next_frontier.append((neighbour, new_path, new_rel_path))
            frontier = next_frontier
        out.sort(key=lambda r: (r[1], r[0]))
        return pd.DataFrame(out, columns=["node_id", "depth", "path", "rel_path"])

    def trace(self, element_id: str, direction: str = "out", max_depth: int = 5) -> list[dict[str, Any]]:
        df = self._trace_frame(element_id, direction, max_depth)
        sep = ">" if direction == "out" else "<"
        out = []
        for row in df.itertuples(index=False):
            out.append(
                {
                    "element_id": row.node_id,
                    "depth": int(row.depth),
                    "path": row.path.split(sep),
                    "rel_path": row.rel_path.split(sep) if row.rel_path else [],
                    "direction": direction,
                }
            )
        return out

    def edges_frame(self) -> pd.DataFrame:
        return self._fetch_df(
            f"SELECT src_id, dst_id, rel_type_id, qualifier, relationship_id, target_state FROM {self._rel()} AS rl WHERE status <> 'retired'"
        )

    # -------------------------------------------------------------- audit
    def history(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where = " WHERE entity_id = ?" if entity_id else ""
        df = self._fetch_df(
            f"SELECT change_id, entity_kind, entity_id, op, actor, changed_at, before_json, after_json, version, branch_id FROM change_log{where} ORDER BY changed_at DESC"
            + self._page(limit),
            [entity_id] if entity_id else [],
        )
        return df.to_dict("records")

    # ------------------------------------------------------------ branches
    @staticmethod
    def _row_to_branch(row: tuple) -> Branch:
        return Branch(
            branch_id=row[0],
            name=row[1],
            description=row[2] or "",
            work_package=row[3] or "",
            status=row[4],
            created_by=row[5] or "",
            created_at=row[6],
            closed_by=row[7] or "",
            closed_at=row[8],
        )

    _BRANCH_COLS = (
        "branch_id, name, description, work_package, status, created_by, created_at, closed_by, closed_at"
    )

    def create_branch(self, branch: Branch, actor: str) -> Branch:
        validate_branch_id(branch.branch_id)
        if branch.branch_id == MAIN or self.get_branch(branch.branch_id) is not None:
            raise ConflictError(f"branch {branch.branch_id} already exists")
        branch.status, branch.created_by, branch.created_at = "open", actor, _now()
        with self._lock:
            self._insert_rows(
                "branch",
                [
                    [
                        branch.branch_id,
                        branch.name,
                        branch.description or None,
                        branch.work_package or None,
                        branch.status,
                        actor,
                        branch.created_at,
                        None,
                        None,
                    ]
                ],
            )
            self._log("branch", branch.branch_id, "create", actor, None, {"name": branch.name}, None, MAIN)
        return branch

    def get_branch(self, branch_id: str) -> Branch | None:
        rows = self._fetch_all(f"SELECT {self._BRANCH_COLS} FROM branch WHERE branch_id = ?", [branch_id])
        if not rows:
            return None
        b = self._row_to_branch(rows[0])
        b.changes = self._branch_row_count(branch_id)
        return b

    def list_branches(self, status: str | None = None) -> list[Branch]:
        where = " WHERE status = ?" if status else ""
        rows = self._fetch_all(
            f"SELECT {self._BRANCH_COLS} FROM branch{where} ORDER BY created_at DESC",
            [status] if status else [],
        )
        out = []
        for r in rows:
            b = self._row_to_branch(r)
            b.changes = self._branch_row_count(b.branch_id)
            out.append(b)
        return out

    def _branch_row_count(self, branch_id: str) -> int:
        n1 = self._fetch_all("SELECT COUNT(*) FROM branch_element WHERE branch_id = ?", [branch_id])[0][0]
        n2 = self._fetch_all("SELECT COUNT(*) FROM branch_relationship WHERE branch_id = ?", [branch_id])[0][
            0
        ]
        return int(n1) + int(n2)

    def _close_branch(self, branch_id: str, status: str, actor: str) -> None:
        self._execute(
            "UPDATE branch SET status = ?, closed_by = ?, closed_at = ? WHERE branch_id = ?",
            [status, actor, _now(), branch_id],
        )

    @staticmethod
    def _changed_fields(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[str]:
        if not before or not after:
            return []
        skip = {"version", "created_at", "created_by", "updated_at", "updated_by"}
        return sorted(k for k in after if k not in skip and before.get(k) != after.get(k))

    def _main_elements(self, ids: list[str]) -> dict[str, Element]:
        out: dict[str, Element] = {}
        for chunk in chunks(ids, self.IN_CHUNK):
            for row in self._fetch_all(
                f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM element WHERE element_id IN ({self._marks(chunk)})",
                chunk,
            ):
                e = self._row_to_element(row)
                out[e.element_id] = e
        return out

    def _main_rels(self, ids: list[str]) -> dict[str, Relationship]:
        out: dict[str, Relationship] = {}
        for chunk in chunks(ids, self.IN_CHUNK):
            for row in self._fetch_all(
                f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM relationship WHERE relationship_id IN ({self._marks(chunk)})",
                chunk,
            ):
                r = self._row_to_rel(row)
                out[r.relationship_id] = r
        return out

    def _links_of(self, ids: list[str], branch_id: str | None = None) -> dict[str, list[Link]]:
        """The links of many elements at once: main's, or a branch's overlay rows."""
        out: dict[str, list[Link]] = defaultdict(list)
        for chunk in chunks(ids, self.IN_CHUNK):
            if branch_id is None:
                sql = f"SELECT element_id, link_id, url, label, sort_order FROM element_link WHERE element_id IN ({self._marks(chunk)}) ORDER BY element_id, sort_order"
                params: list[Any] = list(chunk)
            else:
                sql = f"SELECT element_id, link_id, url, label, sort_order FROM branch_link WHERE branch_id = ? AND element_id IN ({self._marks(chunk)}) ORDER BY element_id, sort_order"
                params = [branch_id, *chunk]
            for eid, lid, u, lb, so in self._fetch_all(sql, params):
                out[eid].append(Link(element_id=eid, url=u, label=lb or "", link_id=lid, sort_order=so))
        return out

    def diff_branch(self, branch_id: str) -> ChangeSet:
        """The branch's rows against `main` today, with a conflict wherever `main` moved since the base version."""
        branch = self.get_branch(branch_id)
        if branch is None:
            raise NotFoundError(branch_id, "branch")
        items: list[ChangeItem] = []
        element_rows = self._fetch_all(
            f"SELECT {', '.join(ELEMENT_COLUMNS)}, base_version, op FROM branch_element WHERE branch_id = ? ORDER BY element_id",
            [branch_id],
        )
        element_ids = [row[0] for row in element_rows]
        mains = self._main_elements(element_ids)
        main_links = self._links_of(element_ids)
        branch_links = self._links_of(element_ids, branch_id)
        for row in element_rows:
            e = self._row_to_element(row[: len(ELEMENT_COLUMNS)])
            base, op = int(row[-2]), row[-1]
            main = mains.get(e.element_id)
            before = self._public(main) if main else None
            after = self._public(e) if op == "upsert" else None
            if main is None:
                change = "added"
            elif op == "delete":
                change = "deleted"
            else:
                change = "changed"
            if before is not None:
                before["links"] = [ln.url for ln in main_links.get(e.element_id, [])]
            if after is not None:
                after["links"] = [ln.url for ln in branch_links.get(e.element_id, [])]
            items.append(
                ChangeItem(
                    kind="element",
                    entity_id=e.element_id,
                    label=e.name,
                    change=change,
                    base_version=base,
                    main_version=main.version if main else None,
                    conflict=main is not None and main.version != base,
                    before=before,
                    after=after,
                    fields_changed=self._changed_fields(before, after),
                )
            )
        rel_rows = self._fetch_all(
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)}, base_version, op FROM branch_relationship WHERE branch_id = ? ORDER BY relationship_id",
            [branch_id],
        )
        main_rels = self._main_rels([row[0] for row in rel_rows])
        for row in rel_rows:
            r = self._row_to_rel(row[: len(RELATIONSHIP_COLUMNS)])
            base, op = int(row[-2]), row[-1]
            main = main_rels.get(r.relationship_id)
            before = self._public(main) if main else None
            after = self._public(r) if op == "upsert" else None
            change = "added" if main is None else ("deleted" if op == "delete" else "changed")
            items.append(
                ChangeItem(
                    kind="relationship",
                    entity_id=r.relationship_id,
                    label=f"{r.src_id} {r.rel_type_id.split('__')[1].replace('_', ' ') if '__' in r.rel_type_id else r.rel_type_id} {r.dst_id}",
                    change=change,
                    base_version=base,
                    main_version=main.version if main else None,
                    conflict=main is not None and main.version != base,
                    before=before,
                    after=after,
                    fields_changed=self._changed_fields(before, after),
                )
            )
        return ChangeSet(branch=branch, items=items)

    def _main_links(self, element_id: str) -> list[Link]:
        return self._links_of([element_id]).get(element_id, [])

    def _branch_links(self, branch_id: str, element_id: str) -> list[Link]:
        return self._links_of([element_id], branch_id).get(element_id, [])

    def merge_branch(
        self,
        branch_id: str,
        actor: str,
        include: set[str] | None = None,
        resolutions: dict[str, str] | None = None,
    ) -> MergeResult:
        """Apply the branch's rows to `main`, item by item.

        `include` names the item keys (`element:<id>`, `relationship:<id>`) to merge now; None
        means every item. A conflicting item is applied only when `resolutions[key] == "branch"`;
        with "main" it is dropped from the branch; otherwise it stays on the branch. Applied and
        dropped rows leave the branch; the branch closes when nothing remains.
        """
        change_set = self.diff_branch(branch_id)
        if change_set.branch.status not in OPEN_STATUSES:
            raise ConflictError(f"branch {branch_id} is {change_set.branch.status}")
        resolutions = resolutions or {}
        result = MergeResult(branch_id=branch_id)
        now = _now()
        with self._lock:
            # relationships that are deleted go first, elements next, relationships added or changed last,
            # so an added relationship always finds its ends on main
            ordered = (
                [i for i in change_set.items if i.kind == "relationship" and i.change == "deleted"]
                + [i for i in change_set.items if i.kind == "element"]
                + [i for i in change_set.items if i.kind == "relationship" and i.change != "deleted"]
            )
            for item in ordered:
                if include is not None and item.key not in include:
                    continue
                if item.conflict:
                    choice = resolutions.get(item.key)
                    if choice == "main":
                        self._drop_branch_row(branch_id, item)
                        result.dropped.append(item.key)
                        continue
                    if choice != "branch":
                        continue  # unresolved: stays on the branch
                self._apply_item(branch_id, item, actor, now)
                self._drop_branch_row(branch_id, item)
                result.applied.append(item.key)
            result.remaining = self._branch_row_count(branch_id)
            if result.remaining == 0:
                self._close_branch(branch_id, "merged", actor)
                result.closed = True
            self._log(
                "branch",
                branch_id,
                "merge",
                actor,
                None,
                {"applied": result.applied, "dropped": result.dropped, "remaining": result.remaining},
                None,
                MAIN,
            )
        return result

    def _apply_item(self, branch_id: str, item: ChangeItem, actor: str, now: datetime) -> None:
        origin_log = f"branch:{branch_id}"
        if item.kind == "element":
            rows = self._fetch_all(
                f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM branch_element WHERE branch_id = ? AND element_id = ?",
                [branch_id, item.entity_id],
            )
            if item.change == "deleted":
                self._execute("DELETE FROM element WHERE element_id = ?", [item.entity_id])
                self._execute("DELETE FROM element_link WHERE element_id = ?", [item.entity_id])
                self._log(
                    "element",
                    item.entity_id,
                    "delete",
                    actor,
                    item.before,
                    None,
                    item.main_version,
                    origin_log,
                )
                return
            e = self._row_to_element(rows[0])
            e.version = (item.main_version or 0) + 1
            e.updated_at, e.updated_by = now, actor
            if item.main_version is None:
                e.created_at, e.created_by = e.created_at or now, e.created_by or actor
            self._execute("DELETE FROM element WHERE element_id = ?", [item.entity_id])
            self._insert_rows("element", [self._element_values(e)])
            self._execute("DELETE FROM element_link WHERE element_id = ?", [item.entity_id])
            self._insert_rows(
                "element_link",
                [
                    [ln.link_id, item.entity_id, ln.url, ln.label or None, ln.sort_order]
                    for ln in self._branch_links(branch_id, item.entity_id)
                ],
            )
            self._log(
                "element",
                item.entity_id,
                "insert" if item.main_version is None else "update",
                actor,
                item.before,
                self._public(e),
                e.version,
                origin_log,
            )
        else:
            rows = self._fetch_all(
                f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM branch_relationship WHERE branch_id = ? AND relationship_id = ?",
                [branch_id, item.entity_id],
            )
            if item.change == "deleted":
                self._execute("DELETE FROM relationship WHERE relationship_id = ?", [item.entity_id])
                self._log(
                    "relationship",
                    item.entity_id,
                    "delete",
                    actor,
                    item.before,
                    None,
                    item.main_version,
                    origin_log,
                )
                return
            r = self._row_to_rel(rows[0])
            r.version = (item.main_version or 0) + 1
            r.updated_at, r.updated_by = now, actor
            self._execute("DELETE FROM relationship WHERE relationship_id = ?", [item.entity_id])
            self._insert_rows("relationship", [self._rel_values(r)])
            self._log(
                "relationship",
                item.entity_id,
                "insert" if item.main_version is None else "update",
                actor,
                item.before,
                self._public(r),
                r.version,
                origin_log,
            )

    def _drop_branch_row(self, branch_id: str, item: ChangeItem) -> None:
        if item.kind == "element":
            self._execute(
                "DELETE FROM branch_element WHERE branch_id = ? AND element_id = ?",
                [branch_id, item.entity_id],
            )
            self._execute(
                "DELETE FROM branch_link WHERE branch_id = ? AND element_id = ?", [branch_id, item.entity_id]
            )
        else:
            self._execute(
                "DELETE FROM branch_relationship WHERE branch_id = ? AND relationship_id = ?",
                [branch_id, item.entity_id],
            )

    def abandon_branch(self, branch_id: str, actor: str) -> Branch:
        branch = self.get_branch(branch_id)
        if branch is None:
            raise NotFoundError(branch_id, "branch")
        with self._lock:
            for table in ("branch_element", "branch_relationship", "branch_link"):
                self._execute(f"DELETE FROM {table} WHERE branch_id = ?", [branch_id])
            self._close_branch(branch_id, "abandoned", actor)
            self._log("branch", branch_id, "abandon", actor, None, None, None, MAIN)
        return self.get_branch(branch_id)  # type: ignore[return-value]

    def set_branch_status(self, branch_id: str, status: str, actor: str) -> Branch:
        if self.get_branch(branch_id) is None:
            raise NotFoundError(branch_id, "branch")
        with self._lock:
            if status in ("merged", "abandoned"):
                self._close_branch(branch_id, status, actor)
            else:
                self._execute(
                    "UPDATE branch SET status = ?, closed_by = NULL, closed_at = NULL WHERE branch_id = ?",
                    [status, branch_id],
                )
            self._log("branch", branch_id, f"status:{status}", actor, None, {"status": status}, None, MAIN)
        return self.get_branch(branch_id)  # type: ignore[return-value]

    # ------------------------------------------------------------- reviews
    def add_review(self, review: Review) -> Review:
        review.review_id = review.review_id or new_id("rev")
        review.decided_at = review.decided_at or _now()
        with self._lock:
            self._insert_rows(
                "branch_review",
                [
                    [
                        review.review_id,
                        review.branch_id,
                        review.reviewer,
                        review.decision,
                        json.dumps(review.type_ids),
                        review.comment or None,
                        review.decided_at,
                    ]
                ],
            )
            self._log(
                "branch",
                review.branch_id,
                f"review:{review.decision}",
                review.reviewer,
                None,
                {"types": review.type_ids, "comment": review.comment},
                None,
                MAIN,
            )
        return review

    def list_reviews(self, branch_id: str) -> list[Review]:
        rows = self._fetch_all(
            "SELECT review_id, branch_id, reviewer, decision, type_ids, comment, decided_at FROM branch_review "
            "WHERE branch_id = ? ORDER BY decided_at",
            [branch_id],
        )
        return [
            Review(
                review_id=r[0],
                branch_id=r[1],
                reviewer=r[2],
                decision=r[3],
                type_ids=json.loads(r[4] or "[]"),
                comment=r[5] or "",
                decided_at=r[6],
            )
            for r in rows
        ]

    def list_reviewer_assignments(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for type_id, reviewer in self._fetch_all(
            "SELECT type_id, reviewer FROM reviewer_assignment ORDER BY type_id, reviewer"
        ):
            out.setdefault(type_id, []).append(reviewer)
        return out

    def set_reviewer_assignment(self, type_id: str, reviewers: list[str], actor: str) -> None:
        with self._lock:
            self._execute("DELETE FROM reviewer_assignment WHERE type_id = ?", [type_id])
            now = _now()
            self._insert_rows(
                "reviewer_assignment",
                [
                    [type_id, r, actor, now]
                    for r in dict.fromkeys(x.strip() for x in reviewers if x and x.strip())
                ],
            )
            self._log("reviewers", type_id, "assign", actor, None, {"reviewers": reviewers}, None, MAIN)

    # ----------------------------------------------------------- proposals
    def save_proposal(self, p: Proposal) -> Proposal:
        p.proposal_id = p.proposal_id or new_id("prp")
        p.created_at = p.created_at or _now()
        with self._lock:
            self._execute("DELETE FROM proposal WHERE proposal_id = ?", [p.proposal_id])
            self._insert_rows(
                "proposal",
                [
                    [
                        p.proposal_id,
                        p.branch_id,
                        p.title,
                        json.dumps(p.sources, ensure_ascii=False, default=str),
                        json.dumps(p.result, ensure_ascii=False, default=str),
                        json.dumps(p.pushback, ensure_ascii=False),
                        p.status,
                        p.created_by or None,
                        p.created_at,
                    ]
                ],
            )
        return p

    def list_proposals(self, branch_id: str | None = None) -> list[Proposal]:
        where = " WHERE branch_id = ?" if branch_id else ""
        rows = self._fetch_all(
            f"SELECT proposal_id, branch_id, title, sources_json, result_json, pushback_json, status, created_by, created_at FROM proposal{where} ORDER BY created_at DESC",
            [branch_id] if branch_id else [],
        )
        out = []
        for r in rows:
            out.append(
                Proposal(
                    proposal_id=r[0],
                    branch_id=r[1],
                    title=r[2] or "",
                    sources=json.loads(r[3] or "[]"),
                    result=json.loads(r[4] or "{}"),
                    pushback=json.loads(r[5] or "[]"),
                    status=r[6] or "",
                    created_by=r[7] or "",
                    created_at=r[8],
                )
            )
        return out

    # ---------------------------------------------------------------- sql
    def query(self, sql: str, params: list[Any] | None = None, limit: int = 1000) -> pd.DataFrame:
        stripped = re.sub(r"--[^\n]*", "", sql).strip().rstrip(";").strip()
        if ";" in stripped or not _READ_ONLY_RE.match(stripped) or _FORBIDDEN_RE.search(stripped):
            raise ValueError("only a single read-only SELECT/WITH statement is allowed")
        return self._fetch_df(f"SELECT * FROM ({stripped}) AS q LIMIT {int(limit)}", params)


__all__ = ["SqlBackend", "chunks", "new_id", "table_columns"]
