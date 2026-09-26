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
    database, endpoint = app["resources"]
    assert database["database"] == {
        "instance_name": "${resources.database_instances.ea.name}",
        "database_name": "${var.database}",
        "permission": "CAN_CONNECT_AND_CREATE",
    }
    # the assistant's model: one serving endpoint the app may query, and nothing more (decision 0023)
    assert endpoint["serving_endpoint"] == {"name": "${var.serving_endpoint}", "permission": "CAN_QUERY"}
    assert env["EA_AGENT_ENDPOINT"]["value"] == "${var.serving_endpoint}"
    # which model answers is the workspace's choice: the bundle names an endpoint, never a model
    assert "default" not in bundle["variables"]["serving_endpoint"]
    assert "ANTHROPIC_API_KEY" not in env, "no model key lives in the app on Databricks"
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


def test_the_tool_server_is_an_app_of_its_own_on_the_same_store():
    """Initiative 26: the read tools served over MCP, beside the web application, never inside it."""
    bundle = yaml.safe_load(Path(ROOT / "databricks.yml").read_text())
    apps = bundle["resources"]["apps"]
    web, tools = apps["ea_repository"], apps["ea_tool_server"]
    assert tools["config"]["command"][-3:] == ["ea", "mcp", "--http"]
    assert tools["resources"][0]["database"] == web["resources"][0]["database"]
    env = {e["name"]: e["value"] for e in tools["config"]["env"]}
    web_env = {e["name"]: e["value"] for e in web["config"]["env"]}
    for name in (
        "EA_BACKEND",
        "EA_LAKEBASE_INSTANCE",
        "PGDATABASE",
        "EA_SCHEMA",
        "EA_AUTH",
        "EA_ROLE_GROUPS",
    ):
        assert env[name] == web_env[name], name
    # it answers with the model's own tools, never a model: no serving endpoint is granted
    assert not any("serving_endpoint" in r for r in tools["resources"])
    assert "EA_AGENT_ENDPOINT" not in env
