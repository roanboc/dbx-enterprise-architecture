"""Fixtures: the pack, and the store on every engine.

The `backend` fixture runs each test on DuckDB and again on the Databricks
engine over a warehouse played by DuckDB (`fake_warehouse.py`), so the SQL the
platform receives is proved on every change. With `EA_LIVE_DATABRICKS=1` and the
platform's variables set (`DATABRICKS_HOST`, credentials, `DATABRICKS_WAREHOUSE_ID`,
`EA_CATALOG`), a third run uses a real warehouse, in a schema of its own that is
dropped at the end.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from tests.fake_warehouse import connect_fake_warehouse

from ea.backend.databricks_backend import DatabricksBackend
from ea.backend.duckdb_backend import DuckDBBackend
from ea.backend.sql import DDL
from ea.config import Settings
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack
from ea.services import GraphService, RepositoryService

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "packs" / "higher_education" / "metamodel.yaml"
SAMPLE = ROOT / "data" / "sample"
ENGINES = ["duckdb", "databricks-on-duckdb"] + (
    ["databricks-live"] if os.environ.get("EA_LIVE_DATABRICKS") else []
)


@pytest.fixture(scope="session")
def pack():
    return load_pack(PACK)


@pytest.fixture(scope="session")
def registry(pack):
    return Registry(pack)


@pytest.fixture(scope="session")
def live_backend():
    """One connection to the real warehouse for the whole run, in a schema named for the run."""
    pytest.importorskip("databricks.sql", reason="the databricks extra is not installed")
    settings = Settings.from_env()
    if not settings.databricks_catalog:
        pytest.skip("EA_CATALOG names the catalog the live run may create a schema in")
    settings.databricks_schema = f"ea_test_{uuid.uuid4().hex[:8]}"
    b = DatabricksBackend.from_settings(settings)
    yield b
    b._execute(f"DROP SCHEMA IF EXISTS {b.catalog}.{b.schema} CASCADE")
    b.close()


@pytest.fixture(params=ENGINES)
def backend(request, pack):
    if request.param == "duckdb":
        b = DuckDBBackend(":memory:")
    elif request.param == "databricks-on-duckdb":
        b = DatabricksBackend("/sql/1.0/warehouses/fake", "memory", "main", connect=connect_fake_warehouse)
    else:
        b = request.getfixturevalue("live_backend")
        for table in DDL:  # the schema is shared by the run: every test starts from empty tables
            b._execute(f"DELETE FROM {table}")
    b.save_pack(pack)
    yield b
    if request.param != "databricks-live":
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
