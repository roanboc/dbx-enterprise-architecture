"""A SQL warehouse played by DuckDB, so the Databricks dialect is proved on every change.

`DatabricksBackend` takes a `connect` callable that returns a DB-API connection.
This one wraps an in-memory DuckDB and reads the statements the way a Spark
warehouse would: Delta's `ADD COLUMNS (…)` and `SET TIME ZONE` are translated,
and string literals are unescaped as Spark unescapes them, so the backslash the
backend doubles for Spark arrives in the row as one backslash — as it would on
the platform. Everything else (`STRING`, `MERGE INTO`, `DESCRIBE`, `INSTR`,
`MIN_BY`, `WITH RECURSIVE`) DuckDB reads as written.
"""

from __future__ import annotations

import re
import threading
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
        return "SELECT 1"
    sql = _ADD_COLUMNS_RE.sub(lambda m: f"ADD COLUMN {m.group(1)} {m.group(2)}", sql)
    if "\\" in sql:
        sql = _LITERAL_RE.sub(_unescape, sql)
    return sql


class FakeCursor:
    def __init__(self, conn: duckdb.DuckDBPyConnection, log: list[str]):
        self._conn = conn
        self._log = log
        self.description: list[tuple] | None = None
        self._result: duckdb.DuckDBPyConnection | None = None

    def execute(self, sql: str, parameters: Any = None) -> None:
        self._log.append(sql)
        self._result = self._conn.execute(spark_to_duckdb(sql), list(parameters or []))
        self.description = self._result.description

    def fetchall(self) -> list[tuple]:
        return self._result.fetchall() if self._result is not None else []

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
        self.open = True

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._conn, self.statements)

    def close(self) -> None:
        self.open = False
        self._conn.close()


def connect_fake_warehouse() -> FakeWarehouseConnection:
    return FakeWarehouseConnection()
