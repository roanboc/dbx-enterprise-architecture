"""The deployment bundle and the grant step say what the platform needs, and nothing else."""

from __future__ import annotations

from pathlib import Path

import yaml
from deploy.grants import grant_statements
from tests.conftest import ROOT


def test_the_grants_name_the_catalog_first_and_the_schema_privileges_once():
    statements = grant_statements("ea_dev", "ea", "1234-app")
    assert statements == [
        "GRANT USE CATALOG ON CATALOG ea_dev TO `1234-app`",
        "GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY ON SCHEMA ea_dev.ea TO `1234-app`",
    ]
    assert "`" not in grant_statements("c", "s", "a`b")[0].split("TO ")[1].strip("`")


def test_the_bundle_runs_the_app_on_the_databricks_store_with_the_extra_installed():
    bundle = yaml.safe_load(Path(ROOT / "databricks.yml").read_text())
    app = bundle["resources"]["apps"]["ea_repository"]
    assert app["source_code_path"] == "."
    assert app["config"]["command"] == [
        "uv", "run", "--frozen", "--no-dev", "--extra", "databricks", "python", "app.py"
    ]  # fmt: skip
    env = {e["name"]: e for e in app["config"]["env"]}
    assert env["EA_BACKEND"]["value"] == "databricks" and env["EA_AUTH"]["value"] == "databricks"
    assert env["DATABRICKS_WAREHOUSE_ID"]["valueFrom"] == "sql-warehouse"
    # the deployed names, not the variables: development mode prefixes what it creates
    assert env["EA_CATALOG"]["value"] == "${resources.schemas.ea.catalog_name}"
    assert env["EA_SCHEMA"]["value"] == "${resources.schemas.ea.name}"
    assert {r["name"] for r in app["resources"]} == {"sql-warehouse"}
    assert app["resources"][0]["sql_warehouse"]["permission"] == "CAN_USE"
    schema = bundle["resources"]["schemas"]["ea"]
    assert (schema["catalog_name"], schema["name"]) == ("${var.catalog}", "${var.schema}")
    injected = {"DATABRICKS_APP_PORT", "DATABRICKS_HOST", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET"}
    assert not injected & set(env), "what the platform injects is never set by the bundle"
    assert bundle["targets"]["dev"]["default"] is True and "prod" in bundle["targets"]
