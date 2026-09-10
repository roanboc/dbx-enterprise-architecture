"""Grant the deployed app's service principal what the store needs on its schema.

The bundle creates the schema and the app, but the app's service principal
exists only once the app does, so the grant is a step after the first deploy:

    databricks bundle deploy -t dev
    uv run --extra databricks python deploy/grants.py --catalog ea_dev --schema ea --app ea-repository

The bundle's development mode prefixes the schema and the app with the
deployer's name; `databricks bundle summary -t dev` prints the names to pass.
The statements are run on the warehouse the app uses (`DATABRICKS_WAREHOUSE_ID`),
as whoever runs this — who must own the catalog or hold MANAGE on it.
"""

from __future__ import annotations

import argparse
import os
import sys

SCHEMA_PRIVILEGES = ("USE SCHEMA", "CREATE TABLE", "SELECT", "MODIFY")


def grant_statements(catalog: str, schema: str, principal: str) -> list[str]:
    """The GRANTs, in the order Unity Catalog wants them (the catalog before what is in it)."""
    who = "`" + principal.replace("`", "") + "`"
    return [
        f"GRANT USE CATALOG ON CATALOG {catalog} TO {who}",
        f"GRANT {', '.join(SCHEMA_PRIVILEGES)} ON SCHEMA {catalog}.{schema} TO {who}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--catalog", default=os.environ.get("EA_CATALOG", ""), help="the catalog (EA_CATALOG)"
    )
    parser.add_argument("--schema", default=os.environ.get("EA_SCHEMA", "ea"), help="the schema (EA_SCHEMA)")
    parser.add_argument("--app", default="ea-repository", help="the deployed app's name")
    parser.add_argument(
        "--warehouse-id",
        default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""),
        help="the warehouse that runs the statements (DATABRICKS_WAREHOUSE_ID)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the statements and stop")
    args = parser.parse_args(argv)
    if not args.catalog:
        print("--catalog (or EA_CATALOG) names the catalog", file=sys.stderr)
        return 2

    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient()
    app = client.apps.get(args.app)
    principal = app.service_principal_client_id or app.service_principal_name
    if not principal:
        print(f"app {args.app} has no service principal yet; deploy it first", file=sys.stderr)
        return 1
    statements = grant_statements(args.catalog, args.schema, principal)
    for statement in statements:
        print(statement)
    if args.dry_run:
        return 0
    if not args.warehouse_id:
        print("--warehouse-id (or DATABRICKS_WAREHOUSE_ID) names the warehouse", file=sys.stderr)
        return 2
    for statement in statements:
        result = client.statement_execution.execute_statement(
            warehouse_id=args.warehouse_id, statement=statement, wait_timeout="30s"
        )
        state = result.status.state.value if result.status and result.status.state else "unknown"
        if state != "SUCCEEDED":
            message = result.status.error.message if result.status and result.status.error else state
            print(f"failed: {statement}: {message}", file=sys.stderr)
            return 1
    print(f"granted to {principal} on {args.catalog}.{args.schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
