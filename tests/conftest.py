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
from ea.backend.sql import DDL, schemas
from ea.config import Settings
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack
from ea.services import GraphService, OrganisationService, RepositoryService

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


def _drop_schemas(b) -> None:
    """A store is a schema per group of tables now, so a test drops every one of them."""
    for schema in schemas(b.schema_prefix):
        b._execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


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
    _drop_schemas(b)
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
    OrganisationService(b).ensure_default(pack)  # what the app does on its first start
    yield b
    if request.param == "lakebase":
        _drop_schemas(b)
    if request.param != "lakebase-live":
        b.close()


@pytest.fixture
def fresh_backend(pack):
    """A second, empty store — what an export has to be able to rebuild the model into.

    Always DuckDB: the comparison is of what the two stores hold, not of how they hold it, so
    the engine the export is read back into does not need to vary with the engine it came from.
    """
    b = DuckDBBackend(":memory:")
    b.save_pack(pack)
    OrganisationService(b).ensure_default(pack)
    yield b
    b.close()


@pytest.fixture
def loaded(backend, registry):
    report = import_directory(backend, registry, SAMPLE, "sample")
    assert report.ok, report.summary()
    return backend


@pytest.fixture
def app_context(loaded):
    """The application context a page callback is handed, over the seeded store.

    A page's own logic — what the address says, what a count means, which rows a drill-down
    keeps — is a pure function of a filter and a store, so it is provable here rather than
    only in the browser round.
    """
    from ea.ui.context import AppContext

    return AppContext(settings=Settings.from_env(), backend=loaded)


@pytest.fixture
def repo(loaded, registry):
    return RepositoryService(loaded, registry)


@pytest.fixture
def graph(loaded, registry):
    return GraphService(loaded, registry)
