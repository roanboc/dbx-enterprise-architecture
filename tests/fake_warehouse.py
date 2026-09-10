"""A SQL warehouse played by DuckDB, so the Databricks dialect is proved on every change.

`DatabricksBackend` takes a `connect` callable that returns a DB-API connection.
This one wraps an in-memory DuckDB and reads the statements the way a Spark
warehouse would: Delta's `ADD COLUMNS (…)` and `SET TIME ZONE` are translated,
and string literals are unescaped as Spark unescapes them, so the backslash the
backend doubles for Spark arrives in the row as one backslash and `\'` as a
quote — as they would on the platform. Once the session has set a time zone,
timestamps come back zone-aware, as the connector returns them. Everything else
(`STRING`, `MERGE INTO`, `DESCRIBE`, `INSTR`, `MIN_BY`, `WITH RECURSIVE`,
`CREATE SCHEMA`, `USE`) DuckDB reads as written.
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime
from typing import Any

import duckdb

_ADD_COLUMNS_RE = re.compile(r"ADD COLUMNS \((\w+) (\w+)\)", re.IGNORECASE)
_LITERAL_RE = re.compile(r"'((?:[^'\\]|\\.|'')*)'")
_ESCAPES = {"\\\\": "\\", "\\'": "'", "\\n": "\n", "\\t": "\t", "\\r": "\r"}


def _unescape(match: re.Match[str]) -> str:
    body = re.sub(r"\\(.)", lambda m: _ESCAPES.get("\\" + m.group(1), m.group(1)), match.group(1))
    return "'" + body.replace("'", "''").replace("''''", "''") + "'"


def spark_to_duckdb(sql: str) -> str:
    """The statement as DuckDB reads it, with Spark's own reading of literals applied first."""
    if sql.strip().upper().startswith("SET TIME ZONE"):
        return "SET TimeZone = " + sql.strip().split(" ", 3)[3]
    sql = _ADD_COLUMNS_RE.sub(lambda m: f"ADD COLUMN {m.group(1)} {m.group(2)}", sql)
    if "\\" in sql:
        sql = _LITERAL_RE.sub(_unescape, sql)
    return sql


class FakeCursor:
    def __init__(self, warehouse: FakeWarehouseConnection):
        self._warehouse = warehouse
        self._conn = warehouse._conn
        self._log = warehouse.statements
        self.description: list[tuple] | None = None
        self._result: duckdb.DuckDBPyConnection | None = None

    def execute(self, sql: str, parameters: Any = None) -> None:
        self._log.append(sql)
        if sql.strip().upper().startswith("SET TIME ZONE"):
            self._warehouse.timezone = sql.strip().split(" ", 3)[3].strip("'")
        self._result = self._conn.execute(spark_to_duckdb(sql), list(parameters or []))
        self.description = self._result.description

    def fetchall(self) -> list[tuple]:
        rows = self._result.fetchall() if self._result is not None else []
        if self._warehouse.timezone:  # the connector returns zone-aware timestamps once a zone is set
            rows = [
                tuple(
                    v.replace(tzinfo=UTC) if isinstance(v, datetime) and v.tzinfo is None else v for v in row
                )
                for row in rows
            ]
        return rows

    def close(self) -> None:
        pass

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class FakeWarehouseConnection:
    """DB-API enough for the backend: `cursor()`, `close()`, `open`; every statement is kept in `statements`."""

    def __init__(self, path: str = ":memory:"):
        self._conn = duckdb.connect(path)
        self._lock = threading.RLock()
        self.statements: list[str] = []
        self.timezone: str | None = None
        self.open = True
        self.fail_with: Exception | None = None  # raised by every cursor() until cleared: a lost session

    def cursor(self) -> FakeCursor:
        if self.fail_with is not None:
            raise self.fail_with
        return FakeCursor(self)

    def close(self) -> None:
        self.open = False
        self._conn.close()


def connect_fake_warehouse() -> FakeWarehouseConnection:
    return FakeWarehouseConnection()
