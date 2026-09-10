.PHONY: install seed run test test-fast test-live gui gui-install lint format check validate deploy deploy-grants deploy-run clean

install:            ## create .venv and install runtime + dev dependencies with uv
	uv sync

seed:               ## create data/ea.duckdb, load the higher-education pack and the sample curriculum model
	uv run ea init --pack packs/higher_education/metamodel.yaml
	uv run ea import data/sample --source sample

run:                ## start the app locally on DuckDB (Dash debug server)
	uv run python app.py --dev

test:               ## run the test suite: the unit tests and the command-line scenarios
	uv run pytest

test-fast:          ## the unit tests alone, in seconds, while iterating
	uv run pytest -m "not cli"

test-live:          ## the unit tests a third time, on a real SQL warehouse (DATABRICKS_HOST, credentials, DATABRICKS_WAREHOUSE_ID, EA_CATALOG)
	EA_LIVE_DATABRICKS=1 uv run --extra databricks pytest -m "not cli"

gui-install:        ## add the browser driver and its browser
	uv sync --group gui
	uv run --group gui playwright install chromium

gui:                ## the browser-driven round: drives the app, writes .testrun/<stamp>/
	uv run --group gui pytest tests/ui tests/test_ui_coverage.py -m "gui or cli"

lint:               ## ruff, as CI runs it: the lint rules and the formatting
	uv run ruff check src tests app.py
	uv run ruff format --check src tests app.py

format:             ## ruff format
	uv run ruff format src tests app.py

validate:           ## archreator validators (relative links, element-ID references)
	python3 scripts/check_links.py
	python3 scripts/check_model.py

check: lint test validate   ## everything CI runs

deploy:             ## the bundle: the Unity Catalog schema and the app, deployed and not yet started (BUNDLE_VAR_warehouse_id; TARGET=dev)
	databricks bundle validate -t $(or $(TARGET),dev)
	databricks bundle deploy -t $(or $(TARGET),dev)

deploy-grants:      ## after the first deploy, before the first run: the app's principal on the schema (EA_CATALOG, EA_SCHEMA, DATABRICKS_WAREHOUSE_ID; --schema/--app in GRANT_ARGS for dev-mode names)
	uv run --extra databricks python deploy/grants.py $(GRANT_ARGS)

deploy-run:         ## start (or restart) the deployed app
	databricks bundle run ea_repository -t $(or $(TARGET),dev)

clean:
	rm -f data/ea.duckdb data/ea.duckdb.wal
