"""One application under test, one browser, and the recorder that writes the report.

The round runs against a real server on a throwaway database: seeded from the pack and
the sample model, served by the same entry point production uses, with the stub agent
provider so an answer is the same on every run and no model key is needed. One browser
drives it in sequence — DuckDB takes one writer, and the branch and the persona live in
a session cookie, so parallel pages would be testing each other.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.ui.evidence import Finding, Scenario
from tests.ui.harness import Ui
from tests.ui.report import run_context, write_report

if importlib.util.find_spec("playwright") is None:
    # The round is not installed here (CI takes the default groups only). Deselecting by
    # marker is not enough: pytest imports a module before it reads its markers.
    collect_ignore_glob = ["test_*.py"]

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample"
PACK = ROOT / "packs" / "higher_education" / "metamodel.yaml"
VIEWPORT = {"width": 1600, "height": 1000}
NARROW = {"width": 480, "height": 900}

_scenarios: list[Scenario] = []
_findings: list[Finding] = []
_context: dict[str, str] = {}
_run_dir: list[Path] = []


def pytest_configure(config: pytest.Config) -> None:
    config.stash  # noqa: B018 — touch the stash so a plugin-less run still imports cleanly


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _seed(db_path: Path) -> str:
    """Load the pack and the sample model into a database this round owns."""
    from ea.backend.duckdb_backend import DuckDBBackend
    from ea.importer import import_directory
    from ea.metamodel import Registry, load_pack

    pack = load_pack(PACK)
    backend = DuckDBBackend(str(db_path))
    try:
        backend.save_pack(pack)
        report = import_directory(backend, Registry(pack), SAMPLE, "sample")
        assert report.ok, report.summary()
        elements = backend.count_elements()
        relationships = backend.count_relationships()
    finally:
        backend.close()
    return f"{elements} elements, {relationships} relationships (the sample model)"


@pytest.fixture(scope="session")
def run_dir() -> Path:
    """One folder per run: the report and everything it embeds, and nothing shared."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
    suffix = os.environ.get("EA_ROUND_LABEL") or f"p{os.getpid()}"
    d = ROOT / ".testrun" / f"{stamp}-{suffix}"
    (d / "screenshots").mkdir(parents=True, exist_ok=True)
    (d / "downloads").mkdir(parents=True, exist_ok=True)
    _run_dir.append(d)
    return d


@pytest.fixture(scope="session")
def app_env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    db = tmp_path_factory.mktemp("ea-under-test") / "ea.duckdb"
    seed = _seed(db)
    env = dict(os.environ)
    env.update(
        EA_DB_PATH=str(db),
        EA_PACK=str(PACK),
        EA_AUTH="mock",
        EA_AGENT_PROVIDER="stub",
        EA_SECRET_KEY="test-round-fixed-key",
        EA_BACKEND="duckdb",
    )
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["_EA_SEED_SUMMARY"] = seed
    return env


@pytest.fixture(scope="session")
def server(app_env: dict[str, str], run_dir: Path) -> Iterator[str]:
    """The application, served the way it is served in production."""
    import urllib.error
    import urllib.request

    port = _free_port()
    env = dict(app_env, PORT=str(port))
    log = run_dir / "server.log"
    handle = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=ROOT,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # its own group, so nothing outlives the round
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            handle.close()
            raise RuntimeError(
                f"the application exited with {proc.returncode}:\n"
                + (log / "server.log").read_text(encoding="utf-8")[-3000:]
            )
        try:
            with urllib.request.urlopen(base + "/", timeout=2) as r:  # noqa: S310 — localhost
                if r.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.4)
    else:
        proc.terminate()
        handle.close()
        raise RuntimeError("the application did not come up within 90 s")
    try:
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        handle.close()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none"])
        try:
            yield b
        finally:
            b.close()


@pytest.fixture(scope="session")
def ui(browser, server: str, run_dir: Path, app_env: dict[str, str]) -> Iterator[Ui]:
    context = browser.new_context(
        viewport=VIEWPORT,
        device_scale_factor=1,
        accept_downloads=True,
        locale="en-AU",
        timezone_id="UTC",
        reduced_motion="reduce",  # an animation mid-flight is the commonest cause of a flaky shot
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    page.set_default_timeout(20_000)
    helper = Ui(page=page, base_url=server, run_dir=run_dir)
    _context.update(
        run_context(
            base_url=server,
            browser=f"Chromium {browser.version}",
            viewport=f"{VIEWPORT['width']}x{VIEWPORT['height']}",
            provider="stub (no model key — deterministic)",
            seed=app_env["_EA_SEED_SUMMARY"],
        )
    )
    try:
        yield helper
    finally:
        context.close()


@pytest.fixture(autouse=True)
def _reset(request: pytest.FixtureRequest) -> Iterator[None]:
    """Every scenario starts as Admin on main, whatever the one before it left behind."""
    if "ui" not in request.fixturenames:
        yield
        return
    helper = request.getfixturevalue("ui")
    if helper.page.url.startswith("http"):
        try:
            helper.wide()
            if helper.role_badge().lower().find("admin") < 0:
                helper.persona("Admin")
            if helper.branch_badge().strip().lower() not in ("main", ""):
                helper.branch("main")
        except Exception:  # noqa: BLE001 — a broken page is the next scenario's problem
            pass
    yield


@pytest.fixture(scope="session")
def cli(tmp_path_factory: pytest.TempPathFactory):
    """Run `ea` against a database of its own — the served one has the single writer."""
    db = tmp_path_factory.mktemp("ea-cli") / "ea.duckdb"
    _seed(db)
    base = dict(os.environ)
    base.update(EA_DB_PATH=str(db), EA_PACK=str(PACK), EA_BACKEND="duckdb", EA_AGENT_PROVIDER="stub")

    def run(*args: str, expect: int | None = 0, **env: str):
        proc = subprocess.run(
            [sys.executable, "-m", "ea.cli", *args],
            cwd=ROOT,
            env={**base, **env, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            timeout=180,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if expect is not None and proc.returncode != expect:
            raise AssertionError(
                f"ea {' '.join(args)} exited {proc.returncode}, expected {expect}\n{out[-2000:]}"
            )
        return proc.returncode, out

    run.db = db  # type: ignore[attr-defined]
    return run


@pytest.fixture
def record(request: pytest.FixtureRequest, ui: Ui) -> Iterator[Scenario]:
    """The scenario this test performs, recorded whatever happens to it."""
    marker = request.node.get_closest_marker("scenario")
    if marker is None:
        raise pytest.UsageError(f"{request.node.name} needs a @pytest.mark.scenario(...)")
    scenario = Scenario(**marker.kwargs)
    ui.bind(scenario)
    _scenarios.append(scenario)
    try:
        yield scenario
    except Exception as exc:  # noqa: BLE001 — the report keeps the failure, then re-raises
        scenario.outcome = "failed"
        scenario.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if scenario.outcome == "passed" and scenario.failed_checks:
            scenario.outcome = "failed"
            scenario.error = "; ".join(c.name for c in scenario.failed_checks)
        ui.unbind()


@pytest.fixture
def finding() -> Iterator[list[Finding]]:
    """Somewhere for a test to lodge what it found without failing for it."""
    yield _findings


def pytest_runtest_makereport(item, call):  # noqa: ANN001, ANN201 — pytest hook signature
    """Keep a failure that happened outside the recorder's own try block."""
    if call.when == "call" and call.excinfo is not None:
        marker = item.get_closest_marker("scenario")
        if marker is None:
            return
        sid = marker.kwargs.get("scenario_id")
        for s in _scenarios:
            if s.scenario_id == sid and s.outcome == "passed":
                s.outcome = "failed"
                s.error = f"{call.excinfo.typename}: {call.excinfo.value}"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _scenarios:
        return
    if not _run_dir:
        return
    out = write_report(_run_dir[-1], _scenarios, _findings, _context)
    print(f"\nRound written to {out}")
