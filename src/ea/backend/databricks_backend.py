"""Databricks engine: Delta tables in a Unity Catalog schema, reached through a SQL warehouse.

The same DDL and the same reads and writes as DuckDB (`sql_backend.py`); what
this module adds is the warehouse. Three things differ from a file on a
workstation, and each is handled here and nowhere else:

* **A statement is a round trip.** The connector accepts at most 255
  parameter markers per statement, so a bulk load is one `MERGE` per batch
  with the rows written as SQL literals, never one insert per row.
* **The dialect.** `VARCHAR` is `STRING`, an added column is `ADD COLUMNS (…)`
  after a `DESCRIBE` says it is missing, and a string literal escapes the
  backslash the way Spark reads it.
* **The session.** Credentials come from the environment the way every
  Databricks SDK client finds them (the app's service principal on Databricks
  Apps, a token or a profile on a workstation); a session that expires is
  reopened once. A warehouse without recursive queries answers the trace
  in process instead, over the same edges.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ea.backend.sql import MIGRATIONS, column_types
from ea.backend.sql_backend import SqlBackend, chunks

log = logging.getLogger(__name__)

# The portable DDL spelt the way Delta wants it.
_TYPES = {"VARCHAR": "STRING", "INTEGER": "INT"}
_TYPE_RE = re.compile(r"\b(VARCHAR|INTEGER)\b")
#: rows per MERGE or INSERT statement (literals, so the marker limit does not apply; the
#: statement stays well under the warehouse's text limit at this size)
BATCH_ROWS = 200
_RECURSION_UNSUPPORTED = ("RECURSIVE", "RECURSION", "PARSE_SYNTAX_ERROR", "UNSUPPORTED")


def spark_literal(value: Any, sql_type: str) -> str:
    """A value as a SQL literal Spark reads back unchanged.

    Strings double the quote and escape the backslash (Spark treats `\\` as an
    escape character inside a literal); a missing value is cast so that a batch
    whose column is null throughout still carries the column's type.
    """
    if value is None:
        return f"CAST(NULL AS {_TYPES.get(sql_type, sql_type)})"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
    if hasattr(value, "to_pydatetime"):  # a pandas Timestamp
        return spark_literal(value.to_pydatetime(), sql_type)
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def to_delta_ddl(ddl: str) -> str:
    """The portable CREATE TABLE in Delta's dialect."""
    return _TYPE_RE.sub(lambda m: _TYPES[m.group(1)], ddl)


def _naive_utc(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class DatabricksBackend(SqlBackend):
    IN_CHUNK = 200  # under the connector's 255 markers, with room for the other parameters
    STRING_TYPE = "STRING"

    def __init__(
        self,
        http_path: str,
        catalog: str,
        schema: str = "ea",
        connect: Callable[[], Any] | None = None,
    ):
        """`connect` returns a DB-API connection; by default the SQL connector authenticated from
        the environment. It is a parameter so the dialect can be proved on another engine."""
        super().__init__()
        self.http_path = http_path
        self.catalog = catalog
        self.schema = schema
        self._connect = connect or self._connect_warehouse
        self._conn = self._connect()
        self._recursive_sql: bool | None = None  # unknown until the first trace
        self.init_schema()

    @classmethod
    def from_settings(cls, settings: Any) -> DatabricksBackend:
        http_path = settings.databricks_http_path or (
            f"/sql/1.0/warehouses/{settings.databricks_warehouse_id}"
            if settings.databricks_warehouse_id
            else ""
        )
        if not http_path:
            raise ValueError("EA_BACKEND=databricks needs DATABRICKS_WAREHOUSE_ID (or DATABRICKS_HTTP_PATH)")
        if not settings.databricks_catalog:
            raise ValueError(
                "EA_BACKEND=databricks needs EA_CATALOG, the Unity Catalog catalog of the schema"
            )
        return cls(http_path, settings.databricks_catalog, settings.databricks_schema or "ea")

    def _connect_warehouse(self) -> Any:
        from databricks import sql as dbsql  # the `databricks` extra
        from databricks.sdk.core import Config

        cfg = Config()  # DATABRICKS_HOST and the credentials: the app's service principal, a token, a profile
        host = re.sub(r"^https?://", "", cfg.host or "").rstrip("/")
        conn = dbsql.connect(
            server_hostname=host,
            http_path=self.http_path,
            credentials_provider=lambda: cfg.authenticate,
            catalog=self.catalog,
            schema=self.schema,
            user_agent_entry="ea-repository",
        )
        with conn.cursor() as cur:
            try:  # the bundle creates the schema; a principal without CREATE SCHEMA still works in it
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.catalog}.{self.schema}")
            except Exception as exc:  # noqa: BLE001
                log.debug("could not create schema %s.%s (%s); using it as it is", self.catalog, self.schema, exc)
            cur.execute(f"USE {self.catalog}.{self.schema}")
            cur.execute("SET TIME ZONE 'UTC'")
        return conn

    # ------------------------------------------------------------ engine hooks
    def _run(self, sql: str, params: list[Any] | None, fetch: bool) -> tuple[list[tuple], list[str]]:
        """One statement, under the lock; a session the warehouse closed is reopened once."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(sql, params or None)
                        if not fetch:
                            return [], []
                        rows = [tuple(_naive_utc(v) for v in row) for row in cur.fetchall()]
                        names = [d[0] for d in (cur.description or [])]
                        return rows, names
                except Exception as exc:  # noqa: BLE001 — only a closed session is retried
                    if attempt == 2 or not self._session_gone(exc):
                        raise
                    log.warning("warehouse session closed (%s); reconnecting", exc)
                    self._conn = self._connect()
        return [], []  # unreachable

    def _session_gone(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            not getattr(self._conn, "open", True)
            or "session" in text
            and ("expired" in text or "invalid" in text or "closed" in text or "not found" in text)
        )

    def _execute(self, sql: str, params: list[Any] | None = None) -> None:
        self._run(sql, params, fetch=False)

    def _fetch_all(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        return self._run(sql, params, fetch=True)[0]

    def _fetch_df(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        rows, names = self._run(sql, params, fetch=True)
        return pd.DataFrame(rows, columns=names)

    def _values(self, table: str, columns: list[str], rows: list[list[Any]]) -> str:
        types = column_types(table)
        return ", ".join(
            "(" + ", ".join(spark_literal(v, types[c]) for c, v in zip(columns, row, strict=True)) + ")"
            for row in rows
        )

    def _insert_rows(self, table: str, rows: list[list[Any]]) -> None:
        columns = list(column_types(table))
        for batch in chunks(rows, BATCH_ROWS):
            self._execute(f"INSERT INTO {table} VALUES {self._values(table, columns, batch)}")

    def _replace_rows(self, table: str, columns: list[str], rows: list[list[Any]], keys: list[str]) -> None:
        """One MERGE per batch: matched rows are rewritten column by column, new rows appended."""
        on = " AND ".join(f"t.{k} = s.{k}" for k in keys)
        update = ", ".join(f"{c} = s.{c}" for c in columns if c not in keys)
        insert_cols = ", ".join(columns)
        insert_vals = ", ".join(f"s.{c}" for c in columns)
        for batch in chunks(rows, BATCH_ROWS):
            self._execute(
                f"MERGE INTO {table} AS t USING (SELECT * FROM (VALUES {self._values(table, columns, batch)}) "
                f"AS v({insert_cols})) AS s ON {on} "
                f"WHEN MATCHED THEN UPDATE SET {update} "
                f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
            )

    def _create_table(self, ddl: str) -> None:
        self._execute(to_delta_ddl(ddl))

    def _columns_of(self, table: str) -> set[str]:
        names = set()
        for row in self._fetch_all(f"DESCRIBE {table}"):
            name = str(row[0] or "").strip()
            if name and not name.startswith("#"):
                names.add(name)
        return names

    def _add_missing_columns(self) -> None:
        described: dict[str, set[str]] = {}
        for table, column, dtype in MIGRATIONS:
            if table not in described:
                described[table] = self._columns_of(table)
            if column not in described[table]:
                self._execute(f"ALTER TABLE {table} ADD COLUMNS ({column} {_TYPES.get(dtype, dtype)})")
                described[table].add(column)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 — closing a closed session is not an error worth raising
                pass

    # -------------------------------------------------------------- graph
    def _trace_frame(self, element_id: str, direction: str, max_depth: int) -> pd.DataFrame:
        """The recursive query where the warehouse runs it; the same walk in process where it does not."""
        if self._recursive_sql is not False:
            try:
                frame = super()._trace_frame(element_id, direction, max_depth)
                self._recursive_sql = True
                return frame
            except Exception as exc:  # noqa: BLE001 — an engine without WITH RECURSIVE says so in its error
                if self._recursive_sql or not any(w in str(exc).upper() for w in _RECURSION_UNSUPPORTED):
                    raise
                log.warning("the warehouse refused the recursive trace (%s); tracing in process", exc)
                self._recursive_sql = False
        return self._trace_in_process(element_id, direction, max_depth)
