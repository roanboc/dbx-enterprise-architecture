"""Lakebase engine: the same store, over the Postgres protocol.

Lakebase is the platform's Postgres database, so nothing here translates a
dialect: the portable DDL of `sql.py` is Postgres's own, and what an engine
adds (decision 0011) is how it connects, runs a statement and lands rows.

* **The connection.** One connection under the lock, opened by a callable so
  a test can hand in any Postgres. On the platform the callable signs in the
  way Lakebase asks: the instance named by `EA_LAKEBASE_INSTANCE` is looked up
  through the Databricks SDK for its host, and an OAuth token generated for it
  is the password; the identity is the app's service principal on Databricks
  Apps, or whoever the SDK signs in as on a workstation. Anywhere else the
  standard `PG*` variables or `EA_POSTGRES_DSN` reach any Postgres, the way
  libpq reads them.
* **A token lives an hour, and a connection may be closed** by the platform
  or the network in between: a statement refused because the connection is
  gone is retried once on a new connection, signed in afresh.
* **The statements.** `?` markers become `%s`; rows land as multi-row inserts,
  a bulk replace as a delete and an insert in one transaction; a reader's own
  query runs in a read-only transaction; the schema is created (where the
  principal may) and entered on every connection, with the session in UTC.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Callable
from typing import Any

import pandas as pd
import psycopg

from ea.backend.sql_backend import SqlBackend, chunks

log = logging.getLogger(__name__)

#: rows per INSERT statement: Postgres binds up to 65,535 values a statement and the widest table has 24 columns
BATCH_ROWS = 500
#: the database every Lakebase instance is created with
DEFAULT_DATABASE = "databricks_postgres"
_LITERAL_OR_MARK = re.compile(r"'(?:[^']|'')*'|(\?)")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# What libpq says when the server or the network dropped the connection under us.
_CONNECTION_GONE = (
    "closed",
    "terminat",
    "ssl syscall",
    "eof detected",
    "connection reset",
    "broken pipe",
    "could not receive",
    "not open",
)


def to_pg(sql: str, params: list[Any] | None = None) -> str:
    """The statement as psycopg reads it: `%s` markers, and a percent doubled when values are bound.

    A `?` inside a string literal is text and stays; a `%` anywhere would be read as a
    format directive once parameters are bound, so it is escaped then and left alone otherwise.
    """
    if params:
        sql = sql.replace("%", "%%")
    return _LITERAL_OR_MARK.sub(lambda m: "%s" if m.group(1) else m.group(0), sql)


def _workspace_client() -> Any:
    from databricks.sdk import WorkspaceClient  # the `databricks` extra

    return WorkspaceClient()


def connect_to_instance(settings: Any, workspace: Callable[[], Any] | None = None) -> psycopg.Connection[Any]:
    """A connection to the named Lakebase instance, signed in as the SDK's identity with a fresh OAuth token.

    The host is the instance's read-write endpoint unless `PGHOST` names it; the user is `PGUSER`,
    else the app's service principal (`DATABRICKS_CLIENT_ID` on Databricks Apps), else whoever the
    SDK signs in as; the password is a token the SDK generates for the instance, good for an hour.
    """
    client = (workspace or _workspace_client)()
    instance = settings.lakebase_instance
    host = settings.pg_host or client.database.get_database_instance(name=instance).read_write_dns
    user = settings.pg_user or os.environ.get("DATABRICKS_CLIENT_ID") or client.current_user.me().user_name
    credential = client.database.generate_database_credential(
        request_id=str(uuid.uuid4()), instance_names=[instance]
    )
    return psycopg.connect(
        host=host,
        port=int(settings.pg_port or 5432),
        dbname=settings.pg_database or DEFAULT_DATABASE,
        user=user,
        password=credential.token,
        sslmode=settings.pg_sslmode or "require",
        application_name="ea-repository",
        autocommit=True,
    )


class LakebaseBackend(SqlBackend):
    def __init__(self, connect: Callable[[], psycopg.Connection[Any]], schema: str = "ea"):
        """`connect` opens a psycopg connection in autocommit mode; the session is prepared the same
        way whichever Postgres it reaches (the schema, the search path, the time zone)."""
        super().__init__()
        if not _IDENTIFIER.fullmatch(schema or ""):
            raise ValueError(f"the schema name {schema!r} must be a plain SQL identifier")
        self.schema = schema
        self._open = connect
        self._conn = self._connect()
        self.init_schema()

    @classmethod
    def from_dsn(cls, dsn: str, schema: str = "ea") -> LakebaseBackend:
        """Any Postgres, from a libpq URL or key=value string (a test server, a workstation, CI)."""
        return cls(lambda: psycopg.connect(dsn, autocommit=True), schema)

    @classmethod
    def from_settings(cls, settings: Any, workspace: Callable[[], Any] | None = None) -> LakebaseBackend:
        schema = settings.store_schema or "ea"
        if settings.lakebase_instance:
            return cls(lambda: connect_to_instance(settings, workspace), schema)
        if not (settings.pg_dsn or settings.pg_host):
            raise ValueError(
                "EA_BACKEND=lakebase needs EA_LAKEBASE_INSTANCE (the instance the platform's identity "
                "signs in to), or PGHOST or EA_POSTGRES_DSN for any Postgres"
            )
        return cls(lambda: psycopg.connect(settings.pg_dsn, autocommit=True), schema)

    # ---------------------------------------------------------------- session
    def _connect(self) -> psycopg.Connection[Any]:
        conn = self._open()
        self._prepare_session(conn)
        return conn

    def _prepare_session(self, conn: psycopg.Connection[Any]) -> None:
        """The schema if it can be made, then the search path and the time zone; on every connection."""
        with conn.cursor() as cur:
            try:  # the app's principal may create in its database; another principal works in what exists
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            except psycopg.Error as exc:
                log.debug("could not create schema %s (%s); using it as it is", self.schema, exc)
            cur.execute(f"SET search_path TO {self.schema}")
            cur.execute("SET TIME ZONE 'UTC'")

    def _connection_gone(self, exc: Exception) -> bool:
        """The connection is closed or broken, or the error says the server or the network dropped it."""
        if self._conn.closed or self._conn.broken:
            return True
        text = str(exc).lower()
        return any(word in text for word in _CONNECTION_GONE)

    # ------------------------------------------------------------ engine hooks
    def _run(self, sql: str, params: list[Any] | None, fetch: bool) -> tuple[list[tuple], list[str]]:
        """One statement, under the lock; a connection the platform closed is reopened once."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(to_pg(sql, params), params or None)
                        if not fetch:
                            return [], []
                        return cur.fetchall(), [d.name for d in (cur.description or [])]
                except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
                    if attempt == 2 or not self._connection_gone(exc):
                        raise
                    log.warning("the connection was closed (%s); signing in again", exc)
                    self._conn = self._connect()
        return [], []  # unreachable

    def _execute(self, sql: str, params: list[Any] | None = None) -> None:
        self._run(sql, params, fetch=False)

    def _fetch_all(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        return self._run(sql, params, fetch=True)[0]

    def _fetch_df(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        rows, names = self._run(sql, params, fetch=True)
        return pd.DataFrame(rows, columns=names)

    @staticmethod
    def _values(rows: list[list[Any]]) -> tuple[str, list[Any]]:
        """The VALUES list of a multi-row insert and its parameters, flattened."""
        one = "(" + ", ".join("?" for _ in rows[0]) + ")"
        return ", ".join(one for _ in rows), [v for row in rows for v in row]

    def _insert_rows(self, table: str, rows: list[list[Any]]) -> None:
        for batch in chunks(rows, BATCH_ROWS):
            values, params = self._values(batch)
            self._execute(f"INSERT INTO {table} VALUES {values}", params)

    def _replace_rows(self, table: str, columns: list[str], rows: list[list[Any]], keys: list[str]) -> None:
        """The keyed rows deleted and the incoming rows inserted, in one transaction per call."""
        if not rows:
            return
        key_tuple = "(" + ", ".join(keys) + ")"
        positions = [columns.index(k) for k in keys]
        with self._lock, self._conn.transaction():
            for batch in chunks(rows, BATCH_ROWS):
                key_values, key_params = self._values([[row[i] for i in positions] for row in batch])
                self._execute(f"DELETE FROM {table} WHERE {key_tuple} IN ({key_values})", key_params)
                values, params = self._values(batch)
                self._execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES {values}", params)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except psycopg.Error:  # closing a closed connection is not an error worth raising
                pass

    # ---------------------------------------------------------------- sql
    def query(self, sql: str, params: list[Any] | None = None, limit: int = 1000) -> pd.DataFrame:
        """A reader's own SQL, in a transaction the server itself holds to reads."""
        with self._lock, self._conn.transaction():
            self._execute("SET LOCAL transaction_read_only = on")
            return super().query(sql, params, limit)


__all__ = ["BATCH_ROWS", "DEFAULT_DATABASE", "LakebaseBackend", "connect_to_instance", "to_pg"]
