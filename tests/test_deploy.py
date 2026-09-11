"""The deployment bundle says what the platform needs, and nothing else."""

from __future__ import annotations

from pathlib import Path

import yaml
from tests.conftest import ROOT


def test_the_bundle_runs_the_app_on_its_own_lakebase_instance_with_the_extra_installed():
    text = Path(ROOT / "databricks.yml").read_text()
    bundle = yaml.safe_load(text)
    instance = bundle["resources"]["database_instances"]["ea"]
    assert (instance["name"], instance["capacity"]) == ("${var.instance}", "${var.capacity}")
    app = bundle["resources"]["apps"]["ea_repository"]
    assert app["source_code_path"] == "."
    assert app["config"]["command"] == [
        "uv", "run", "--frozen", "--no-dev", "--extra", "databricks", "python", "app.py"
    ]  # fmt: skip
    env = {e["name"]: e for e in app["config"]["env"]}
    assert env["EA_BACKEND"]["value"] == "lakebase" and env["EA_AUTH"]["value"] == "databricks"
    # the deployed names, not the variables: development mode prefixes what it creates
    assert env["EA_LAKEBASE_INSTANCE"]["value"] == "${resources.database_instances.ea.name}"
    assert env["PGDATABASE"]["value"] == "${var.database}" and env["EA_SCHEMA"]["value"] == "${var.schema}"
    [database] = app["resources"]
    assert database["database"] == {
        "instance_name": "${resources.database_instances.ea.name}",
        "database_name": "${var.database}",
        "permission": "CAN_CONNECT_AND_CREATE",
    }
    assert "sql_warehouse" not in text and "schemas" not in bundle["resources"], (
        "no warehouse, no catalog schema"
    )
    injected = {
        "DATABRICKS_APP_PORT",
        "DATABRICKS_HOST",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
        "PGHOST",
        "PGUSER",
        "PGPASSWORD",
    }
    assert not injected & set(env), (
        "what the platform injects or the engine looks up is never set by the bundle"
    )
    assert bundle["targets"]["dev"]["default"] is True and "prod" in bundle["targets"]
