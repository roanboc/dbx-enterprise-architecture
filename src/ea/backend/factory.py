from __future__ import annotations

from ea.backend.base import DatabaseBackend
from ea.config import Settings


def backend_from_settings(settings: Settings) -> DatabaseBackend:
    if settings.backend == "duckdb":
        from ea.backend.duckdb_backend import DuckDBBackend

        return DuckDBBackend(settings.db_path)
    if settings.backend == "lakebase":
        from ea.backend.lakebase_backend import LakebaseBackend

        return LakebaseBackend.from_settings(settings)
    raise ValueError(f"unknown backend {settings.backend!r}")
