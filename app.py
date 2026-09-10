"""Entrypoint for the EA repository app (Dash).

* ``python app.py --dev``  - Dash development server with the debug tools (local work)
* ``python app.py``        - gunicorn, what the bundle (``databricks.yml``) runs on Databricks Apps

Binds 0.0.0.0 on DATABRICKS_APP_PORT (or PORT, or 8050); logs to stdout/stderr;
gunicorn's graceful timeout stays under the 15 s SIGTERM budget of Databricks Apps.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ea.ui.app import create_app  # noqa: E402

app = create_app()
server = app.server


def _port() -> int:
    return int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8050)


def serve() -> None:
    from gunicorn.app.base import BaseApplication

    class Server(BaseApplication):
        def __init__(self, application, options):
            self.options = options
            self.application = application
            super().__init__()

        def load_config(self):
            for key, value in self.options.items():
                self.cfg.set(key, value)

        def load(self):
            return self.application

    Server(
        server,
        {
            "bind": f"0.0.0.0:{_port()}",
            "workers": 1,  # one process keeps the DuckDB writer and the graph cache in one place
            "threads": 4,
            "timeout": 60,
            "graceful_timeout": 10,
            "accesslog": "-",
            "errorlog": "-",
            "loglevel": "info",
        },
    ).run()


if __name__ == "__main__":
    if "--dev" in sys.argv or os.environ.get("EA_DEV") == "1":
        # No auto-reloader: it forks a second process and DuckDB allows one writer per file.
        app.run(host="0.0.0.0", port=_port(), debug=True, use_reloader=False)
    else:
        serve()
