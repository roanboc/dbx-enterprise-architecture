"""The Lakebase engine: what differs from DuckDB, proved on a Postgres of the run's own.

The shared behaviour (every read, write, branch, diff and merge) runs through the
Lakebase engine in every test of the suite (`conftest.py`). What is tested here
is the engine's own part: the markers it writes, the transaction a bulk load
lands in, the session it prepares, how it signs in on the platform, and what it
does when the connection is gone.
"""

from __future__ import annotations

import types
import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from tests.conftest import SAMPLE, new_schema_name

from ea.backend.lakebase_backend import BATCH_ROWS, LakebaseBackend, to_pg
from ea.backend.sql import DDL
from ea.config import Settings
from ea.importer import import_directory
from ea.models import Element


@pytest.fixture
def schema(postgres_dsn):
    """A schema of the test's own, dropped afterwards whatever the test did to its connection."""
    name = new_schema_name()
    yield name
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")


@pytest.fixture
def store(postgres_dsn, schema, pack):
    b = LakebaseBackend.from_dsn(postgres_dsn, schema)
    b.save_pack(pack)
    yield b
    b.close()


def test_markers_are_translated_and_a_literal_is_left_alone():
    assert (
        to_pg("SELECT ? FROM t WHERE x = '?' AND y = ?", [1, 2])
        == "SELECT %s FROM t WHERE x = '?' AND y = %s"
    )
    assert to_pg("SELECT 'it''s ?', ?", ["a"]) == "SELECT 'it''s ?', %s"
    unbound = "SELECT name FROM t WHERE name LIKE '%x%'"
    assert to_pg(unbound) == unbound, "no values bound: a percent is a percent"
    assert to_pg(unbound + " AND id = ?", ["a"]) == "SELECT name FROM t WHERE name LIKE '%%x%%' AND id = %s"


def test_a_percent_in_a_readers_query_or_a_search_is_a_percent(store):
    store.insert_element(Element("X1", "capability", "100% done"), "a")
    assert len(store.query("select element_id from element where name like '%100%'")) == 1
    assert [e.element_id for e in store.find_elements(text="100%")] == ["X1"]


def test_a_bulk_load_lands_in_one_transaction(store):
    """A row the server refuses (a name is NOT NULL) rolls the whole batch back: what was there stays."""
    store.upsert_elements([Element("X1", "capability", "Before")], "t")
    with pytest.raises(psycopg.errors.NotNullViolation):
        store.upsert_elements([Element("X1", "capability", "After"), Element("X2", "capability", None)], "t")
    assert store.get_element("X1").name == "Before"
    assert store.get_element("X2") is None


def test_bulk_loads_are_multi_row_inserts_in_batches(store, registry):
    statements: list[str] = []
    real_execute = store._execute
    store._execute = lambda sql, params=None: (statements.append(sql), real_execute(sql, params))[1]
    report = import_directory(store, registry, SAMPLE, "sample")
    assert report.ok, report.summary()
    assert store.count_elements() == 47
    inserts = [s for s in statements if s.startswith("INSERT INTO element ")]
    assert inserts and all("?" in s and "VALUES (?" in s for s in inserts), "rows are bound, never literals"
    statements.clear()
    ids = [f"E{i}" for i in range(BATCH_ROWS * 2 + 1)]
    store.upsert_elements([Element(i, "capability", i) for i in ids], "t")
    assert len([s for s in statements if s.startswith("INSERT INTO element ")]) == 3
    store.upsert_elements([Element(i, "capability", i + " again") for i in ids], "t")  # every id exists now
    assert store.count_elements() == 47 + len(ids)
    assert store.get_element(ids[-1]).name == ids[-1] + " again"


def test_the_session_enters_its_own_schema_and_sets_utc(store, postgres_dsn):
    assert store._fetch_all("SHOW search_path")[0][0] == store.schema
    assert store._fetch_all("SHOW timezone")[0][0] == "UTC"
    tables = {
        r[0]
        for r in store._fetch_all(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?", [store.schema]
        )
    }
    assert tables == set(DDL)
    with psycopg.connect(postgres_dsn, autocommit=True) as other:
        public = other.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    assert not set(DDL) & {r[0] for r in public}, "nothing lands outside the store's schema"


def test_timestamps_come_back_naive_in_utc(store):
    store.insert_element(Element("X1", "capability", "Cap"), "a")
    e = store.get_element("X1")
    assert e.created_at.tzinfo is None
    assert abs((datetime.now(UTC).replace(tzinfo=None) - e.created_at).total_seconds()) < 60
    assert store.history("X1")[0]["changed_at"].tzinfo is None


def test_a_connection_the_server_closed_is_reopened_once_and_the_statement_retried(store, postgres_dsn):
    """The platform's failure mode: the token aged out or the instance restarted and the connection
    is gone; the engine opens a new one, prepared like the first, and the reader never notices."""
    opened: list[int] = []
    real_open = store._open

    def open_and_count():
        opened.append(1)
        return real_open()

    store._open = open_and_count
    with psycopg.connect(postgres_dsn, autocommit=True) as other:
        other.execute("SELECT pg_terminate_backend(%s)", [store._conn.info.backend_pid])
    assert store.count_elements() == 0, "answered by the new connection"
    assert opened == [1]
    assert store._fetch_all("SHOW search_path")[0][0] == store.schema, "prepared like the first"
    assert store._fetch_all("SHOW timezone")[0][0] == "UTC"
    store.count_elements()
    assert opened == [1], "no further reconnect"


def test_an_error_that_is_not_a_lost_connection_is_raised_as_it_is(store):
    opened: list[int] = []
    store._open = lambda: opened.append(1)
    with pytest.raises(psycopg.errors.UndefinedTable):
        store._fetch_all("SELECT * FROM no_such_table")
    assert opened == [], "no reconnect for an ordinary error"
    assert store.count_elements() == 0, "and the session is usable: every statement is its own transaction"


def test_a_readers_query_runs_read_only_on_the_server(store):
    """The word guard of the shared store is the first line; the server's read-only transaction the second."""
    store._execute("CREATE SEQUENCE ticket")
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        store.query("select nextval('ticket')")
    assert len(store.query("select 1 as one")) == 1, "and the connection is usable afterwards"


def test_an_older_store_gains_the_columns_that_shipped_later(postgres_dsn, schema, pack):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"SET search_path TO {schema}")
        conn.execute(DDL["element"].replace(",\n            target_note VARCHAR", ""))
    b = LakebaseBackend.from_dsn(postgres_dsn, schema)
    columns = {
        r[0]
        for r in b._fetch_all(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = ? AND table_name = 'element'",
            [schema],
        )
    }
    assert "target_note" in columns
    b.save_pack(pack)
    b.insert_element(Element("X1", "capability", "Cap", target_note="later"), "a")
    assert b.get_element("X1").target_note == "later"
    b.close()


def test_settings_name_what_the_engine_needs():
    with pytest.raises(ValueError, match="EA_LAKEBASE_INSTANCE"):
        LakebaseBackend.from_settings(Settings(backend="lakebase"))
    with pytest.raises(ValueError, match="identifier"):
        LakebaseBackend.from_dsn("host=/nowhere", schema="ea; drop schema public")


def test_the_platform_sign_in_uses_the_instance_host_and_a_fresh_token(monkeypatch, postgres_dsn, schema):
    """On Databricks Apps the app knows its instance: the host comes from the SDK, the user is the
    service principal, and the password is a token generated for the instance — a new one each time
    a connection is opened, since a token lives an hour."""
    tokens: list[str] = []

    class Workspace:
        class database:
            @staticmethod
            def get_database_instance(name):
                assert name == "ea-repository"
                return types.SimpleNamespace(read_write_dns="instance-1.database.cloud.example")

            @staticmethod
            def generate_database_credential(request_id, instance_names):
                assert instance_names == ["ea-repository"] and uuid.UUID(request_id)
                tokens.append(f"token-{len(tokens) + 1}")
                return types.SimpleNamespace(token=tokens[-1], expiration_time=None)

        class current_user:
            @staticmethod
            def me():
                return types.SimpleNamespace(user_name="1234-app")

    connections: list[dict] = []
    real_connect = psycopg.connect

    def connect_to_the_run(*args, **kwargs):
        if args:  # a fixture's own connection, by DSN
            return real_connect(*args, **kwargs)
        connections.append(kwargs)
        return real_connect(postgres_dsn, autocommit=True)  # the run's server stands in for the instance

    monkeypatch.setattr(psycopg, "connect", connect_to_the_run)
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    b = LakebaseBackend.from_settings(
        Settings(backend="lakebase", lakebase_instance="ea-repository", store_schema=schema),
        workspace=Workspace,
    )
    assert connections == [
        {
            "host": "instance-1.database.cloud.example",
            "port": 5432,
            "dbname": "databricks_postgres",
            "user": "1234-app",
            "password": "token-1",
            "sslmode": "require",
            "application_name": "ea-repository",
            "autocommit": True,
        }
    ]
    with real_connect(postgres_dsn, autocommit=True) as other:  # the platform closes the connection
        other.execute("SELECT pg_terminate_backend(%s)", [b._conn.info.backend_pid])
    assert b.list_packs() == []
    assert [c["password"] for c in connections] == ["token-1", "token-2"], (
        "signed in again with a fresh token"
    )
    b.close()

    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "sp-client-id")  # what Databricks Apps sets for the app
    b = LakebaseBackend.from_settings(
        Settings(
            backend="lakebase", lakebase_instance="ea-repository", pg_host="named-host", store_schema=schema
        ),
        workspace=Workspace,
    )
    assert (connections[-1]["host"], connections[-1]["user"]) == ("named-host", "sp-client-id")
    b.close()
