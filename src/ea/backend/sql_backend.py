"""The store on SQL, once: every read and write the engines share.

One schema, two engines (decision 0002). Everything the repository asks of a
SQL store — the overlay a branch lays over `main`, the optimistic concurrency,
the change log, the diff and the merge, the organisations every row belongs to
and the versions the metamodel is kept in — is written here against the
portable DDL of `sql.py`. An engine (`duckdb_backend.py`, `lakebase_backend.py`)
adds only what differs: how to connect, how to run a statement and how to land
many rows at once.

Every content row carries the organisation it belongs to (decision 0014). The
two element and relationship *sources* (`_el`, `_rel`) read only the current
organisation's rows, on `main` or through the branch overlay, so every query
built on them is scoped without saying so; every write and every direct table
read names the organisation itself.
"""

from __future__ import annotations

import json
import logging
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
from ea.backend.organisations import DEFAULT_ORG, current_org, validate_org_id
from ea.backend.sql import (
    DDL,
    ELEMENT_COLUMNS,
    INDEXES,
    META_TABLES,
    MIGRATIONS,
    ORG_TABLES,
    RELATIONSHIP_COLUMNS,
    TRACE_ENDS,
    TRACE_SQL,
    TRACE_SQL_BOTH,
    create_table_sql,
    index_sql,
    qualified,
    schema_of,
    schemas,
    table_columns,
)
from ea.metamodel.loader import pack_from_dict, pack_to_dict
from ea.models import (
    OPEN_STATUSES,
    PACK_STATUSES,
    Branch,
    ChangeItem,
    ChangeSet,
    ConflictError,
    Element,
    Link,
    MergeResult,
    NotFoundError,
    Organisation,
    Pack,
    PackVersion,
    Proposal,
    Relationship,
    Review,
    validate_identifier,
    validate_version,
)

_READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_WITH_RE = re.compile(r"^\s*with\s+(recursive\s+)?", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|attach|copy|export|import|pragma|call|"
    r"install|load|grant|revoke|vacuum|optimize|restore|refresh|msck)\b",
    re.IGNORECASE,
)
# The keys of an attribute definition kept in the `extra` JSON column of meta_attribute.
_ATTR_EXTRA = ("default", "multiple", "unit", "pattern", "min", "max", "group", "help", "properties")


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


def pack_content(pack: Pack) -> dict[str, Any]:
    """What a version defines, without its lifecycle: the part a frozen version must keep."""
    d = pack_to_dict(pack)
    d["pack"] = {k: v for k, v in d["pack"].items() if k not in ("status", "derived_from", "notes")}
    return d


log = logging.getLogger(__name__)


class SqlBackend(DatabaseBackend):
    """The repository contract on any SQL engine that runs the portable DDL.

    An engine implements the hooks in the first section; everything below them
    is shared, so the DuckDB suite is the acceptance suite of every engine.
    """

    #: how many identifiers one `IN (...)` list may carry (a parameter marker each)
    IN_CHUNK = 500

    def __init__(self, schema_prefix: str = "ea") -> None:
        self._lock = threading.RLock()
        #: the tables are grouped into `<prefix>_<group>` schemas; `EA_SCHEMA` names the prefix
        self.schema_prefix = schema_prefix

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

    def _create_schema(self, name: str) -> None:
        raise NotImplementedError

    def _set_search_path(self, names: list[str]) -> None:
        """So every other statement in this module can name a table without its schema."""
        raise NotImplementedError

    def _table_exists(self, schema: str, table: str) -> bool:
        raise NotImplementedError

    def _move_table(self, table: str, source: str, target: str) -> None:
        """Move a table, with its rows, from one schema to another."""
        raise NotImplementedError

    def _one_schema_store(self) -> str:
        """Where a store made before the tables were grouped keeps all of them."""
        raise NotImplementedError

    def _bind(self, values: list[Any]) -> tuple[list[str], list[Any]]:
        """Values the reader chose (search words, type filters) as SQL: markers and parameters here;
        an engine with a marker budget would render them as literals instead."""
        return ["?" for _ in values], list(values)

    def _add_missing_columns(self) -> None:
        """Bring a store created by an earlier version up to the DDL (the MIGRATIONS list)."""
        for table, column, dtype in MIGRATIONS:
            self._execute(
                f"ALTER TABLE {qualified(table, self.schema_prefix)} "
                f"ADD COLUMN IF NOT EXISTS {column} {dtype}"
            )

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
        org: str | None = None,
    ) -> None:
        self._execute(
            "INSERT INTO change_log (change_id, entity_kind, entity_id, op, actor, changed_at, "
            "before_json, after_json, version, branch_id, org_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                org or current_org(),
            ],
        )

    @staticmethod
    def _marks(items: Iterable[Any]) -> str:
        return ", ".join("?" for _ in items)

    @staticmethod
    def _page(limit: int, offset: int = 0) -> str:
        """LIMIT and OFFSET inline: integers the code chose, never the reader's text."""
        return f" LIMIT {int(limit)}" + (f" OFFSET {int(offset)}" if offset else "")

    # ------------------------------------------------------- organisation scope
    @staticmethod
    def _org() -> str:
        return current_org()

    @staticmethod
    def _qo(org: str | None = None) -> str:
        """The organisation id as a SQL literal; ids are validated so this is safe."""
        return "'" + validate_org_id(org or current_org()) + "'"

    # ------------------------------------------------------------ branch overlay
    @staticmethod
    def _q(branch: str) -> str:
        """A branch id as a SQL literal; ids are validated so this is safe."""
        return "'" + validate_branch_id(branch).replace("'", "''") + "'"

    def _el(self, branch: str | None = None) -> str:
        """The element source: the organisation's main, with the branch's overlay laid over it elsewhere."""
        b = branch or current_branch()
        o = self._qo()
        cols = ", ".join(ELEMENT_COLUMNS)
        if b == MAIN:
            return f"(SELECT {cols} FROM element WHERE org_id = {o})"
        return (
            f"(SELECT {cols} FROM element AS m WHERE m.org_id = {o} AND NOT EXISTS "
            f"(SELECT 1 FROM branch_element AS v WHERE v.org_id = {o} AND v.branch_id = {self._q(b)} "
            f"AND v.element_id = m.element_id) "
            f"UNION ALL SELECT {cols} FROM branch_element WHERE org_id = {o} AND branch_id = {self._q(b)} "
            f"AND op = 'upsert')"
        )

    def _rel(self, branch: str | None = None) -> str:
        b = branch or current_branch()
        o = self._qo()
        cols = ", ".join(RELATIONSHIP_COLUMNS)
        if b == MAIN:
            return f"(SELECT {cols} FROM relationship WHERE org_id = {o})"
        return (
            f"(SELECT {cols} FROM relationship AS m WHERE m.org_id = {o} AND NOT EXISTS "
            f"(SELECT 1 FROM branch_relationship AS v WHERE v.org_id = {o} AND v.branch_id = {self._q(b)} "
            f"AND v.relationship_id = m.relationship_id) "
            f"UNION ALL SELECT {cols} FROM branch_relationship WHERE org_id = {o} AND branch_id = {self._q(b)} "
            f"AND op = 'upsert')"
        )

    def _branch_element_row(self, branch: str, element_id: str) -> tuple[int, str] | None:
        rows = self._fetch_all(
            "SELECT base_version, op FROM branch_element WHERE org_id = ? AND branch_id = ? AND element_id = ?",
            [self._org(), branch, element_id],
        )
        return (int(rows[0][0]), rows[0][1]) if rows else None

    def _branch_rel_row(self, branch: str, relationship_id: str) -> tuple[int, str] | None:
        rows = self._fetch_all(
            "SELECT base_version, op FROM branch_relationship WHERE org_id = ? AND branch_id = ? AND relationship_id = ?",
            [self._org(), branch, relationship_id],
        )
        return (int(rows[0][0]), rows[0][1]) if rows else None

    def _main_element_version(self, element_id: str) -> int | None:
        rows = self._fetch_all(
            "SELECT _version FROM element WHERE org_id = ? AND element_id = ?", [self._org(), element_id]
        )
        return int(rows[0][0]) if rows else None

    def _main_rel_version(self, relationship_id: str) -> int | None:
        rows = self._fetch_all(
            "SELECT _version FROM relationship WHERE org_id = ? AND relationship_id = ?",
            [self._org(), relationship_id],
        )
        return int(rows[0][0]) if rows else None

    def _write_branch_element(self, branch: str, e: Element, base_version: int, op: str = "upsert") -> None:
        with self._lock:
            first_time = self._branch_element_row(branch, e.element_id) is None
            self._execute(
                "DELETE FROM branch_element WHERE org_id = ? AND branch_id = ? AND element_id = ?",
                [self._org(), branch, e.element_id],
            )
            self._insert_rows(
                "branch_element", [self._element_values(e) + [branch, base_version, op, self._org()]]
            )
            if first_time and base_version > 0:
                self._copy_main_links(branch, [e.element_id])

    def _copy_main_links(self, branch: str, element_ids: list[str]) -> None:
        """An element's links follow it onto the branch the first time it is written there, so a
        change to the element alone never reads as a change to its links."""
        org = self._org()
        for chunk in chunks(element_ids, self.IN_CHUNK):
            self._execute(
                f"INSERT INTO branch_link (link_id, element_id, url, label, sort_order, branch_id, org_id) "
                f"SELECT link_id, element_id, url, label, sort_order, ?, org_id "
                f"FROM element_link WHERE org_id = ? AND element_id IN ({self._marks(chunk)}) "
                f"AND element_id NOT IN (SELECT element_id FROM branch_link WHERE org_id = ? AND branch_id = ?)",
                [branch, org, *chunk, org, branch],
            )

    def _write_branch_rel(self, branch: str, r: Relationship, base_version: int, op: str = "upsert") -> None:
        with self._lock:
            self._execute(
                "DELETE FROM branch_relationship WHERE org_id = ? AND branch_id = ? AND relationship_id = ?",
                [self._org(), branch, r.relationship_id],
            )
            self._insert_rows(
                "branch_relationship", [self._rel_values(r) + [branch, base_version, op, self._org()]]
            )

    # ---------------------------------------------------------- lifecycle
    def init_schema(self) -> None:
        with self._lock:
            for schema in schemas(self.schema_prefix):
                self._create_schema(schema)
            self._set_search_path(schemas(self.schema_prefix))
            self._group_existing_tables()
            for table in DDL:
                self._create_table(create_table_sql(table, self.schema_prefix))
            self._add_missing_columns()
            self._migrate_organisations()
            self._create_indexes()

    def _group_existing_tables(self) -> None:
        """A store made before the tables were grouped keeps them all in one schema. Each moves,
        with its rows, to the schema of its group — before the DDL runs, because otherwise the
        DDL makes an empty table in the new place and leaves the rows behind in the old one."""
        home = self._one_schema_store()
        for table in DDL:
            target = schema_of(table, self.schema_prefix)
            if target == home or not self._table_exists(home, table) or self._table_exists(target, table):
                continue
            self._move_table(table, home, target)
            log.info("moved %s from %s to %s", table, home, target)

    def _create_indexes(self) -> None:
        """The indexes of `INDEXES`, each on its own: a store that already holds a duplicate
        refuses its unique index, and that is a thing to report rather than a store that
        will not open. The store enforced these keys in Python long before the database
        knew them, so a refusal names a row that was already wrong."""
        for name, table, unique, columns in INDEXES:
            try:
                self._execute(index_sql(name, table, unique, columns, self.schema_prefix))
            except Exception as exc:  # noqa: BLE001 - an engine raises its own type here
                log.warning("could not create the index %s (%s)", name, exc)

    def _migrate_organisations(self) -> None:
        """A store from before organisations and versions: its rows belong to the default
        organisation, its packs are one version each, and the default organisation applies
        the pack most recently loaded. On a store that already has them, nothing moves."""
        for table in ORG_TABLES:
            self._execute(f"UPDATE {table} SET org_id = ? WHERE org_id IS NULL", [DEFAULT_ORG])
        self._execute("UPDATE meta_pack SET version = '1' WHERE version IS NULL OR version = ''")
        self._execute("UPDATE meta_pack SET status = 'draft' WHERE status IS NULL OR status = ''")
        for table in META_TABLES[1:]:
            self._execute(
                f"UPDATE {table} SET pack_version = (SELECT p.version FROM meta_pack p WHERE p.pack_id = {table}.pack_id) "
                f"WHERE pack_version IS NULL"
            )
        self._execute("UPDATE meta_element_type SET abstract = FALSE WHERE abstract IS NULL")
        if not self._fetch_all("SELECT org_id FROM organisation"):
            packs = self._fetch_all("SELECT pack_id, version FROM meta_pack ORDER BY loaded_at DESC")
            if packs:
                pack_id, version = packs[0]
                self._insert_rows(
                    "organisation",
                    [
                        [
                            DEFAULT_ORG,
                            "Default organisation",
                            None,
                            pack_id,
                            version,
                            True,
                            None,
                            "migration",
                            _now(),
                            _now(),
                        ]
                    ],
                )

    # ---------------------------------------------------------- metamodel
    def _pack_rows(self, pack: Pack) -> dict[str, list[list[Any]]]:
        """Every meta_* row of one version, positionally, in the tables' column order."""

        def keep(k: str, v: Any) -> bool:
            """What the extra JSON carries: a zero and a False are values, an empty one is not."""
            if v is None or (isinstance(v, (str, dict)) and not v):
                return False
            return not (k == "multiple" and v is False)

        def attr_row(a, type_id: str | None, rel_type_id: str | None, i: int) -> list[Any]:
            extra = {k: getattr(a, k) for k in _ATTR_EXTRA if keep(k, getattr(a, k))}
            return [
                pack.id,
                type_id,
                a.name,
                a.label,
                a.type,
                a.required,
                json.dumps(a.enum) if a.enum else None,
                a.description,
                a.sensitivity,
                i,
                pack.version,
                rel_type_id,
                json.dumps(extra, ensure_ascii=False, default=str) if extra else None,
            ]

        attribute_rows = [attr_row(a, None, None, i) for i, a in enumerate(pack.common_attributes)]
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
                    pack.version,
                    t.abstract,
                    json.dumps(t.properties, ensure_ascii=False, default=str) if t.properties else None,
                ]
            )
            attribute_rows += [attr_row(a, t.id, None, i) for i, a in enumerate(t.attributes)]
        rel_rows = []
        for r in pack.relationship_types:
            rel_rows.append(
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
                    pack.version,
                    json.dumps(r.properties, ensure_ascii=False, default=str) if r.properties else None,
                ]
            )
            attribute_rows += [attr_row(a, None, r.id, i) for i, a in enumerate(r.attributes)]
        domain_rows = [
            [
                pack.id,
                d.id,
                d.name,
                d.description,
                d.sort_order,
                json.dumps(d.notation),
                pack.version,
                json.dumps(d.properties, ensure_ascii=False, default=str) if d.properties else None,
            ]
            for d in pack.domains
        ]
        group_rows = [
            [
                pack.id,
                g.id,
                g.name,
                g.description,
                g.sort_order,
                pack.version,
                json.dumps(g.properties, ensure_ascii=False, default=str) if g.properties else None,
            ]
            for g in pack.attribute_groups
        ]
        return {
            "meta_domain": domain_rows,
            "meta_attribute_group": group_rows,
            "meta_element_type": type_rows,
            "meta_attribute": attribute_rows,
            "meta_relationship_type": rel_rows,
        }

    def _pack_header(self, pack_id: str, version: str) -> tuple | None:
        rows = self._fetch_all(
            "SELECT pack_id, version, status, created_by, created_at, published_by, published_at, loaded_at, name, "
            "derived_from, notes FROM meta_pack WHERE pack_id = ? AND version = ?",
            [pack_id, version],
        )
        return rows[0] if rows else None

    def save_pack(self, pack: Pack, actor: str = "") -> None:
        validate_identifier(pack.id, "pack id")
        validate_version(pack.version, "pack version")
        now = _now()
        with self._lock:
            header = self._pack_header(pack.id, pack.version)
            created_by, created_at, published_by, published_at = actor or None, now, None, None
            if header is not None:
                _, _, status, created_by, created_at, published_by, published_at, *_ = header
                if status in ("published", "retired"):
                    stored = self.load_pack(pack.id, pack.version)
                    if stored is not None and pack_content(stored) == pack_content(pack):
                        return  # the same definition again: nothing to store
                    raise ConflictError(
                        f"version {pack.version} of pack {pack.id} is {status} and frozen; "
                        "load the definition under another version, or start a draft from it"
                    )
            if pack.status == "published" and not published_at:
                published_by, published_at = actor or None, now
            rows = self._pack_rows(pack)
            for t in META_TABLES:
                self._execute(
                    f"DELETE FROM {t} WHERE pack_id = ? AND version = ?"
                    if t == "meta_pack"
                    else f"DELETE FROM {t} WHERE pack_id = ? AND pack_version = ?",
                    [pack.id, pack.version],
                )
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
                        now,
                        pack.status,
                        pack.derived_from or None,
                        pack.notes or None,
                        json.dumps(pack.properties, ensure_ascii=False, default=str)
                        if pack.properties
                        else None,
                        created_by,
                        created_at,
                        published_by,
                        published_at,
                    ]
                ],
            )
            for table, table_rows in rows.items():
                self._insert_rows(table, table_rows)
            self._log(
                "metamodel",
                pack.ref,
                "save" if header is None else "replace",
                actor or "system",
                None,
                {
                    "status": pack.status,
                    "types": len(pack.element_types),
                    "relationship_types": len(pack.relationship_types),
                },
                None,
                MAIN,
            )

    def load_pack(self, pack_id: str, version: str | None = None) -> Pack | None:
        if version is None:
            rows = self._fetch_all(
                "SELECT version FROM meta_pack WHERE pack_id = ? ORDER BY loaded_at DESC", [pack_id]
            )
            if not rows:
                return None
            version = rows[0][0]
        rows = self._fetch_all(
            "SELECT pack_id, name, version, description, source, provenance_values, status, derived_from, notes, properties "
            "FROM meta_pack WHERE pack_id = ? AND version = ?",
            [pack_id, version],
        )
        if not rows:
            return None
        pid, name, version, description, source, prov, status, derived_from, notes, properties = rows[0]
        domains = [
            {
                "id": d,
                "name": n,
                "description": desc,
                "notation": json.loads(notation or "{}"),
                "properties": _loads(props),
            }
            for d, n, desc, notation, props in self._fetch_all(
                "SELECT domain_id, name, description, notation, properties FROM meta_domain "
                "WHERE pack_id = ? AND pack_version = ? ORDER BY sort_order",
                [pid, version],
            )
        ]
        attribute_groups = [
            {"id": g, "name": n, "description": desc or "", "properties": _loads(props)}
            for g, n, desc, props in self._fetch_all(
                "SELECT group_id, name, description, properties FROM meta_attribute_group "
                "WHERE pack_id = ? AND pack_version = ? ORDER BY sort_order",
                [pid, version],
            )
        ]
        attrs = self._fetch_all(
            "SELECT type_id, name, label, datatype, required, enum_values, description, sensitivity, rel_type_id, extra "
            "FROM meta_attribute WHERE pack_id = ? AND pack_version = ? ORDER BY sort_order",
            [pid, version],
        )

        def attr_dict(row: tuple) -> dict[str, Any]:
            _, aname, label, dtype, required, enum_values, adesc, sens, _, extra = row
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
            d.update(_loads(extra))
            return d

        common = [attr_dict(a) for a in attrs if a[0] is None and a[8] is None]
        element_types = []
        for row in self._fetch_all(
            "SELECT type_id, name, plural, supertype_id, active, deactivation_reason, domain_id, provenance, prefix, "
            "description, examples, source_of_record, type_owner, instance_owner, notation, abstract, properties "
            "FROM meta_element_type WHERE pack_id = ? AND pack_version = ? ORDER BY sort_order",
            [pid, version],
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
                    "abstract": bool(row[15]),
                    "properties": _loads(row[16]),
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
                "properties": _loads(r[11]),
                "attributes": [attr_dict(a) for a in attrs if a[8] == r[0]],
            }
            for r in self._fetch_all(
                "SELECT rel_type_id, name, inverse_name, source_type_id, target_type_id, provenance, qualifiers, "
                "diagrams, description, src_max, dst_max, properties FROM meta_relationship_type "
                "WHERE pack_id = ? AND pack_version = ? ORDER BY sort_order",
                [pid, version],
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
                    "status": status or "draft",
                    "derived_from": derived_from or "",
                    "notes": notes or "",
                    "properties": _loads(properties),
                },
                "domains": domains,
                "attribute_groups": attribute_groups,
                "common_attributes": common,
                "element_types": element_types,
                "relationship_types": relationship_types,
            }
        )

    def list_pack_versions(self, pack_id: str | None = None) -> list[PackVersion]:
        where = " WHERE pack_id = ?" if pack_id else ""
        applied: dict[tuple[str, str], list[str]] = defaultdict(list)
        for org_id, pid, version in self._fetch_all(
            "SELECT org_id, pack_id, pack_version FROM organisation ORDER BY org_id"
        ):
            applied[(pid, version)].append(org_id)
        out = []
        for row in self._fetch_all(
            "SELECT pack_id, version, name, status, derived_from, notes, loaded_at, created_by, created_at, "
            f"published_by, published_at FROM meta_pack{where} ORDER BY loaded_at DESC",
            [pack_id] if pack_id else [],
        ):
            out.append(
                PackVersion(
                    pack_id=row[0],
                    version=row[1],
                    name=row[2] or "",
                    status=row[3] or "draft",
                    derived_from=row[4] or "",
                    notes=row[5] or "",
                    loaded_at=row[6],
                    created_by=row[7] or "",
                    created_at=row[8],
                    published_by=row[9] or "",
                    published_at=row[10],
                    applied_by=applied.get((row[0], row[1]), []),
                )
            )
        return out

    def set_pack_status(self, pack_id: str, version: str, status: str, actor: str) -> PackVersion:
        if status not in PACK_STATUSES:
            raise ValueError(f"status must be one of {PACK_STATUSES}")
        if self._pack_header(pack_id, version) is None:
            raise NotFoundError(f"{pack_id}@{version}", "metamodel version")
        with self._lock:
            if status == "published":
                self._execute(
                    "UPDATE meta_pack SET status = ?, published_by = ?, published_at = ? WHERE pack_id = ? AND version = ?",
                    [status, actor, _now(), pack_id, version],
                )
            else:
                self._execute(
                    "UPDATE meta_pack SET status = ? WHERE pack_id = ? AND version = ?",
                    [status, pack_id, version],
                )
            self._log(
                "metamodel",
                f"{pack_id}@{version}",
                f"status:{status}",
                actor,
                None,
                {"status": status},
                None,
                MAIN,
            )
        return next(v for v in self.list_pack_versions(pack_id) if v.version == version)

    def delete_pack_version(self, pack_id: str, version: str, actor: str) -> None:
        if self._pack_header(pack_id, version) is None:
            raise NotFoundError(f"{pack_id}@{version}", "metamodel version")
        with self._lock:
            self._execute("DELETE FROM meta_pack WHERE pack_id = ? AND version = ?", [pack_id, version])
            for t in META_TABLES[1:]:
                self._execute(f"DELETE FROM {t} WHERE pack_id = ? AND pack_version = ?", [pack_id, version])
            self._log("metamodel", f"{pack_id}@{version}", "delete", actor, None, None, None, MAIN)

    # ------------------------------------------------------- organisations
    _ORG_COLS = "org_id, name, description, pack_id, pack_version, is_default, copied_from, created_by, created_at, updated_at"

    @staticmethod
    def _row_to_org(row: tuple) -> Organisation:
        return Organisation(
            org_id=row[0],
            name=row[1],
            description=row[2] or "",
            pack_id=row[3] or "",
            pack_version=row[4] or "",
            is_default=bool(row[5]),
            copied_from=row[6] or "",
            created_by=row[7] or "",
            created_at=row[8],
            updated_at=row[9],
        )

    def _org_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = defaultdict(
            lambda: {"elements": 0, "relationships": 0, "branches": 0}
        )
        for org, n in self._fetch_all("SELECT org_id, COUNT(*) FROM element GROUP BY org_id"):
            out[org]["elements"] = int(n)
        for org, n in self._fetch_all("SELECT org_id, COUNT(*) FROM relationship GROUP BY org_id"):
            out[org]["relationships"] = int(n)
        for org, n in self._fetch_all(
            "SELECT org_id, COUNT(*) FROM branch WHERE status IN ('open', 'in_review', 'approved') GROUP BY org_id"
        ):
            out[org]["branches"] = int(n)
        return out

    def list_organisations(self) -> list[Organisation]:
        counts = self._org_counts()
        out = []
        for row in self._fetch_all(
            f"SELECT {self._ORG_COLS} FROM organisation ORDER BY is_default DESC, created_at, org_id"
        ):
            org = self._row_to_org(row)
            c = counts.get(org.org_id, {})
            org.elements, org.relationships, org.branches = (
                c.get("elements", 0),
                c.get("relationships", 0),
                c.get("branches", 0),
            )
            out.append(org)
        return out

    def get_organisation(self, org_id: str) -> Organisation | None:
        rows = self._fetch_all(f"SELECT {self._ORG_COLS} FROM organisation WHERE org_id = ?", [org_id])
        return self._row_to_org(rows[0]) if rows else None

    def default_organisation(self) -> Organisation | None:
        rows = self._fetch_all(
            f"SELECT {self._ORG_COLS} FROM organisation WHERE is_default ORDER BY created_at"
        )
        return self._row_to_org(rows[0]) if rows else None

    def save_organisation(self, org: Organisation, actor: str) -> Organisation:
        validate_org_id(org.org_id)
        now = _now()
        with self._lock:
            existing = self.get_organisation(org.org_id)
            org.created_by = existing.created_by if existing else (org.created_by or actor)
            org.created_at = existing.created_at if existing else (org.created_at or now)
            org.updated_at = now
            if org.is_default:
                self._execute("UPDATE organisation SET is_default = FALSE WHERE org_id <> ?", [org.org_id])
            self._replace_rows(
                "organisation",
                table_columns("organisation"),
                [
                    [
                        org.org_id,
                        org.name,
                        org.description or None,
                        org.pack_id or None,
                        org.pack_version or None,
                        bool(org.is_default),
                        org.copied_from or None,
                        org.created_by or None,
                        org.created_at,
                        org.updated_at,
                    ]
                ],
                ["org_id"],
            )
            self._log(
                "organisation",
                org.org_id,
                "create" if existing is None else "update",
                actor,
                {"name": existing.name, "metamodel": existing.pack_ref, "default": existing.is_default}
                if existing
                else None,
                {"name": org.name, "metamodel": org.pack_ref, "default": org.is_default},
                None,
                MAIN,
                org.org_id,
            )
        return org

    def delete_organisation(self, org_id: str, actor: str) -> None:
        if self.get_organisation(org_id) is None:
            raise NotFoundError(org_id, "organisation")
        with self._lock:
            for table in ORG_TABLES:
                if table != "change_log":
                    self._execute(f"DELETE FROM {table} WHERE org_id = ?", [org_id])
            self._execute("DELETE FROM organisation WHERE org_id = ?", [org_id])
            self._log("organisation", org_id, "delete", actor, None, None, None, MAIN, org_id)

    def copy_organisation_content(self, src_org: str, dst_org: str, actor: str) -> dict[str, int]:
        validate_org_id(src_org)
        validate_org_id(dst_org)
        if self.get_organisation(dst_org) is None:
            raise NotFoundError(dst_org, "organisation")
        counts = self._org_counts().get(dst_org, {})
        if counts.get("elements") or counts.get("relationships"):
            raise ConflictError(f"organisation {dst_org} already holds content; a copy needs an empty one")
        copied: dict[str, int] = {}
        with self._lock:
            for table in ("element", "relationship", "element_link", "reviewer_assignment"):
                cols = [c for c in table_columns(table) if c != "org_id"]
                col_list = ", ".join(cols)
                self._execute(
                    f"INSERT INTO {table} ({col_list}, org_id) SELECT {col_list}, ? FROM {table} WHERE org_id = ?",
                    [dst_org, src_org],
                )
                copied[table] = int(
                    self._fetch_all(f"SELECT COUNT(*) FROM {table} WHERE org_id = ?", [dst_org])[0][0]
                )
            self._log(
                "organisation", dst_org, "copy", actor, None, {"from": src_org, **copied}, None, MAIN, dst_org
            )
        return copied

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
            marks, bound = self._bind([f"%{word}%"] * 5)
            clauses.append(
                f"(name ILIKE {marks[0]} OR key ILIKE {marks[1]} OR element_id ILIKE {marks[2]} "
                f"OR description_md ILIKE {marks[3]} OR attrs ILIKE {marks[4]})"
            )
            params += bound
        if type_id:
            ids = [type_id] if isinstance(type_id, str) else list(type_id)
            marks, bound = self._bind(ids)
            clauses.append(f"type_id IN ({', '.join(marks)})")
            params += bound
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
        branch, org = current_branch(), self._org()
        if branch == MAIN:
            rows = self._fetch_all("SELECT DISTINCT element_id FROM element_link WHERE org_id = ?", [org])
        else:
            rows = self._fetch_all(
                "SELECT DISTINCT element_id FROM element_link WHERE org_id = ? AND element_id NOT IN "
                "(SELECT element_id FROM branch_element WHERE org_id = ? AND branch_id = ?) "
                "UNION SELECT DISTINCT element_id FROM branch_link WHERE org_id = ? AND branch_id = ?",
                [org, org, branch, org, branch],
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
                self._insert_rows("element", [self._element_values(element) + [self._org()]])
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
                    "current_state=?, target_state=?, target_work_package=?, target_note=? "
                    "WHERE org_id=? AND element_id=? AND _version=?",
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
                        self._org(),
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
            where = f"org_id = ? AND {key} IN ({self._marks(chunk)})"
            params: list[Any] = [self._org(), *chunk]
            if branch is not None:
                where = f"branch_id = ? AND {where}"
                params = [branch, *params]
            for row_id, v in self._fetch_all(f"SELECT {key}, {column} FROM {table} WHERE {where}", params):
                out[row_id] = int(v)
        return out

    def upsert_elements(self, elements: list[Element], actor: str) -> tuple[int, int]:
        if not elements:
            return 0, 0
        now = _now()
        branch, org = current_branch(), self._org()
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
                self._replace_rows(
                    "element",
                    ELEMENT_COLUMNS + ["org_id"],
                    [r + [org] for r in rows],
                    ["org_id", "element_id"],
                )
            else:
                branch_rows = self._versions("branch_element", "element_id", "base_version", ids, branch)
                main_versions = self._versions("element", "element_id", "_version", ids)
                extra = [
                    [branch, branch_rows.get(e.element_id, main_versions.get(e.element_id, 0)), "upsert", org]
                    for e in elements
                ]
                self._replace_rows(
                    "branch_element",
                    ELEMENT_COLUMNS + ["branch_id", "base_version", "op", "org_id"],
                    [r + x for r, x in zip(rows, extra, strict=True)],
                    ["org_id", "branch_id", "element_id"],
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
        branch, org = current_branch(), self._org()
        with self._lock:
            if branch == MAIN:
                table, extra = "element_link", [org]
                self._execute(
                    "DELETE FROM element_link WHERE org_id = ? AND element_id = ?", [org, element_id]
                )
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
                table, extra = "branch_link", [branch, org]
                self._execute(
                    "DELETE FROM branch_link WHERE org_id = ? AND branch_id = ? AND element_id = ?",
                    [org, branch, element_id],
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
        branch, org = current_branch(), self._org()
        if branch != MAIN and self._branch_element_row(branch, element_id) is not None:
            rows = self._fetch_all(
                "SELECT link_id, url, label, sort_order FROM branch_link WHERE org_id = ? AND branch_id = ? "
                "AND element_id = ? ORDER BY sort_order",
                [org, branch, element_id],
            )
        else:
            rows = self._fetch_all(
                "SELECT link_id, url, label, sort_order FROM element_link WHERE org_id = ? AND element_id = ? "
                "ORDER BY sort_order",
                [org, element_id],
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

    def find_relationships(
        self, rel_type_id: str | None = None, limit: int = 500, offset: int = 0
    ) -> list[Relationship]:
        where = " WHERE rel_type_id = ?" if rel_type_id else ""
        rows = self._fetch_all(
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl{where} ORDER BY rel_type_id, src_id, dst_id, relationship_id"
            + self._page(limit, offset),
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
                self._insert_rows("relationship", [self._rel_values(rel) + [self._org()]])
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
                    "WHERE org_id=? AND relationship_id=? AND _version=?",
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
                        self._org(),
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
        branch, org = current_branch(), self._org()
        with self._lock:
            if branch == MAIN:
                self._execute(
                    "DELETE FROM relationship WHERE org_id = ? AND relationship_id = ?",
                    [org, relationship_id],
                )
            else:
                main_version = self._main_rel_version(relationship_id)
                if main_version is None:  # only ever existed on the branch: just drop it
                    self._execute(
                        "DELETE FROM branch_relationship WHERE org_id = ? AND branch_id = ? AND relationship_id = ?",
                        [org, branch, relationship_id],
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
        branch, org = current_branch(), self._org()
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
                self._replace_rows(
                    "relationship",
                    RELATIONSHIP_COLUMNS + ["org_id"],
                    [r + [org] for r in rows],
                    ["org_id", "relationship_id"],
                )
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
                        org,
                    ]
                    for r in rels
                ]
                self._replace_rows(
                    "branch_relationship",
                    RELATIONSHIP_COLUMNS + ["branch_id", "base_version", "op", "org_id"],
                    [r + x for r, x in zip(rows, extra, strict=True)],
                    ["org_id", "branch_id", "relationship_id"],
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
        if direction == "both":
            return TRACE_SQL_BOTH.replace("{rel}", self._rel())
        step, take = TRACE_ENDS["out" if direction == "out" else "in"]
        return TRACE_SQL.replace("{rel}", self._rel()).replace("{step}", step).replace("{take}", take)

    def _reached(self, element_id: str, direction: str, max_depth: int) -> list[tuple[Any, ...]]:
        """(node, depth, the node one step nearer, the relationship type between them)."""
        return self._fetch_all(self._trace_sql(direction), [element_id, max_depth, element_id])

    def trace(self, element_id: str, direction: str = "out", max_depth: int = 5) -> list[dict[str, Any]]:
        """Every element reachable within the depth, each with one shortest path to it.

        The walk returns a node once, with the edge that reached it first; a path is
        rebuilt here by following those edges back to the start, which is a step per hop
        rather than a row per path (decision: a walk, not an enumeration)."""
        rows = self._reached(element_id, direction, max_depth)
        via = {str(node): (str(parent), str(rel)) for node, _depth, parent, rel in rows}
        out = []
        for node, depth, _parent, _rel in rows:
            chain, rels, cur = [str(node)], [], str(node)
            # `via` steps one level nearer each time, so this ends at the start; the depth is
            # held against it all the same, because a path that walked in circles would be a
            # loop here rather than a wrong answer on the page.
            while cur in via and len(chain) <= max_depth:
                parent, rel = via[cur]
                chain.append(parent)
                rels.append(rel)
                cur = parent
            out.append(
                {
                    "element_id": str(node),
                    "depth": int(depth),
                    "path": list(reversed(chain)),
                    "rel_path": list(reversed(rels)),
                    "direction": direction,
                }
            )
        return out

    def elements_by_ids(self, ids: list[str]) -> list[Element]:
        """The elements these identifiers name, in one read per chunk.

        What a traversal needs to label its answer. The alternative — one `get_element` per
        row, or the whole model in memory — is what this replaces (decision 0019)."""
        wanted = list(dict.fromkeys(i for i in ids if i))
        if not wanted:
            return []
        out: list[Element] = []
        for chunk in chunks(wanted, self.IN_CHUNK):
            out.extend(
                self._row_to_element(row)
                for row in self._fetch_all(
                    f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM {self._el()} AS el "
                    f"WHERE element_id IN ({self._marks(chunk)})",
                    list(chunk),
                )
            )
        return out

    def edges_among(self, ids: list[str]) -> list[Relationship]:
        """Every live relationship with both ends inside this set of elements."""
        wanted = list(dict.fromkeys(i for i in ids if i))
        if not wanted:
            return []
        out: list[Relationship] = []
        seen: set[str] = set()
        for chunk in chunks(wanted, max(1, self.IN_CHUNK // 2)):
            marks = self._marks(chunk)
            rows = self._fetch_all(
                f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl "
                f"WHERE status <> 'retired' AND src_id IN ({marks}) AND dst_id IN ({marks})",
                list(chunk) + list(chunk),
            )
            for row in rows:
                r = self._row_to_rel(row)
                if r.relationship_id not in seen:
                    seen.add(r.relationship_id)
                    out.append(r)
        # A chunked IN pair only sees edges whose ends fall in the same chunk; with more than
        # one chunk the set is walked again from each element so nothing across a boundary is
        # lost. One chunk is the ordinary case and costs a single read.
        if len(wanted) > max(1, self.IN_CHUNK // 2):
            inside = set(wanted)
            for chunk in chunks(wanted, self.IN_CHUNK):
                for row in self._fetch_all(
                    f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM {self._rel()} AS rl "
                    f"WHERE status <> 'retired' AND src_id IN ({self._marks(chunk)})",
                    list(chunk),
                ):
                    r = self._row_to_rel(row)
                    if r.dst_id in inside and r.relationship_id not in seen:
                        seen.add(r.relationship_id)
                        out.append(r)
        return out

    def edges_frame(self) -> pd.DataFrame:
        return self._fetch_df(
            f"SELECT src_id, dst_id, rel_type_id, qualifier, relationship_id, target_state FROM {self._rel()} AS rl WHERE status <> 'retired'"
        )

    # -------------------------------------------------------------- audit
    def history(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where = " WHERE org_id = ?" + (" AND entity_id = ?" if entity_id else "")
        df = self._fetch_df(
            f"SELECT change_id, entity_kind, entity_id, op, actor, changed_at, before_json, after_json, version, branch_id FROM change_log{where} ORDER BY changed_at DESC"
            + self._page(limit),
            [self._org(), entity_id] if entity_id else [self._org()],
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
                        self._org(),
                    ]
                ],
            )
            self._log("branch", branch.branch_id, "create", actor, None, {"name": branch.name}, None, MAIN)
        return branch

    def get_branch(self, branch_id: str) -> Branch | None:
        rows = self._fetch_all(
            f"SELECT {self._BRANCH_COLS} FROM branch WHERE org_id = ? AND branch_id = ?",
            [self._org(), branch_id],
        )
        if not rows:
            return None
        b = self._row_to_branch(rows[0])
        b.changes = self._branch_row_count(branch_id)
        return b

    def list_branches(self, status: str | None = None) -> list[Branch]:
        where = " AND status = ?" if status else ""
        rows = self._fetch_all(
            f"SELECT {self._BRANCH_COLS} FROM branch WHERE org_id = ?{where} ORDER BY created_at DESC",
            [self._org(), status] if status else [self._org()],
        )
        out = []
        for r in rows:
            b = self._row_to_branch(r)
            b.changes = self._branch_row_count(b.branch_id)
            out.append(b)
        return out

    def _branch_row_count(self, branch_id: str) -> int:
        org = self._org()
        n1 = self._fetch_all(
            "SELECT COUNT(*) FROM branch_element WHERE org_id = ? AND branch_id = ?", [org, branch_id]
        )[0][0]
        n2 = self._fetch_all(
            "SELECT COUNT(*) FROM branch_relationship WHERE org_id = ? AND branch_id = ?", [org, branch_id]
        )[0][0]
        return int(n1) + int(n2)

    def _close_branch(self, branch_id: str, status: str, actor: str) -> None:
        self._execute(
            "UPDATE branch SET status = ?, closed_by = ?, closed_at = ? WHERE org_id = ? AND branch_id = ?",
            [status, actor, _now(), self._org(), branch_id],
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
                f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM element WHERE org_id = ? AND element_id IN ({self._marks(chunk)})",
                [self._org(), *chunk],
            ):
                e = self._row_to_element(row)
                out[e.element_id] = e
        return out

    def _main_rels(self, ids: list[str]) -> dict[str, Relationship]:
        out: dict[str, Relationship] = {}
        for chunk in chunks(ids, self.IN_CHUNK):
            for row in self._fetch_all(
                f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM relationship WHERE org_id = ? AND relationship_id IN ({self._marks(chunk)})",
                [self._org(), *chunk],
            ):
                r = self._row_to_rel(row)
                out[r.relationship_id] = r
        return out

    def _links_of(self, ids: list[str], branch_id: str | None = None) -> dict[str, list[Link]]:
        """The links of many elements at once: main's, or a branch's overlay rows."""
        out: dict[str, list[Link]] = defaultdict(list)
        org = self._org()
        for chunk in chunks(ids, self.IN_CHUNK):
            if branch_id is None:
                sql = (
                    f"SELECT element_id, link_id, url, label, sort_order FROM element_link WHERE org_id = ? "
                    f"AND element_id IN ({self._marks(chunk)}) ORDER BY element_id, sort_order"
                )
                params: list[Any] = [org, *chunk]
            else:
                sql = (
                    f"SELECT element_id, link_id, url, label, sort_order FROM branch_link WHERE org_id = ? "
                    f"AND branch_id = ? AND element_id IN ({self._marks(chunk)}) ORDER BY element_id, sort_order"
                )
                params = [org, branch_id, *chunk]
            for eid, lid, u, lb, so in self._fetch_all(sql, params):
                out[eid].append(Link(element_id=eid, url=u, label=lb or "", link_id=lid, sort_order=so))
        return out

    def diff_branch(self, branch_id: str) -> ChangeSet:
        """The branch's rows against `main` today, with a conflict wherever `main` moved since the base version."""
        branch = self.get_branch(branch_id)
        if branch is None:
            raise NotFoundError(branch_id, "branch")
        org = self._org()
        items: list[ChangeItem] = []
        element_rows = self._fetch_all(
            f"SELECT {', '.join(ELEMENT_COLUMNS)}, base_version, op FROM branch_element "
            f"WHERE org_id = ? AND branch_id = ? ORDER BY element_id",
            [org, branch_id],
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
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)}, base_version, op FROM branch_relationship "
            f"WHERE org_id = ? AND branch_id = ? ORDER BY relationship_id",
            [org, branch_id],
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
        org = self._org()
        if item.kind == "element":
            rows = self._fetch_all(
                f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM branch_element WHERE org_id = ? AND branch_id = ? AND element_id = ?",
                [org, branch_id, item.entity_id],
            )
            if item.change == "deleted":
                self._execute(
                    "DELETE FROM element WHERE org_id = ? AND element_id = ?", [org, item.entity_id]
                )
                self._execute(
                    "DELETE FROM element_link WHERE org_id = ? AND element_id = ?", [org, item.entity_id]
                )
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
            self._execute("DELETE FROM element WHERE org_id = ? AND element_id = ?", [org, item.entity_id])
            self._insert_rows("element", [self._element_values(e) + [org]])
            self._execute(
                "DELETE FROM element_link WHERE org_id = ? AND element_id = ?", [org, item.entity_id]
            )
            self._insert_rows(
                "element_link",
                [
                    [ln.link_id, item.entity_id, ln.url, ln.label or None, ln.sort_order, org]
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
                f"SELECT {', '.join(RELATIONSHIP_COLUMNS)} FROM branch_relationship WHERE org_id = ? AND branch_id = ? AND relationship_id = ?",
                [org, branch_id, item.entity_id],
            )
            if item.change == "deleted":
                self._execute(
                    "DELETE FROM relationship WHERE org_id = ? AND relationship_id = ?", [org, item.entity_id]
                )
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
            self._execute(
                "DELETE FROM relationship WHERE org_id = ? AND relationship_id = ?", [org, item.entity_id]
            )
            self._insert_rows("relationship", [self._rel_values(r) + [org]])
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
        org = self._org()
        if item.kind == "element":
            self._execute(
                "DELETE FROM branch_element WHERE org_id = ? AND branch_id = ? AND element_id = ?",
                [org, branch_id, item.entity_id],
            )
            self._execute(
                "DELETE FROM branch_link WHERE org_id = ? AND branch_id = ? AND element_id = ?",
                [org, branch_id, item.entity_id],
            )
        else:
            self._execute(
                "DELETE FROM branch_relationship WHERE org_id = ? AND branch_id = ? AND relationship_id = ?",
                [org, branch_id, item.entity_id],
            )

    def abandon_branch(self, branch_id: str, actor: str) -> Branch:
        branch = self.get_branch(branch_id)
        if branch is None:
            raise NotFoundError(branch_id, "branch")
        with self._lock:
            for table in ("branch_element", "branch_relationship", "branch_link"):
                self._execute(
                    f"DELETE FROM {table} WHERE org_id = ? AND branch_id = ?", [self._org(), branch_id]
                )
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
                    "UPDATE branch SET status = ?, closed_by = NULL, closed_at = NULL WHERE org_id = ? AND branch_id = ?",
                    [status, self._org(), branch_id],
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
                        self._org(),
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
            "WHERE org_id = ? AND branch_id = ? ORDER BY decided_at",
            [self._org(), branch_id],
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
            "SELECT type_id, reviewer FROM reviewer_assignment WHERE org_id = ? ORDER BY type_id, reviewer",
            [self._org()],
        ):
            out.setdefault(type_id, []).append(reviewer)
        return out

    def set_reviewer_assignment(self, type_id: str, reviewers: list[str], actor: str) -> None:
        org = self._org()
        with self._lock:
            self._execute("DELETE FROM reviewer_assignment WHERE org_id = ? AND type_id = ?", [org, type_id])
            now = _now()
            self._insert_rows(
                "reviewer_assignment",
                [
                    [type_id, r, actor, now, org]
                    for r in dict.fromkeys(x.strip() for x in reviewers if x and x.strip())
                ],
            )
            self._log("reviewers", type_id, "assign", actor, None, {"reviewers": reviewers}, None, MAIN)

    # ----------------------------------------------------------- proposals
    def save_proposal(self, p: Proposal) -> Proposal:
        p.proposal_id = p.proposal_id or new_id("prp")
        p.created_at = p.created_at or _now()
        org = self._org()
        with self._lock:
            self._execute("DELETE FROM proposal WHERE org_id = ? AND proposal_id = ?", [org, p.proposal_id])
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
                        org,
                    ]
                ],
            )
        return p

    def list_proposals(self, branch_id: str | None = None) -> list[Proposal]:
        where = " WHERE org_id = ?" + (" AND branch_id = ?" if branch_id else "")
        rows = self._fetch_all(
            f"SELECT proposal_id, branch_id, title, sources_json, result_json, pushback_json, status, created_by, created_at FROM proposal{where} ORDER BY created_at DESC",
            [self._org(), branch_id] if branch_id else [self._org()],
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
    def _scope_ctes(self) -> str:
        """Common table expressions that shadow the content tables with the current organisation's
        main and the metamodel tables with the version it applies, so a reader's own SQL answers
        for where the reader is."""
        org = self._qo()
        ctes = [f"{t} AS (SELECT * FROM {t} WHERE org_id = {org})" for t in ORG_TABLES]
        current = self.get_organisation(current_org())
        if current is not None and current.pack_id:
            pid = validate_identifier(current.pack_id, "pack id")
            ver = validate_version(current.pack_version or "1", "pack version")
            ctes.append(
                f"meta_pack AS (SELECT * FROM meta_pack WHERE pack_id = '{pid}' AND version = '{ver}')"
            )
            ctes += [
                f"{t} AS (SELECT * FROM {t} WHERE pack_id = '{pid}' AND pack_version = '{ver}')"
                for t in META_TABLES[1:]
            ]
        return ", ".join(ctes)

    def query(
        self, sql: str, params: list[Any] | None = None, limit: int = 1000, scoped: bool = True
    ) -> pd.DataFrame:
        stripped = re.sub(r"--[^\n]*", "", sql).strip().rstrip(";").strip()
        # A word inside a string literal is a value ('merge' is a target state), not a statement.
        bare = re.sub(r"'(?:[^']|'')*'", "''", stripped)
        if ";" in bare or not _READ_ONLY_RE.match(bare) or _FORBIDDEN_RE.search(bare):
            raise ValueError("only a single read-only SELECT/WITH statement is allowed")
        if scoped:
            ctes = self._scope_ctes()
            m = _WITH_RE.match(stripped)
            if m:
                recursive = "RECURSIVE " if m.group(1) else ""
                stripped = f"WITH {recursive}{ctes}, {stripped[m.end() :]}"
            else:
                stripped = f"WITH {ctes} {stripped}"
        return self._fetch_df(f"SELECT * FROM ({stripped}) AS q LIMIT {int(limit)}", params)


__all__ = ["SqlBackend", "chunks", "new_id", "pack_content", "table_columns"]
