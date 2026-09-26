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
from contextlib import contextmanager
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, current_branch, validate_branch_id
from ea.backend.organisations import DEFAULT_ORG, current_org, validate_org_id
from ea.backend.sql import (
    AUDIT_TABLES,
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
    staging_schema,
    table_columns,
)
from ea.metamodel.loader import pack_from_dict, pack_to_dict
from ea.models import (
    DEEP_DIVE_KINDS,
    DEEP_DIVE_ROLES,
    DEEP_DIVE_STATUSES,
    OPEN_STATUSES,
    PACK_STATUSES,
    Branch,
    ChangeItem,
    ChangeSet,
    ConflictError,
    DeepDive,
    DeepDiveElement,
    DeepDiveRating,
    Element,
    ElementFilter,
    ImportRun,
    Issue,
    Link,
    MergeResult,
    NotFoundError,
    Organisation,
    Pack,
    PackVersion,
    Proposal,
    ProposalTemplate,
    Relationship,
    Review,
    SourceFeed,
    is_pack_id,
    pack_id_from_legacy,
    validate_identifier,
    validate_pack_id,
    validate_version,
)

_READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_WITH_RE = re.compile(r"^\s*with\s+(recursive\s+)?", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|attach|copy|export|import|pragma|call|"
    r"install|load|grant|revoke|vacuum|optimize|restore|refresh|msck)\b",
    re.IGNORECASE,
)
#: The catalogues a reader could find the store's own schema names in, and the qualifiers
#: that reach a table directly. Refused in a reader's own SQL for the same reason the store's
#: schemas are: the scoping shadows bare names only.
_SYSTEM_SCHEMAS = ("information_schema", "pg_catalog", "pg_temp", "main", "memory", "system", "temp")
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


_ISSUE_FIELDS = tuple(f.name for f in fields(Issue))


def _string_list(value: Any) -> list[str]:
    """A JSON array of strings, degrading to empty rather than raising on anything else.

    The names are stored as JSON rather than joined on a separator because a file name may
    legitimately contain one: on POSIX it may contain a newline, and a separator would have
    turned one file into two on the way back."""
    try:
        out = json.loads(value) if value else []
    except (TypeError, ValueError):
        return []
    return [str(v) for v in out] if isinstance(out, list) else []


def _issues(value: Any) -> list[Issue]:
    """The issues a run kept, reading only the fields `Issue` declares.

    A row written by a version whose `Issue` had one more field must not make every run
    unreadable by this one: one unreadable row would take the whole history page with it."""
    try:
        raw = json.loads(value) if value else []
    except (TypeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kept = {k: v for k, v in item.items() if k in _ISSUE_FIELDS}
        if kept.get("level") and kept.get("code"):
            out.append(Issue(**{"message": "", **kept}))
    return out


def _counts(value: Any) -> dict[str, int]:
    """Issue totals by code, skipping anything that is not one rather than raising."""
    out: dict[str, int] = {}
    for code, count in _loads(value).items():
        try:
            out[str(code)] = int(count)
        except (TypeError, ValueError):
            continue
    return out


#: A staging table is named by configuration, so its name is checked before it reaches a
#: statement as a name rather than as a bound value.
_STAGING_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def new_id(prefix: str = "") -> str:
    return (prefix + "-" if prefix else "") + uuid.uuid4().hex[:12]


def chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


#: Header fields that are not part of what a version *defines*, so a frozen version may still
#: change them. `status`, `derived_from` and `notes` are its lifecycle. `name` joined them at
#: decision 0022: it is a label a reader sees, nothing keys off it — the identifier does that,
#: and it is opaque (decision 0021) — so a wrong name is corrected where it is wrong rather
#: than by copying a whole definition into a new version to carry the correction.
#:
#: `description`, `source`, `provenance_values` and `properties` are deliberately NOT here.
#: `source` says where a definition came from and `provenance_values` is the vocabulary the
#: registry checks a type's provenance against, so both are part of what was validated;
#: `description` is arguably a label like the name, and is left frozen because widening an
#: approval is not the agent's to do (scope 21).
NOT_DEFINITION = ("status", "derived_from", "notes", "name")


def pack_content(pack: Pack) -> dict[str, Any]:
    """What a version defines, without its lifecycle: the part a frozen version must keep."""
    d = pack_to_dict(pack)
    d["pack"] = {k: v for k, v in d["pack"].items() if k not in NOT_DEFINITION}
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
        #: how deep the open transaction is nested; 0 when none is open
        self._tx_depth = 0
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

    @contextmanager
    def _engine_transaction(self) -> Iterator[None]:
        """Begin; commit when the block ends, roll back when it raises."""
        raise NotImplementedError
        yield

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

    # ----------------------------------------------------------- transactions
    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Every write inside lands together or none of it does, under the store's lock.

        One opened inside another joins it rather than nesting: the outer one decides.
        """
        with self._lock:
            if self._tx_depth:
                self._tx_depth += 1
                try:
                    yield
                finally:
                    self._tx_depth -= 1
                return
            self._tx_depth = 1
            try:
                with self._engine_transaction():
                    yield
            finally:
                self._tx_depth = 0

    # ---------------------------------------------------------------- helpers
    def _put_rows(self, table: str, keys: list[str], rows: list[list[Any]]) -> None:
        """Rows in the DDL's column order, written by key: updated where the key is held, inserted
        where it is not.

        Never a delete and an insert of one key, and only the columns whose value moved are
        set: inside a transaction, once the row is on disk, DuckDB refuses the first and can
        refuse an update that rewrites an indexed column to the value it already holds — and a
        merge is one transaction.
        """
        columns = table_columns(table)
        at = {c: i for i, c in enumerate(columns)}
        others = [c for c in columns if c not in keys]
        where = " AND ".join(f"{k} = ?" for k in keys)
        for row in rows:
            key = [row[at[k]] for k in keys]
            held = self._fetch_all(f"SELECT {', '.join(others)} FROM {table} WHERE {where}", key)
            if not held:
                self._insert_rows(table, [row])
                continue
            moved = [c for c, value in zip(others, held[0], strict=True) if value != row[at[c]]]
            if moved:
                self._execute(
                    f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in moved)} WHERE {where}",
                    [row[at[c]] for c in moved] + key,
                )

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

    def _base_row(self, table: str, key: str, branch: str, entity_id: str) -> str | None:
        """The base row this branch already keeps for this entity, if it keeps one."""
        rows = self._fetch_all(
            f"SELECT base_row FROM {table} WHERE org_id = ? AND branch_id = ? AND {key} = ?",
            [self._org(), branch, entity_id],
        )
        return rows[0][0] if rows else None

    def _base_rows(self, table: str, key: str, branch: str, ids: list[str]) -> dict[str, str | None]:
        """The base rows this branch already keeps, by entity id."""
        out: dict[str, str | None] = {}
        for chunk in chunks(ids, self.IN_CHUNK):
            for entity_id, base_row in self._fetch_all(
                f"SELECT {key}, base_row FROM {table} WHERE org_id = ? AND branch_id = ? "
                f"AND {key} IN ({self._marks(chunk)})",
                [self._org(), branch, *chunk],
            ):
                out[entity_id] = base_row
        return out

    def _main_bases(
        self, ids: list[str], kept: dict[str, str | None], branch_rows: dict[str, Any]
    ) -> dict[str, str | None]:
        """A base row per element: the one the branch already keeps, or main's row captured now."""
        fresh = [i for i in ids if not kept.get(i) and i not in branch_rows]
        mains = self._main_elements(fresh) if fresh else {}
        links = self._links_of(fresh) if fresh else {}
        out: dict[str, str | None] = dict(kept)
        for eid in fresh:
            main = mains.get(eid)
            if main is None:
                out[eid] = None
                continue
            was = self._public(main)
            was["links"] = [ln.url for ln in links.get(eid, [])]
            out[eid] = _dumps(was)
        return out

    def _write_branch_element(self, branch: str, e: Element, base_version: int, op: str = "upsert") -> None:
        with self._lock:
            first_time = self._branch_element_row(branch, e.element_id) is None
            # The row as main held it when this branch first touched it. Kept because
            # `base_version` says only *that* main has moved, never *what* moved: without the
            # base, a branch that changed a description and a main that changed a target state
            # are indistinguishable from two edits of the same field.
            base_row = self._base_row("branch_element", "element_id", branch, e.element_id)
            if first_time and base_version > 0:
                main = self._main_elements([e.element_id]).get(e.element_id)
                if main is not None:
                    was = self._public(main)
                    # Links are part of the row for the purposes of a merge, so they are part
                    # of what the branch started from.
                    was["links"] = [ln.url for ln in self._main_links(e.element_id)]
                    base_row = _dumps(was)
                else:
                    base_row = None
            self._execute(
                "DELETE FROM branch_element WHERE org_id = ? AND branch_id = ? AND element_id = ?",
                [self._org(), branch, e.element_id],
            )
            self._insert_rows(
                "branch_element",
                [self._element_values(e) + [branch, base_version, op, base_row, self._org()]],
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
            first_time = self._branch_rel_row(branch, r.relationship_id) is None
            base_row = self._base_row("branch_relationship", "relationship_id", branch, r.relationship_id)
            if first_time and base_version > 0:
                main = self._main_rels([r.relationship_id]).get(r.relationship_id)
                base_row = _dumps(self._public(main)) if main else None
            self._execute(
                "DELETE FROM branch_relationship WHERE org_id = ? AND branch_id = ? AND relationship_id = ?",
                [self._org(), branch, r.relationship_id],
            )
            self._insert_rows(
                "branch_relationship",
                [self._rel_values(r) + [branch, base_version, op, base_row, self._org()]],
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
            self._migrate_pack_identifiers()
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

    def _migrate_pack_identifiers(self) -> None:
        """A store keyed on readable pack identifiers, brought onto opaque ones (decision 0021).

        Every identifier is folded the same way, by `pack_id_from_legacy`, so a store carried
        forward here and one seeded from the shipped file land on the same key — which is what
        lets the two exchange a pack afterwards. Nothing else moves: the new key satisfies the
        same column and the same index, so there is no DDL, no new column and no re-indexing on
        either engine.

        `change_log` is left alone on purpose. It records what happened under the name things
        had at the time, and rewriting a record of the past to match the present is not a
        migration.
        """
        rows = self._fetch_all("SELECT DISTINCT pack_id FROM meta_pack")
        old_ids = [r[0] for r in rows if r[0] and not is_pack_id(r[0])]
        if not old_ids:
            return
        held = {r[0] for r in rows if r[0]}
        for old in old_ids:
            new = pack_id_from_legacy(old)
            if new in held:
                # The store already holds the same framework under its opaque key — it was
                # seeded from a current file beside a version loaded before. Rewriting would
                # collide on `meta_pack_key`, so the old rows are left where a person can see
                # them and decide, which beats an application that will not open.
                log.warning(
                    "pack %r would become %s, which this store already holds; left as it is", old, new
                )
                continue
            self._execute("UPDATE meta_pack SET pack_id = ? WHERE pack_id = ?", [new, old])
            for table in META_TABLES[1:]:
                self._execute(f"UPDATE {table} SET pack_id = ? WHERE pack_id = ?", [new, old])
            self._execute("UPDATE organisation SET pack_id = ? WHERE pack_id = ?", [new, old])
            # `derived_from` is a `<pack id>@<version>` reference in a text column, so it is
            # rewritten by its prefix rather than by equality.
            self._execute(
                "UPDATE meta_pack SET derived_from = ? || SUBSTRING(derived_from FROM ?) "
                "WHERE derived_from LIKE ?",
                [new, len(old) + 1, f"{old}@%"],
            )
            held.add(new)
            log.info("pack %r is now %s", old, new)

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
                    t.level or "enterprise",
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

    def _rename_pack(self, pack_id: str, version: str, name: str, was: str, actor: str, now: Any) -> None:
        """Write a version's name without touching what it defines.

        The one update a frozen version takes (decision 0022). It is logged with the name it
        had, because the row itself keeps no history and a correction nobody can trace back is
        not a correction anybody can argue with.
        """
        self._execute(
            "UPDATE meta_pack SET name = ?, loaded_at = ? WHERE pack_id = ? AND version = ?",
            [name, now, pack_id, version],
        )
        self._log(
            "metamodel",
            f"{pack_id}@{version}",
            "rename",
            actor or "system",
            {"name": was},
            {"name": name},
            None,
        )

    def save_pack(self, pack: Pack, actor: str = "") -> None:
        validate_pack_id(pack.id)
        validate_version(pack.version, "pack version")
        now = _now()
        with self._lock:
            header = self._pack_header(pack.id, pack.version)
            created_by, created_at, published_by, published_at = actor or None, now, None, None
            if header is not None:
                # pack_id, version, status, created_by, created_at, published_by, published_at,
                # loaded_at, name, ... — the name is column 8, not column 1.
                _, _, status, created_by, created_at, published_by, published_at, _, stored_name, *_ = header
                if status in ("published", "retired"):
                    stored = self.load_pack(pack.id, pack.version)
                    if stored is not None and pack_content(stored) == pack_content(pack):
                        # The same definition again. The name is not part of a definition
                        # (decision 0022), so a save that changes only that is a rename, and
                        # is written rather than refused or silently dropped.
                        if stored.name != pack.name:
                            self._rename_pack(pack.id, pack.version, pack.name, stored.name, actor, now)
                        return
                    raise ConflictError(
                        f"version {pack.version} of {stored_name or pack.id} is {status} and frozen; "
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
            "description, examples, source_of_record, type_owner, instance_owner, notation, abstract, properties, "
            "level FROM meta_element_type WHERE pack_id = ? AND pack_version = ? ORDER BY sort_order",
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
                    "level": row[17] or "enterprise",
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
                # The change log stays and everything else goes, runs included: an org_id is
                # free to be taken again, and a run carries the actor names, file names, issue
                # messages and whole mapping of the organisation that is gone.
                if table not in AUDIT_TABLES:
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
            for table in (
                "element",
                "relationship",
                "element_link",
                "reviewer_assignment",
                "proposal_template",
            ):
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

    @staticmethod
    def _like(word: str) -> str:
        """A reader's word as a LIKE pattern.

        `%` and `_` are wildcards to SQL and ordinary characters to the person typing them,
        so a search for '50%' would otherwise match every row holding '50'. They are escaped
        here and every clause below says `ESCAPE '\\'`.
        """
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def _any_of(self, column: str, values: list[str]) -> tuple[str, list[Any]]:
        """`column IN (...)`, or the empty-string case a grid sends for 'not set'."""
        real = [v for v in values if v]
        blank = len(real) < len(values)
        parts, params = [], []
        if real:
            marks, bound = self._bind(real)
            parts.append(f"{column} IN ({', '.join(marks)})")
            params += bound
        if blank:
            parts.append(f"({column} IS NULL OR {column} = '')")
        return ("(" + " OR ".join(parts) + ")") if parts else "", params

    def _where(self, filt: ElementFilter | None) -> tuple[str, list[Any]]:
        """Every criterion the filter carries, ANDed together."""
        f = filt or ElementFilter()
        clauses: list[str] = []
        params: list[Any] = []
        for word in f.words:  # every word must match somewhere
            marks, bound = self._bind([self._like(word)] * 5)
            clauses.append(
                f"(name ILIKE {marks[0]} ESCAPE '\\' OR key ILIKE {marks[1]} ESCAPE '\\' "
                f"OR element_id ILIKE {marks[2]} ESCAPE '\\' OR description_md ILIKE {marks[3]} ESCAPE '\\' "
                f"OR attrs ILIKE {marks[4]} ESCAPE '\\')"
            )
            params += bound
        for column, values in (
            ("type_id", f.type_ids),
            ("status", f.statuses),
            ("current_state", f.current_states),
            ("target_state", f.target_states),
            ("target_work_package", f.work_packages),
            ("source_system", f.sources),
            ("lifecycle_status", f.lifecycle_statuses),
        ):
            if values:
                clause, bound = self._any_of(column, list(values))
                if clause:
                    clauses.append(clause)
                    params += bound
        for a in f.attributes:
            if not a.name:
                continue
            # The attribute is stored inside the row's JSON, so the name is matched as the
            # key it is written as and the value as a substring of what follows it. A reader
            # asking for an attribute with no value asks only that it is set.
            marks, bound = self._bind(
                [self._like(f'"{a.name}":')] + ([self._like(a.value)] if a.value else [])
            )
            clause = f"attrs ILIKE {marks[0]} ESCAPE '\\'"
            if a.value:
                clause += f" AND attrs ILIKE {marks[1]} ESCAPE '\\'"
            clauses.append(f"({clause})")
            params += bound
        if f.updated_since is not None:
            clauses.append("updated_at >= ?")
            params.append(f.updated_since)
        if f.updated_before is not None:
            clauses.append("updated_at < ?")
            params.append(f.updated_before)
        if f.only_ids is not None:
            if not f.only_ids:
                return " WHERE 1 = 0", []
            clause, bound = self._any_of("element_id", list(f.only_ids))
            clauses.append(clause)
            params += bound
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _rank(self, words: list[str]) -> tuple[str, list[Any]]:
        """How well a row matches, as SQL, so the store ranks before it pages.

        0 the name starts with what was typed, 1 the name, key or identifier holds every
        word, 2 it matched somewhere else (a description, an attribute). Ranking in Python
        over a page would rank only the rows that page happened to contain.
        """
        if not words:
            return "0", []
        params: list[Any] = []
        prefix_mark, bound = self._bind([self._like(" ".join(words))[1:]])  # 'word%', not '%word%'
        params += bound
        alls = []
        for column in ("name", "key", "element_id"):
            marks, bound = self._bind([self._like(w) for w in words])
            alls.append(" AND ".join(f"{column} ILIKE {m} ESCAPE '\\'" for m in marks))
            params += bound
        both = " OR ".join(f"({a})" for a in alls)
        return (
            f"CASE WHEN name ILIKE {prefix_mark[0]} ESCAPE '\\' THEN 0 WHEN {both} THEN 1 ELSE 2 END"
        ), params

    #: What each sort order is in SQL. Every one ends on the identifier, so a page boundary
    #: never splits two rows that compare equal and shows one of them twice.
    _SORT_SQL = {
        "name": "name",
        "type": "type_id",
        "status": "status",
        "updated": "updated_at",
        "created": "created_at",
    }

    def _order_by(self, filt: ElementFilter | None) -> tuple[str, list[Any]]:
        f = filt or ElementFilter()
        direction = " DESC" if f.descending else ""
        order = f.order()
        if order == "relevance":
            rank, params = self._rank(f.words)
            return f" ORDER BY {rank}{direction}, name, element_id", params
        return f" ORDER BY {self._SORT_SQL[order]}{direction}, element_id", []

    def find_elements(
        self, filt: ElementFilter | None = None, limit: int = 200, offset: int = 0
    ) -> list[Element]:
        where, params = self._where(filt)
        order, order_params = self._order_by(filt)
        rows = self._fetch_all(
            f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM {self._el()} AS el{where}{order}"
            + self._page(limit, offset),
            params + order_params,
        )
        return [self._row_to_element(r) for r in rows]

    def count_elements(self, filt: ElementFilter | None = None) -> int:
        where, params = self._where(filt)
        return int(self._fetch_all(f"SELECT COUNT(*) FROM {self._el()} AS el{where}", params)[0][0])

    def distinct_values(self, column: str) -> list[str]:
        """The values a filterable column actually holds, for the options on a filter control.

        Only the columns the filter names may be asked for, so the name never reaches SQL
        from anywhere but this list.
        """
        if column not in self._SORT_SQL and column not in (
            "source_system",
            "lifecycle_status",
            "target_work_package",
            "current_state",
            "target_state",
        ):
            raise ValueError(f"{column} is not a filterable column")
        rows = self._fetch_all(
            f"SELECT DISTINCT {column} FROM {self._el()} AS el "
            f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY 1" + self._page(500)
        )
        return [r[0] for r in rows]

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

    def upsert_elements(self, elements: list[Element], actor: str) -> tuple[int, int, int]:
        if not elements:
            return 0, 0, 0
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
            return inserted, 0, len(unchanged)
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
                # `_replace_rows` is a delete and an insert, so every column it does not name
                # comes back empty. Leaving `base_row` out of the list meant one import onto a
                # branch threw away what the branch started from — and nothing recaptures it,
                # because the row is no longer new.
                kept = self._base_rows("branch_element", "element_id", branch, ids)
                bases = self._main_bases(ids, kept, branch_rows)
                extra = [
                    [
                        branch,
                        branch_rows.get(e.element_id, main_versions.get(e.element_id, 0)),
                        "upsert",
                        bases.get(e.element_id),
                        org,
                    ]
                    for e in elements
                ]
                self._replace_rows(
                    "branch_element",
                    ELEMENT_COLUMNS + ["branch_id", "base_version", "op", "base_row", "org_id"],
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
        return inserted, len(existing) - len(unchanged), len(unchanged)

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

    def upsert_relationships(self, rels: list[Relationship], actor: str) -> tuple[int, int, int]:
        if not rels:
            return 0, 0, 0
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
            return inserted, 0, len(unchanged)
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
                kept = self._base_rows("branch_relationship", "relationship_id", branch, ids)
                bases = {
                    rid: kept.get(rid)
                    or (
                        None
                        if rid in branch_rows
                        else _dumps(self._public(m))
                        if (m := self._main_rels([rid]).get(rid))
                        else None
                    )
                    for rid in ids
                }
                extra = [
                    [
                        branch,
                        branch_rows.get(r.relationship_id, main_versions.get(r.relationship_id, 0)),
                        "upsert",
                        bases.get(r.relationship_id),
                        org,
                    ]
                    for r in rels
                ]
                self._replace_rows(
                    "branch_relationship",
                    RELATIONSHIP_COLUMNS + ["branch_id", "base_version", "op", "base_row", "org_id"],
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
        return inserted, len(existing) - len(unchanged), len(unchanged)

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

    def elements_by_keys(self, keys: list[str]) -> list[Element]:
        """The elements carrying these human keys, in one read per chunk.

        What an import merging on the source's own key needs: the identity the store already
        gave the thing, so a second load updates it rather than making another one."""
        wanted = list(dict.fromkeys(k for k in keys if k))
        if not wanted:
            return []
        out: list[Element] = []
        for chunk in chunks(wanted, self.IN_CHUNK):
            out.extend(
                self._row_to_element(row)
                for row in self._fetch_all(
                    f"SELECT {', '.join(ELEMENT_COLUMNS)} FROM {self._el()} AS el "
                    f"WHERE key IN ({self._marks(chunk)})",
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

    def _three_way(
        self,
        was: dict[str, Any] | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        main: Any,
        base: int,
        op: str,
    ) -> tuple[list[str], list[str], list[str]]:
        """What the branch changed, what main changed, and where the two disagree.

        A version that moved says only that main was written; it does not say the two
        disagree. With the base row, the branch's changes and main's changes are each a set
        of fields, and only their **intersection** is a conflict — an architect who edited a
        description and one who edited a target state have not disagreed about anything.

        Without a base row (a branch written before this was kept, or a row the branch
        added), the old rule stands: a moved version is treated as a conflict over
        everything the branch touched, because nothing here can prove otherwise.
        """
        if main is None:
            return [], [], []
        now = self._public(main)
        if before is not None and "links" in before:
            now["links"] = before["links"]
        if op == "delete":
            # The branch wants the row gone and main has been writing to it. That is a
            # disagreement about the whole row, and it used to pass as no conflict at all:
            # the delete applied and main's edit went with it, unremarked.
            theirs = self._changed_fields(was, now) if was is not None else []
            if was is None and main.version != base:
                return [], ["the row"], ["the row"]
            return [], theirs, list(theirs)
        if was is None:
            if main.version == base:
                return self._changed_fields(before, after), [], []
            # No base to compare against: every field the branch touched is in dispute.
            touched = self._changed_fields(before, after)
            return touched, touched, touched
        # A base written before links were part of it cannot speak about them.
        blind = [] if "links" in was else ["links"]
        mine = [f for f in self._changed_fields(was, after) if f not in blind]
        theirs = [f for f in self._changed_fields(was, now) if f not in blind]
        both = sorted(set(mine) & set(theirs))
        # A field both sides moved to the *same* value is not a disagreement.
        both = [f for f in both if (after or {}).get(f) != now.get(f)]
        return mine, theirs, both

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
            f"SELECT {', '.join(ELEMENT_COLUMNS)}, base_version, op, base_row FROM branch_element "
            f"WHERE org_id = ? AND branch_id = ? ORDER BY element_id",
            [org, branch_id],
        )
        element_ids = [row[0] for row in element_rows]
        mains = self._main_elements(element_ids)
        main_links = self._links_of(element_ids)
        branch_links = self._links_of(element_ids, branch_id)
        for row in element_rows:
            e = self._row_to_element(row[: len(ELEMENT_COLUMNS)])
            base, op, base_row = int(row[-3]), row[-2], row[-1]
            main = mains.get(e.element_id)
            before = self._public(main) if main else None
            after = self._public(e) if op == "upsert" else None
            if main is None:
                change = "added"
            elif op == "delete":
                change = "deleted"
            else:
                change = "changed"
            # `main` gone with a base version above zero means the row the branch started
            # from was deleted on main. Writing the branch's copy back would resurrect it
            # without anybody deciding to, so it is a conflict like any other.
            gone_on_main = main is None and base > 0
            was = _loads(base_row) if base_row else None
            # Links are compared with the fields, not after them. They used to be attached
            # once the three-way had run, so a branch that touched no field still replaced
            # main's links on merge and nothing on the screen said it would.
            if before is not None:
                before["links"] = [ln.url for ln in main_links.get(e.element_id, [])]
            if after is not None:
                after["links"] = [ln.url for ln in branch_links.get(e.element_id, [])]
            mine, theirs, both = self._three_way(was, before, after, main, base, op)
            items.append(
                ChangeItem(
                    kind="element",
                    entity_id=e.element_id,
                    label=e.name,
                    change=change,
                    base_version=base,
                    main_version=main.version if main else None,
                    conflict=gone_on_main or bool(both),
                    before=before,
                    after=after,
                    fields_changed=self._changed_fields(before, after),
                    base=was,
                    branch_fields=mine,
                    main_fields=theirs,
                    overlapping=both,
                )
            )
        rel_rows = self._fetch_all(
            f"SELECT {', '.join(RELATIONSHIP_COLUMNS)}, base_version, op, base_row FROM branch_relationship "
            f"WHERE org_id = ? AND branch_id = ? ORDER BY relationship_id",
            [org, branch_id],
        )
        main_rels = self._main_rels([row[0] for row in rel_rows])
        for row in rel_rows:
            r = self._row_to_rel(row[: len(RELATIONSHIP_COLUMNS)])
            base, op, base_row = int(row[-3]), row[-2], row[-1]
            main = main_rels.get(r.relationship_id)
            before = self._public(main) if main else None
            after = self._public(r) if op == "upsert" else None
            change = "added" if main is None else ("deleted" if op == "delete" else "changed")
            gone_on_main = main is None and base > 0
            was = _loads(base_row) if base_row else None
            mine, theirs, both = self._three_way(was, before, after, main, base, op)
            items.append(
                ChangeItem(
                    kind="relationship",
                    entity_id=r.relationship_id,
                    label=f"{r.src_id} {r.rel_type_id.split('__')[1].replace('_', ' ') if '__' in r.rel_type_id else r.rel_type_id} {r.dst_id}",
                    change=change,
                    base_version=base,
                    main_version=main.version if main else None,
                    conflict=gone_on_main or bool(both),
                    before=before,
                    after=after,
                    fields_changed=self._changed_fields(before, after),
                    base=was,
                    branch_fields=mine,
                    main_fields=theirs,
                    overlapping=both,
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
        resolutions: dict[str, str | dict[str, str]] | None = None,
    ) -> MergeResult:
        """Apply the branch's rows to `main`, item by item, field by field.

        `include` names the item keys (`element:<id>`, `relationship:<id>`) to merge now; None
        means every item. Every applied row is **main's current row with the branch's changed
        fields laid over it**, so a branch that moved on does not revert what main did to the
        fields it never touched.

        A row is a conflict only where both sides changed the *same* field. `resolutions[key]`
        decides it, and takes either form:

        * `"branch"` — take the branch's value for every disputed field;
        * `"main"` — drop the row from the branch, keeping main's as it is;
        * `{field: "branch" | "main"}` — decide field by field. A disputed field the mapping
          does not name is left undecided, and the row stays on the branch.

        Applied and dropped rows leave the branch; the branch closes when nothing remains.
        """
        resolutions = resolutions or {}
        result = MergeResult(branch_id=branch_id)
        now = _now()
        # One transaction, the diff read inside it: a failure on any row leaves main and the
        # branch as they were, rather than half the change on main and gone from the branch.
        with self.transaction():
            change_set = self.diff_branch(branch_id)
            if change_set.branch.status not in OPEN_STATUSES:
                raise ConflictError(f"branch {branch_id} is {change_set.branch.status}")
            # relationships that are deleted go first, elements next, relationships added or changed last,
            # so an added relationship always finds its ends on main
            ordered = (
                [i for i in change_set.items if i.kind == "relationship" and i.change == "deleted"]
                + [i for i in change_set.items if i.kind == "element"]
                + [i for i in change_set.items if i.kind == "relationship" and i.change != "deleted"]
            )
            # Which elements this merge will put on main. A merge of everything writes every
            # end before the relationships that need them; a merge of some rows need not, so
            # the ends are checked rather than assumed.
            landing = {
                i.entity_id
                for i in ordered
                if i.kind == "element"
                and i.change != "deleted"
                and (include is None or i.key in include)
                and (not i.conflict or self._decided(resolutions.get(i.key)))
            }
            leaving = {
                i.entity_id
                for i in ordered
                if i.kind == "element"
                and i.change == "deleted"
                and (include is None or i.key in include)
                and (not i.conflict or self._decided(resolutions.get(i.key)))
            }
            for item in ordered:
                if include is not None and item.key not in include:
                    continue
                take: dict[str, str] = {}
                if item.conflict:
                    choice = resolutions.get(item.key)
                    if choice == "main":
                        self._drop_branch_row(branch_id, item)
                        result.dropped.append(item.key)
                        continue
                    if choice == "branch":
                        take = dict.fromkeys(item.overlapping, "branch")
                    elif isinstance(choice, dict):
                        if not item.overlapping:
                            # Nothing here is disputed field by field — main deleted the row,
                            # or the base is unknown — so a mapping cannot express the choice.
                            result.held_back.append(
                                {
                                    "key": item.key,
                                    "reason": "this one is the whole row: resolve it as branch or main",
                                }
                            )
                            continue
                        take = {f: v for f, v in choice.items() if f in item.overlapping}
                        undecided = [f for f in item.overlapping if f not in take]
                        if undecided:
                            result.held_back.append(
                                {"key": item.key, "reason": f"no decision for {', '.join(undecided)}"}
                            )
                            continue
                        if all(v == "main" for v in take.values()) and not [
                            f for f in item.branch_fields if f not in item.overlapping
                        ]:
                            # Every disputed field goes to main and the branch changed nothing
                            # else, so the row has nothing left to contribute. `take` is never
                            # empty here: an empty overlap was turned away above, and an
                            # `all()` over nothing would have made this true for every row.
                            self._drop_branch_row(branch_id, item)
                            result.dropped.append(item.key)
                            continue
                    else:
                        result.held_back.append({"key": item.key, "reason": "the conflict is not resolved"})
                        continue  # unresolved: stays on the branch
                if (
                    item.change == "changed"
                    and item.before is not None
                    and not item.branch_fields
                    and not item.conflict
                ):
                    # The branch holds a copy of main's row and changed none of it — `set_links`
                    # alone puts one there. Writing it back reverted every field main moved
                    # since, with no conflict and nothing on the screen to say so.
                    self._drop_branch_row(branch_id, item)
                    result.dropped.append(item.key)
                    continue
                missing = self._ends_missing(item, landing, leaving)
                if missing:
                    # Writing it anyway would leave main holding a relationship to an element
                    # that is not there — a broken model nothing on the branch can repair,
                    # because the row that would repair it has already been merged away.
                    result.held_back.append(
                        {
                            "key": item.key,
                            "reason": f"{missing} is not on main and is not in this merge",
                        }
                    )
                    continue
                self._apply_item(branch_id, item, actor, now, take)
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

    @staticmethod
    def _decided(choice: Any) -> bool:
        """Whether a resolution means the branch's row is going to land on main."""
        return choice == "branch" or isinstance(choice, dict)

    def _ends_missing(self, item: ChangeItem, landing: set[str], leaving: set[str]) -> str:
        """The end of a relationship this merge would leave dangling on main, or empty.

        `landing` is what this merge writes to main, `leaving` what it deletes from main.
        An end counts as present when it is on main already and not being deleted, or when
        this same merge is putting it there.
        """
        if item.kind != "relationship" or item.change == "deleted":
            return ""
        row = item.after or {}
        for end in (row.get("src_id"), row.get("dst_id")):
            if not end or end in landing:
                continue
            if end in leaving or self._main_element_version(end) is None:
                return str(end)
        return ""

    #: Fields the merge never sets from the merged row: the first five describe the row's own
    #: history on main rather than anything the branch decided, and `links` are their own
    #: table — they are compared as a field and written as rows, below.
    _NEVER_MERGED = ("version", "created_at", "created_by", "updated_at", "updated_by", "links")

    def _merged_element(self, item: ChangeItem, branch_row: Element, take: dict[str, str]) -> Element:
        """Main's row with the branch's changes laid over it, field by field.

        Writing the branch's whole row was what made a conflict cost more than it should:
        two architects editing different fields of one element, and whoever merged second
        reverted the first one's work along with their own change landing. Only the fields
        the branch actually changed are carried over now, and `take` decides the ones both
        sides moved.
        """
        return self._lay_over(item, branch_row, take)

    def _merged_rel(self, item: ChangeItem, branch_row: Relationship, take: dict[str, str]) -> Relationship:
        return self._lay_over(item, branch_row, take)

    def _lay_over(self, item: ChangeItem, branch_row: Any, take: dict[str, str]) -> Any:
        # `before` is main's row. Without one there is nothing to lay over — the branch added
        # this row — so the branch's own row stands. The *base* being unknown is a different
        # thing: `_three_way` then treats every touched field as disputed, and `take` still
        # decides them, which is why the guard reads `before` rather than `base`.
        if item.before is None:
            return branch_row
        merged = item.merged_row(take)
        for f, v in merged.items():
            if f in self._NEVER_MERGED or not hasattr(branch_row, f):
                continue
            setattr(branch_row, f, v)
        return branch_row

    def _takes_links(self, item: ChangeItem, take: dict[str, str]) -> bool:
        """Whether this merge should write the branch's links over main's.

        Only when the branch actually changed them, and — where main changed them too — only
        when somebody said the branch wins. A branch carries a copy of main's links from the
        moment it first touches the element, so writing them unconditionally reverted every
        link main added in the meantime.
        """
        if item.before is None:
            return True  # a row the branch added brings its own links
        if "links" not in item.branch_fields:
            return False
        return take.get("links", "branch") == "branch"

    def _apply_item(
        self, branch_id: str, item: ChangeItem, actor: str, now: datetime, take: dict[str, str] | None = None
    ) -> None:
        origin_log = f"branch:{branch_id}"
        org = self._org()
        take = take or {}
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
            e = self._merged_element(item, self._row_to_element(rows[0]), take)
            e.version = (item.main_version or 0) + 1
            e.updated_at, e.updated_by = now, actor
            if item.main_version is None:
                e.created_at, e.created_by = e.created_at or now, e.created_by or actor
            self._put_rows("element", ["org_id", "element_id"], [self._element_values(e) + [org]])
            if self._takes_links(item, take):
                links = self._branch_links(branch_id, item.entity_id)
                kept = [ln.link_id for ln in links]
                # written before the ones the branch dropped are deleted: see `_put_rows`
                self._put_rows(
                    "element_link",
                    ["org_id", "link_id"],
                    [
                        [ln.link_id, item.entity_id, ln.url, ln.label or None, ln.sort_order, org]
                        for ln in links
                    ],
                )
                self._execute(
                    "DELETE FROM element_link WHERE org_id = ? AND element_id = ?"
                    + (f" AND link_id NOT IN ({', '.join('?' for _ in kept)})" if kept else ""),
                    [org, item.entity_id, *kept],
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
            r = self._merged_rel(item, self._row_to_rel(rows[0]), take)
            r.version = (item.main_version or 0) + 1
            r.updated_at, r.updated_by = now, actor
            self._put_rows("relationship", ["org_id", "relationship_id"], [self._rel_values(r) + [org]])
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
    _PROPOSAL_COLUMNS = (
        "proposal_id, branch_id, title, sources_json, result_json, pushback_json, status, "
        "created_by, created_at, template_id, revises, conversation_json, updated_at"
    )

    def save_proposal(self, p: Proposal) -> Proposal:
        p.proposal_id = p.proposal_id or new_id("prp")
        p.created_at = p.created_at or _now()
        p.updated_at = _now()
        org = self._org()
        with self.transaction():
            self._put_rows(
                "proposal",
                ["org_id", "proposal_id"],
                [
                    [
                        p.proposal_id,
                        p.branch_id or "",
                        p.title,
                        json.dumps(p.sources, ensure_ascii=False, default=str),
                        json.dumps(p.result, ensure_ascii=False, default=str),
                        json.dumps(p.pushback, ensure_ascii=False),
                        p.status,
                        p.created_by or None,
                        p.created_at,
                        org,
                        p.template_id or None,
                        p.revises or None,
                        json.dumps(p.conversation, ensure_ascii=False, default=str),
                        p.updated_at,
                    ]
                ],
            )
        return p

    @staticmethod
    def _row_to_proposal(r: tuple) -> Proposal:
        return Proposal(
            proposal_id=r[0],
            branch_id=r[1] or "",
            title=r[2] or "",
            sources=json.loads(r[3] or "[]"),
            result=json.loads(r[4] or "{}"),
            pushback=json.loads(r[5] or "[]"),
            status=r[6] or "",
            created_by=r[7] or "",
            created_at=r[8],
            template_id=r[9] or "",
            revises=r[10] or "",
            conversation=json.loads(r[11] or "[]"),
            updated_at=r[12] or r[8],
        )

    def list_proposals(
        self, branch_id: str | None = None, status: str | None = None, created_by: str | None = None
    ) -> list[Proposal]:
        where, params = ["org_id = ?"], [self._org()]
        for column, value in (("branch_id", branch_id), ("status", status), ("created_by", created_by)):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        rows = self._fetch_all(
            f"SELECT {self._PROPOSAL_COLUMNS} FROM proposal WHERE {' AND '.join(where)} "
            "ORDER BY COALESCE(updated_at, created_at) DESC, created_at DESC",
            params,
        )
        return [self._row_to_proposal(r) for r in rows]

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        rows = self._fetch_all(
            f"SELECT {self._PROPOSAL_COLUMNS} FROM proposal WHERE org_id = ? AND proposal_id = ?",
            [self._org(), proposal_id],
        )
        return self._row_to_proposal(rows[0]) if rows else None

    def delete_proposal(self, proposal_id: str) -> None:
        with self._lock:
            self._execute(
                "DELETE FROM proposal WHERE org_id = ? AND proposal_id = ?", [self._org(), proposal_id]
            )

    # ------------------------------------------------------------ templates
    _TEMPLATE_COLUMNS = (
        "template_id, name, description, pack_id, document, created_by, created_at, updated_at"
    )

    @staticmethod
    def _row_to_template(r: tuple) -> ProposalTemplate:
        return ProposalTemplate(
            template_id=r[0],
            name=r[1] or "",
            description=r[2] or "",
            pack_id=r[3] or "",
            document=r[4] or "",
            created_by=r[5] or "",
            created_at=r[6],
            updated_at=r[7],
        )

    def save_proposal_template(self, t: ProposalTemplate, actor: str) -> ProposalTemplate:
        org = self._org()
        now = _now()
        t.template_id = t.template_id or new_id("tpl")
        held = self.get_proposal_template(t.template_id)
        t.created_by = held.created_by if held else (t.created_by or actor)
        t.created_at = held.created_at if held else now
        t.updated_at = now
        with self.transaction():
            self._put_rows(
                "proposal_template",
                ["org_id", "template_id"],
                [
                    [
                        t.template_id,
                        t.name,
                        t.description or None,
                        t.pack_id or None,
                        t.document,
                        t.created_by or None,
                        t.created_at,
                        t.updated_at,
                        org,
                    ]
                ],
            )
            self._log(
                "template",
                t.template_id,
                "update" if held else "insert",
                actor,
                {"name": held.name, "pack_id": held.pack_id} if held else None,
                {"name": t.name, "pack_id": t.pack_id},
                None,
                MAIN,
            )
        return t

    def list_proposal_templates(self) -> list[ProposalTemplate]:
        rows = self._fetch_all(
            f"SELECT {self._TEMPLATE_COLUMNS} FROM proposal_template WHERE org_id = ? ORDER BY name",
            [self._org()],
        )
        return [self._row_to_template(r) for r in rows]

    def get_proposal_template(self, template_id: str) -> ProposalTemplate | None:
        rows = self._fetch_all(
            f"SELECT {self._TEMPLATE_COLUMNS} FROM proposal_template WHERE org_id = ? AND template_id = ?",
            [self._org(), template_id],
        )
        return self._row_to_template(rows[0]) if rows else None

    def delete_proposal_template(self, template_id: str, actor: str) -> None:
        held = self.get_proposal_template(template_id)
        if held is None:
            raise NotFoundError(template_id, "proposal template")
        with self.transaction():
            self._execute(
                "DELETE FROM proposal_template WHERE org_id = ? AND template_id = ?",
                [self._org(), template_id],
            )
            self._log("template", template_id, "delete", actor, {"name": held.name}, None, None, MAIN)

    # ------------------------------------------------------------ deep dives
    #: A deep dive nobody has rated sorts as the middle of the scale: above one the readers
    #: judged poor, below one they judged good (decision 0024).
    _UNRATED = 3

    _DEEP_DIVE_HEAD = (
        "d.deep_dive_id, d.title, d.kind, d.brief_json, d.domain_ids, d.type_ids, d.work_package, "
        "d.branch_id, d.pack_id, d.pack_version, d.status, d.created_by, d.created_at, "
        "r.average, r.n"
    )

    def _ratings_joined(self) -> str:
        """The deep dives of the organisation with their rating beside them — none for an unrated one."""
        return (
            "deep_dive AS d LEFT JOIN (SELECT deep_dive_id, AVG(stars) AS average, COUNT(*) AS n "
            "FROM deep_dive_rating WHERE org_id = ? GROUP BY deep_dive_id) AS r "
            "ON r.deep_dive_id = d.deep_dive_id"
        )

    @staticmethod
    def _row_to_deep_dive(r: tuple, content: str | None = None) -> DeepDive:
        return DeepDive(
            deep_dive_id=r[0],
            title=r[1] or "",
            kind=r[2] or "",
            brief=json.loads(r[3] or "{}"),
            domain_ids=json.loads(r[4] or "[]"),
            type_ids=json.loads(r[5] or "[]"),
            work_package=r[6] or "",
            branch_id=r[7] or "",
            pack_id=r[8] or "",
            pack_version=r[9] or "",
            status=r[10] or "kept",
            created_by=r[11] or "",
            created_at=r[12],
            rating_average=round(float(r[13]), 2) if r[13] is not None else None,
            rating_count=int(r[14] or 0),
            content=json.loads(content) if content else {},
        )

    def save_deep_dive(self, d: DeepDive) -> DeepDive:
        if d.kind not in DEEP_DIVE_KINDS:
            raise ValueError(f"a deep dive is one of {', '.join(DEEP_DIVE_KINDS)}, not {d.kind!r}")
        org, branch = self._org(), current_branch()
        d.deep_dive_id = d.deep_dive_id or new_id("dd")
        d.created_at = d.created_at or _now()
        d.status = "kept"
        d.branch_id = "" if branch == MAIN else branch
        if not d.pack_id:
            held = self.get_organisation(org)
            d.pack_id, d.pack_version = (held.pack_id, held.pack_version) if held else ("", "")
        # One row per element, in the strongest part it plays: what the deep dive is about
        # before what a finding names, before what a view merely draws.
        rank = {role: i for i, role in enumerate(DEEP_DIVE_ROLES)}
        cited: dict[str, DeepDiveElement] = {}
        for e in d.elements:
            held_e = cited.get(e.element_id)
            if held_e is None or rank.get(e.role, 9) < rank.get(held_e.role, 9):
                cited[e.element_id] = e
        d.elements = list(cited.values())
        with self.transaction():
            self._insert_rows(
                "deep_dive",
                [
                    [
                        d.deep_dive_id,
                        d.title,
                        d.kind,
                        json.dumps(d.brief, ensure_ascii=False, default=str),
                        json.dumps(d.content, ensure_ascii=False, default=str),
                        json.dumps(d.domain_ids, ensure_ascii=False),
                        json.dumps(d.type_ids, ensure_ascii=False),
                        d.work_package or None,
                        d.branch_id or None,
                        d.pack_id or None,
                        d.pack_version or None,
                        d.status,
                        d.created_by or None,
                        d.created_at,
                        org,
                    ]
                ],
            )
            if d.elements:
                self._insert_rows(
                    "deep_dive_element",
                    [[d.deep_dive_id, e.element_id, e.role, int(e.maturity), org] for e in d.elements],
                )
            self._log(
                "deep_dive",
                d.deep_dive_id,
                "insert",
                d.created_by,
                None,
                {"title": d.title, "kind": d.kind},
                None,
            )
        return d

    def get_deep_dive(self, deep_dive_id: str) -> DeepDive | None:
        org = self._org()
        rows = self._fetch_all(
            f"SELECT {self._DEEP_DIVE_HEAD}, d.content_json FROM {self._ratings_joined()} "
            "WHERE d.org_id = ? AND d.deep_dive_id = ?",
            [org, org, deep_dive_id],
        )
        if not rows:
            return None
        d = self._row_to_deep_dive(rows[0][:15], rows[0][15])
        d.elements = [
            DeepDiveElement(r[0], r[1] or "drawn", int(r[2] or 1))
            for r in self._fetch_all(
                "SELECT element_id, role, maturity FROM deep_dive_element "
                "WHERE org_id = ? AND deep_dive_id = ? ORDER BY element_id",
                [org, deep_dive_id],
            )
        ]
        return d

    def list_deep_dives(
        self,
        kind: str | None = None,
        domain_id: str | None = None,
        type_id: str | None = None,
        work_package: str | None = None,
        element_id: str | None = None,
        text: str | None = None,
        min_rating: float | None = None,
        include_withdrawn: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DeepDive], int]:
        org = self._org()
        where, params = ["d.org_id = ?"], [org, org]
        if not include_withdrawn:
            where.append("d.status = 'kept'")
        if kind:
            where.append("d.kind = ?")
            params.append(kind)
        # The catalogue's lists are JSON arrays of identifiers, so an entry is found quoted.
        for column, value in (("d.domain_ids", domain_id), ("d.type_ids", type_id)):
            if value:
                where.append(f"{column} LIKE ? ESCAPE '\\'")
                params.append(self._like(json.dumps(value)))
        if work_package:
            where.append("d.work_package = ?")
            params.append(work_package)
        if element_id:
            where.append(
                "EXISTS (SELECT 1 FROM deep_dive_element AS e WHERE e.org_id = d.org_id "
                "AND e.deep_dive_id = d.deep_dive_id AND e.element_id = ?)"
            )
            params.append(element_id)
        if text and text.strip():
            where.append("(LOWER(d.title) LIKE ? ESCAPE '\\' OR LOWER(d.brief_json) LIKE ? ESCAPE '\\')")
            params += [self._like(text.strip().lower())] * 2
        if min_rating:
            where.append("r.average >= ?")
            params.append(float(min_rating))
        body = f"FROM {self._ratings_joined()} WHERE {' AND '.join(where)}"
        total = int(self._fetch_all(f"SELECT COUNT(*) {body}", params)[0][0])
        rows = self._fetch_all(
            f"SELECT {self._DEEP_DIVE_HEAD} {body} "
            f"ORDER BY COALESCE(r.average, {self._UNRATED}) DESC, d.created_at DESC"
            + self._page(limit, offset),
            params,
        )
        return [self._row_to_deep_dive(r) for r in rows], total

    def deep_dives_for_elements(self, element_ids: list[str], limit: int = 20) -> list[DeepDive]:
        ids = sorted({i for i in element_ids if i})[:500]
        if not ids:
            return []
        org = self._org()
        rows = self._fetch_all(
            f"SELECT {self._DEEP_DIVE_HEAD} FROM {self._ratings_joined()} "
            "WHERE d.org_id = ? AND d.status = 'kept' AND EXISTS (SELECT 1 FROM deep_dive_element AS e "
            f"WHERE e.org_id = d.org_id AND e.deep_dive_id = d.deep_dive_id AND e.element_id IN ({self._marks(ids)})) "
            f"ORDER BY COALESCE(r.average, {self._UNRATED}) DESC, d.created_at DESC" + self._page(limit),
            [org, org, *ids],
        )
        return [self._row_to_deep_dive(r) for r in rows]

    def set_deep_dive_status(self, deep_dive_id: str, status: str, actor: str) -> None:
        if status not in DEEP_DIVE_STATUSES:
            raise ValueError(f"a deep dive is {' or '.join(DEEP_DIVE_STATUSES)}, not {status!r}")
        held = self.get_deep_dive(deep_dive_id)
        if held is None:
            raise NotFoundError(deep_dive_id, "deep dive")
        with self.transaction():
            self._execute(
                "UPDATE deep_dive SET status = ? WHERE org_id = ? AND deep_dive_id = ?",
                [status, self._org(), deep_dive_id],
            )
            self._log(
                "deep_dive", deep_dive_id, status, actor, {"status": held.status}, {"status": status}, None
            )

    def rate_deep_dive(self, rating: DeepDiveRating) -> None:
        stars = int(rating.stars)
        if not 1 <= stars <= 5:
            raise ValueError(f"a rating is one to five stars, not {rating.stars!r}")
        if not rating.rated_by:
            raise ValueError("a rating names who gave it")
        if self.get_deep_dive(rating.deep_dive_id) is None:
            raise NotFoundError(rating.deep_dive_id, "deep dive")
        org = self._org()
        with self.transaction():
            self._put_rows(
                "deep_dive_rating",
                ["org_id", "deep_dive_id", "rated_by"],
                [[rating.deep_dive_id, rating.rated_by, stars, rating.comment or None, _now(), org]],
            )

    def clear_deep_dive_rating(self, deep_dive_id: str, rated_by: str) -> bool:
        """A rating is its person's judgement, so they may take it back; the deep dive stays."""
        org = self._org()
        where = "WHERE org_id = ? AND deep_dive_id = ? AND rated_by = ?"
        held = self._fetch_all(f"SELECT stars FROM deep_dive_rating {where}", [org, deep_dive_id, rated_by])
        if not held:
            return False
        with self.transaction():
            self._execute(f"DELETE FROM deep_dive_rating {where}", [org, deep_dive_id, rated_by])
            self._log(
                "deep_dive",
                deep_dive_id,
                "unrate",
                rated_by,
                {"rated_by": rated_by, "stars": int(held[0][0])},
                None,
                None,
            )
        return True

    def deep_dive_ratings(self, deep_dive_id: str) -> list[DeepDiveRating]:
        rows = self._fetch_all(
            "SELECT deep_dive_id, rated_by, stars, comment, rated_at FROM deep_dive_rating "
            "WHERE org_id = ? AND deep_dive_id = ? ORDER BY rated_at DESC",
            [self._org(), deep_dive_id],
        )
        return [DeepDiveRating(r[0], r[1], int(r[2]), r[3] or "", r[4]) for r in rows]

    # ---------------------------------------------------------------- sql
    #: The content tables a branch overlays, with the branch table holding the overlay rows and
    #: the key the two are matched on. A reader's own SQL is scoped by all three the same way
    #: every other read is.
    _OVERLAID = {
        "element": ("branch_element", "element_id"),
        "relationship": ("branch_relationship", "relationship_id"),
        "element_link": ("branch_link", "element_id"),
    }

    def _overlay_cte(self, table: str, branch: str) -> str:
        """One content table as the current branch sees it: main, minus what the branch
        overrides, plus what the branch adds."""
        overlay, key = self._OVERLAID[table]
        org, b = self._qo(), self._q(branch)
        cols = ", ".join(c for c in table_columns(table) if c != "op")
        op = " AND op = 'upsert'" if overlay != "branch_link" else ""
        return (
            f"{table} AS (SELECT {cols} FROM {table} AS m WHERE m.org_id = {org} AND NOT EXISTS "
            f"(SELECT 1 FROM {overlay} AS v WHERE v.org_id = {org} AND v.branch_id = {b} "
            f"AND v.{key} = m.{key}) "
            f"UNION ALL SELECT {cols} FROM {overlay} WHERE org_id = {org} AND branch_id = {b}{op})"
        )

    def _scope_ctes(self) -> str:
        """Common table expressions that shadow the content tables with what the reader is
        standing on — the current organisation, the current branch's overlay, and the
        metamodel version the organisation applies — so a reader's own SQL answers for where
        the reader is rather than for main.

        A reader on a branch used to get main's rows back from `ea sql` and from the agent's
        SQL tool with nothing saying so, which made the one tool meant for checking a branch
        the one tool that could not see it.
        """
        org = self._qo()
        branch = current_branch()
        ctes = [
            self._overlay_cte(t, branch)
            if (branch != MAIN and t in self._OVERLAID)
            else f"{t} AS (SELECT * FROM {t} WHERE org_id = {org})"
            for t in ORG_TABLES
        ]
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

    # ----------------------------------------------------------------- feeds
    _FEED_COLUMNS = (
        "feed_id",
        "name",
        "source_system",
        "elements_table",
        "relationships_table",
        "links_table",
        "mapping_yaml",
        "target_branch",
        "clear_after",
        "enabled",
        "schedule",
        "schedule_timezone",
        "last_run_at",
        "last_run_status",
        "last_run_summary",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    )

    def save_feed(self, feed: SourceFeed, actor: str) -> SourceFeed:
        feed.feed_id = feed.feed_id or new_id("feed")
        now, org = _now(), self._org()
        with self._lock:
            existing = self.get_feed(feed.feed_id)
            feed.created_at = existing.created_at if existing else now
            feed.created_by = existing.created_by if existing else actor
            feed.updated_at, feed.updated_by = now, actor
            self._execute("DELETE FROM source_feed WHERE org_id = ? AND feed_id = ?", [org, feed.feed_id])
            self._insert_rows("source_feed", [self._feed_values(feed) + [org]])
            self._log("source_feed", feed.feed_id, "save", actor, None, self._public(feed), None)
        return feed

    def _feed_values(self, f: SourceFeed) -> list[Any]:
        return [
            f.feed_id,
            f.name or None,
            f.source_system or None,
            f.elements_table or None,
            f.relationships_table or None,
            f.links_table or None,
            f.mapping_yaml or None,
            f.target_branch or None,
            bool(f.clear_after),
            bool(f.enabled),
            f.schedule or None,
            f.schedule_timezone or None,
            f.last_run_at,
            f.last_run_status or None,
            f.last_run_summary or None,
            f.created_at,
            f.created_by or None,
            f.updated_at,
            f.updated_by or None,
        ]

    def _row_to_feed(self, r: tuple) -> SourceFeed:
        return SourceFeed(
            feed_id=r[0],
            name=r[1] or "",
            source_system=r[2] or "",
            elements_table=r[3] or "",
            relationships_table=r[4] or "",
            links_table=r[5] or "",
            mapping_yaml=r[6] or "",
            target_branch=r[7] or "",
            clear_after=bool(r[8]),
            enabled=bool(r[9]),
            schedule=r[10] or "",
            schedule_timezone=r[11] or "",
            last_run_at=r[12],
            last_run_status=r[13] or "",
            last_run_summary=r[14] or "",
            created_at=r[15],
            created_by=r[16] or "",
            updated_at=r[17],
            updated_by=r[18] or "",
        )

    def list_feeds(self) -> list[SourceFeed]:
        rows = self._fetch_all(
            f"SELECT {', '.join(self._FEED_COLUMNS)} FROM source_feed WHERE org_id = ? ORDER BY name, feed_id",
            [self._org()],
        )
        return [self._row_to_feed(r) for r in rows]

    def get_feed(self, feed_id: str) -> SourceFeed | None:
        rows = self._fetch_all(
            f"SELECT {', '.join(self._FEED_COLUMNS)} FROM source_feed WHERE org_id = ? AND feed_id = ?",
            [self._org(), feed_id],
        )
        return self._row_to_feed(rows[0]) if rows else None

    def delete_feed(self, feed_id: str, actor: str) -> None:
        org = self._org()
        with self._lock:
            before = self.get_feed(feed_id)
            self._execute("DELETE FROM source_feed WHERE org_id = ? AND feed_id = ?", [org, feed_id])
            if before is not None:
                self._log("source_feed", feed_id, "delete", actor, self._public(before), None, None)

    # ------------------------------------------------------ import history
    _RUN_COLUMNS = (
        "run_id",
        "source_system",
        "trigger_kind",
        "feed_id",
        "feed_name",
        "actor",
        "branch_id",
        "inputs",
        "mapping_yaml",
        "started_at",
        "finished_at",
        "status",
        "summary",
        "message",
        "elements_created",
        "elements_updated",
        "elements_unchanged",
        "elements_retired",
        "relationships_created",
        "relationships_updated",
        "relationships_unchanged",
        "relationships_retired",
        "links_loaded",
        "error_count",
        "warning_count",
        "issues_json",
        "issue_counts_json",
        "truncated",
    )

    def record_run(self, run: ImportRun) -> ImportRun:
        run.run_id = run.run_id or new_id("run")
        with self._lock:
            self._insert_rows("import_run", [self._run_values(run) + [self._org()]])
        return run

    def _run_values(self, r: ImportRun) -> list[Any]:
        return [
            r.run_id,
            r.source_system or None,
            r.trigger or None,
            r.feed_id or None,
            r.feed_name or None,
            r.actor or None,
            r.branch_id or None,
            json.dumps(r.inputs, ensure_ascii=False),
            r.mapping_yaml or None,
            r.started_at,
            r.finished_at,
            r.status or None,
            r.summary or None,
            r.message or None,
            int(r.elements_created),
            int(r.elements_updated),
            int(r.elements_unchanged),
            int(r.elements_retired),
            int(r.relationships_created),
            int(r.relationships_updated),
            int(r.relationships_unchanged),
            int(r.relationships_retired),
            int(r.links_loaded),
            int(r.error_count),
            int(r.warning_count),
            json.dumps([vars(i) for i in r.issues], ensure_ascii=False, default=str),
            _dumps(r.issue_counts),
            bool(r.truncated),
        ]

    @staticmethod
    def _row_to_run(r: tuple) -> ImportRun:
        return ImportRun(
            run_id=r[0],
            source_system=r[1] or "",
            trigger=r[2] or "",
            feed_id=r[3] or "",
            feed_name=r[4] or "",
            actor=r[5] or "",
            branch_id=r[6] or "",
            inputs=_string_list(r[7]),
            mapping_yaml=r[8] or "",
            started_at=r[9],
            finished_at=r[10],
            status=r[11] or "",
            summary=r[12] or "",
            message=r[13] or "",
            elements_created=r[14] or 0,
            elements_updated=r[15] or 0,
            elements_unchanged=r[16] or 0,
            elements_retired=r[17] or 0,
            relationships_created=r[18] or 0,
            relationships_updated=r[19] or 0,
            relationships_unchanged=r[20] or 0,
            relationships_retired=r[21] or 0,
            links_loaded=r[22] or 0,
            error_count=r[23] or 0,
            warning_count=r[24] or 0,
            issues=_issues(r[25]),
            issue_counts=_counts(r[26]),
            truncated=bool(r[27]),
        )

    def runs(self, limit: int, offset: int, feed_id: str = "") -> list[ImportRun]:
        where, params = "org_id = ?", [self._org()]
        if feed_id:
            where, params = where + " AND feed_id = ?", [*params, feed_id]
        rows = self._fetch_all(
            f"SELECT {', '.join(self._RUN_COLUMNS)} FROM import_run WHERE {where} "
            # `run_id` breaks the tie: two runs of the same second would otherwise come back
            # in whatever order the engine felt like, and a page boundary would drop one.
            f"ORDER BY started_at DESC, run_id DESC LIMIT {int(limit)} OFFSET {int(offset)}",
            params,
        )
        return [self._row_to_run(r) for r in rows]

    def get_run(self, run_id: str) -> ImportRun | None:
        rows = self._fetch_all(
            f"SELECT {', '.join(self._RUN_COLUMNS)} FROM import_run WHERE org_id = ? AND run_id = ?",
            [self._org(), run_id],
        )
        return self._row_to_run(rows[0]) if rows else None

    def count_runs(self, feed_id: str = "") -> int:
        where, params = "org_id = ?", [self._org()]
        if feed_id:
            where, params = where + " AND feed_id = ?", [*params, feed_id]
        rows = self._fetch_all(f"SELECT COUNT(*) FROM import_run WHERE {where}", params)
        return int(rows[0][0]) if rows else 0

    # ------------------------------------------------------------- staging
    def _staging(self, table: str) -> str:
        """`<prefix>_staging.<table>`, refusing anything that is not a plain identifier.

        A staging table is named by configuration rather than by the code, and it goes into a
        statement as a name rather than as a bound value — so it is checked here, where the
        statement is built, and not trusted from wherever it came."""
        if not _STAGING_NAME.fullmatch(table or ""):
            raise ValueError(f"{table!r} is not a staging table name: use letters, digits and _")
        return f"{staging_schema(self.schema_prefix)}.{table}"

    def staging_tables(self) -> list[str]:
        rows = self._fetch_all(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ? ORDER BY table_name",
            [staging_schema(self.schema_prefix)],
        )
        return [r[0] for r in rows]

    def read_staging(self, table: str, limit: int, offset: int) -> pd.DataFrame:
        return self._fetch_df(f"SELECT * FROM {self._staging(table)} LIMIT {int(limit)} OFFSET {int(offset)}")

    def clear_staging(self, table: str) -> int:
        name = self._staging(table)
        with self._lock:
            held = self._fetch_all(f"SELECT COUNT(*) FROM {name}")[0][0]
            self._execute(f"DELETE FROM {name}")
        return int(held)

    def _qualified_escape(self, bare: str) -> str:
        """A schema or catalog name in the reader's query that would step around the scope.

        The scoping below shadows the content tables by their **bare** names, so `element`
        answers for the reader's organisation and branch. A qualified name — `ea_content.element`,
        or the catalog before it — resolves to the base table instead and no shadow applies,
        which reads every organisation's rows, not only the reader's. Naming a schema is
        refused rather than rewritten: there is nothing a reader's query needs from one that
        the bare name does not already give, and the system catalogues are how the schema
        names are found in the first place.
        """
        for name in (*schemas(self.schema_prefix), *_SYSTEM_SCHEMAS):
            if re.search(rf"\b{re.escape(name)}\s*\.", bare, re.IGNORECASE):
                return name
        return ""

    def query(
        self, sql: str, params: list[Any] | None = None, limit: int = 1000, scoped: bool = True
    ) -> pd.DataFrame:
        stripped = re.sub(r"--[^\n]*", "", sql).strip().rstrip(";").strip()
        # A word inside a string literal is a value ('merge' is a target state), not a statement.
        bare = re.sub(r"'(?:[^']|'')*'", "''", stripped)
        if ";" in bare or not _READ_ONLY_RE.match(bare) or _FORBIDDEN_RE.search(bare):
            raise ValueError("only a single read-only SELECT/WITH statement is allowed")
        if scoped and (named := self._qualified_escape(bare)):
            raise ValueError(
                f"name the table on its own, not as {named}.<table>: a qualified name reads past "
                f"the organisation and branch this query answers for"
            )
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
