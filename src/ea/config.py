"""Settings from the environment (a local .env is honoured)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    backend: str = "duckdb"
    db_path: str = str(ROOT / "data" / "ea.duckdb")
    pack_path: str = str(ROOT / "packs" / "higher_education" / "metamodel.yaml")
    auth: str = "mock"
    agent_provider: str = "auto"  # auto | anthropic | stub
    agent_model: str = "claude-opus-5"
    max_rows: int = 5000
    admin_contact: str = ""
    databricks_warehouse_id: str = ""
    databricks_http_path: str = ""  # instead of the warehouse id: any SQL endpoint path
    databricks_catalog: str = ""
    databricks_schema: str = "ea"
    role_groups: str = ""  # admin=grp1,grp2;architect=grp3;reviewer=grp4 (decision 0008)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            backend=env.get("EA_BACKEND", "duckdb"),
            db_path=env.get("EA_DB_PATH", cls.db_path),
            pack_path=env.get("EA_PACK", cls.pack_path),
            auth=env.get("EA_AUTH", "mock"),
            agent_provider=env.get("EA_AGENT_PROVIDER", "auto"),
            agent_model=env.get("EA_AGENT_MODEL", "claude-opus-5"),
            max_rows=int(env.get("EA_MAX_ROWS", "5000")),
            admin_contact=env.get("EA_ADMIN_CONTACT", ""),
            databricks_warehouse_id=env.get("DATABRICKS_WAREHOUSE_ID", ""),
            databricks_http_path=env.get("DATABRICKS_HTTP_PATH", ""),
            databricks_catalog=env.get("EA_CATALOG", ""),
            databricks_schema=env.get("EA_SCHEMA", "ea"),
            role_groups=env.get("EA_ROLE_GROUPS", ""),
        )
