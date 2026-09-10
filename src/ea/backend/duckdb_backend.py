"""DuckDB engine: one file, zero infrastructure, the same DDL as Delta.

Everything the store does is in `sql_backend.py`; this module only knows how
to talk to DuckDB — a connection, a lock (the file is single-writer), frames
registered as tables for the bulk loads, and the one DDL form DuckDB has that
Delta does not (`ADD COLUMN IF NOT EXISTS`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ea.backend.sql import MIGRATIONS
from ea.backend.sql_backend import SqlBackend, new_id

__all__ = ["DuckDBBackend", "new_id"]


class DuckDBBackend(SqlBackend):
    def __init__(self, path: str | Path = ":memory:"):
        super().__init__()
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(self.path)
        self.init_schema()

    # ------------------------------------------------------------ engine hooks
    def _execute(self, sql: str, params: list[Any] | None = None) -> None:
        with self._lock:
            self._conn.execute(sql, params or [])

    def _fetch_df(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        with self._lock:
            return self._conn.execute(sql, params or []).df()

    def _fetch_all(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql, params or []).fetchall()

    def _insert_rows(self, table: str, rows: list[list[Any]]) -> None:
        if not rows:
            return
        marks = ", ".join("?" for _ in rows[0])
        with self._lock:
            self._conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)

    def _replace_rows(self, table: str, columns: list[str], rows: list[list[Any]], keys: list[str]) -> None:
        """A frame registered as a table, the keyed rows deleted, the frame appended: one round trip each."""
        if not rows:
            return
        incoming = f"_incoming_{table}"
        match = " AND ".join(f"{table}.{k} = {incoming}.{k}" for k in keys)
        with self._lock:
            self._conn.register(incoming, pd.DataFrame(rows, columns=columns))
            try:
                self._conn.execute(
                    f"DELETE FROM {table} WHERE EXISTS (SELECT 1 FROM {incoming} WHERE {match})"
                )
                self._conn.execute(f"INSERT INTO {table} SELECT {', '.join(columns)} FROM {incoming}")
            finally:
                self._conn.unregister(incoming)

    def _add_missing_columns(self) -> None:
        for table, column, dtype in MIGRATIONS:  # older files: add what shipped later
            self._execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {dtype}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
