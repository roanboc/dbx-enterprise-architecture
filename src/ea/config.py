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
    backend: str = "duckdb"  # duckdb (a file) | lakebase (Postgres: the platform's Lakebase, or any Postgres)
    db_path: str = str(ROOT / "data" / "ea.duckdb")
    pack_path: str = str(ROOT / "packs" / "higher_education" / "metamodel.yaml")
    auth: str = "mock"
    agent_provider: str = "auto"  # auto | anthropic | stub
    agent_model: str = "claude-opus-5"
    max_rows: int = 5000
    admin_contact: str = ""
    # On lakebase: the schema the tables live in; the instance the platform's identity signs in to
    # (the SDK issues the token); or any Postgres instead, as libpq reads a URL or a key=value
    # string; and libpq's own PGHOST, PGPORT, PGDATABASE, PGUSER, PGSSLMODE, honoured either way.
    store_schema: str = "ea"
    lakebase_instance: str = ""
    pg_dsn: str = ""
    pg_host: str = ""
    pg_port: int = 5432
    pg_database: str = ""
    pg_user: str = ""
    pg_sslmode: str = ""
    role_groups: str = ""  # admin=grp1,grp2;architect=grp3;reviewer=grp4 (decision 0008)
    trust_groups_header: bool = False  # only behind a proxy of ours that sets X-Forwarded-Groups

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
            store_schema=env.get("EA_SCHEMA", "ea"),
            lakebase_instance=env.get("EA_LAKEBASE_INSTANCE", ""),
            pg_dsn=env.get("EA_POSTGRES_DSN", ""),
            pg_host=env.get("PGHOST", ""),
            pg_port=int(env.get("PGPORT") or 5432),
            pg_database=env.get("PGDATABASE", ""),
            pg_user=env.get("PGUSER", ""),
            pg_sslmode=env.get("PGSSLMODE", ""),
            role_groups=env.get("EA_ROLE_GROUPS", ""),
            trust_groups_header=env.get("EA_TRUST_GROUPS_HEADER", "").strip().lower() in ("1", "true", "yes"),
        )
