.PHONY: install seed run test test-fast gui gui-install lint format check validate clean

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

gui-install:        ## add the browser driver and its browser
	uv sync --group gui
	uv run --group gui playwright install chromium

gui:                ## the browser-driven round: drives the app, writes .testrun/<stamp>/
	uv run --group gui pytest tests/ui tests/test_ui_coverage.py -m "gui or cli"

lint:               ## ruff
	uv run ruff check src tests app.py

format:             ## ruff format
	uv run ruff format src tests app.py

validate:           ## archreator validators (relative links, element-ID references)
	python3 scripts/check_links.py
	python3 scripts/check_model.py

check: lint test validate   ## everything CI runs

clean:
	rm -f data/ea.duckdb data/ea.duckdb.wal
