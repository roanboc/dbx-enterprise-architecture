"""Fixtures: the pack, and the store on every engine.

The `backend` fixture runs each test on DuckDB and again on the Lakebase engine
over a Postgres of the run's own (`postgres_server.py`: the one `EA_TEST_POSTGRES`
names, else one started for the run), each test in a schema of its own. With
`EA_LIVE_LAKEBASE=1` and the platform's variables set (`EA_LAKEBASE_INSTANCE`
and the SDK's credentials), a third run uses a Lakebase instance, in a schema
named for the run that is dropped at the end.
"""

from __future__ import annotations

import os
import uuid
import warnings
from pathlib import Path

import pytest
from tests.postgres_server import NO_POSTGRES, postgres_for_the_run

from ea.backend.duckdb_backend import DuckDBBackend
from ea.backend.lakebase_backend import LakebaseBackend
from ea.backend.sql import DDL
from ea.config import Settings
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack
from ea.services import GraphService, RepositoryService

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "packs" / "higher_education" / "metamodel.yaml"
SAMPLE = ROOT / "data" / "sample"
ENGINES = ["duckdb", "lakebase"] + (["lakebase-live"] if os.environ.get("EA_LIVE_LAKEBASE") else [])


def new_schema_name() -> str:
    """A schema name for one test on Postgres, so tests never see each other's rows."""
    return f"t_{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session")
def pack():
    return load_pack(PACK)


@pytest.fixture(scope="session")
def registry(pack):
    return Registry(pack)


@pytest.fixture(scope="session")
def postgres_dsn():
    """The Postgres of the run: named by EA_TEST_POSTGRES, or started here and stopped at the end."""
    dsn, let_go = postgres_for_the_run()
    if dsn is None:
        warnings.warn(NO_POSTGRES, stacklevel=1)
        pytest.skip(NO_POSTGRES)
    yield dsn
    let_go()


@pytest.fixture(scope="session")
def live_backend():
    """One connection to a Lakebase instance for the whole run, in a schema named for the run."""
    pytest.importorskip("databricks.sdk", reason="the databricks extra is not installed")
    settings = Settings.from_env()
    if not settings.lakebase_instance:
        pytest.skip("EA_LAKEBASE_INSTANCE names the instance the live run signs in to")
    settings.store_schema = f"ea_test_{uuid.uuid4().hex[:8]}"
    b = LakebaseBackend.from_settings(settings)
    yield b
    b._execute(f"DROP SCHEMA IF EXISTS {b.schema} CASCADE")
    b.close()


@pytest.fixture(params=ENGINES)
def backend(request, pack):
    if request.param == "duckdb":
        b = DuckDBBackend(":memory:")
    elif request.param == "lakebase":
        b = LakebaseBackend.from_dsn(request.getfixturevalue("postgres_dsn"), schema=new_schema_name())
    else:
        b = request.getfixturevalue("live_backend")
        for table in DDL:  # the schema is shared by the run: every test starts from empty tables
            b._execute(f"DELETE FROM {table}")
    b.save_pack(pack)
    yield b
    if request.param == "lakebase":
        b._execute(f"DROP SCHEMA {b.schema} CASCADE")
    if request.param != "lakebase-live":
        b.close()


@pytest.fixture
def loaded(backend, registry):
    report = import_directory(backend, registry, SAMPLE, "sample")
    assert report.ok, report.summary()
    return backend


@pytest.fixture
def repo(loaded, registry):
    return RepositoryService(loaded, registry)


@pytest.fixture
def graph(loaded, registry):
    return GraphService(loaded, registry)
