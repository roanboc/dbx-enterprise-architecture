.PHONY: install seed run test test-fast test-live gui gui-install lint format check validate deploy deploy-run clean

install:            ## create .venv and install runtime + dev dependencies with uv
	uv sync

seed:               ## create data/ea.duckdb, load the higher-education pack and the sample curriculum model
	uv run ea init --pack packs/higher_education/metamodel.yaml
	uv run ea import data/sample --source sample

run:                ## start the app locally on DuckDB (Dash debug server)
	uv run python app.py --dev

test:               ## the test suite: every store test on DuckDB and on a Postgres started for the run, and the command-line scenarios
	uv run pytest

test-fast:          ## the unit tests alone, while iterating
	uv run pytest -m "not cli"

test-live:          ## the unit tests a third time, on a Lakebase instance (EA_LAKEBASE_INSTANCE, DATABRICKS_HOST and the SDK's credentials)
	EA_LIVE_LAKEBASE=1 uv run --extra databricks pytest -m "not cli"

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

deploy:             ## the bundle: the Lakebase instance and the app, deployed and not yet started (TARGET=dev)
	databricks bundle validate -t $(or $(TARGET),dev)
	databricks bundle deploy -t $(or $(TARGET),dev)

deploy-run:         ## start (or restart) the deployed app
	databricks bundle run ea_repository -t $(or $(TARGET),dev)

clean:
	rm -f data/ea.duckdb data/ea.duckdb.wal
