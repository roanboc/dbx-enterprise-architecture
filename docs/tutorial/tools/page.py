"""The film's page, served from `build/` so the shots it draws stay readable by the canvas, and
opened in a browser that waits until every shot and font has loaded."""

from __future__ import annotations

import contextlib
import functools
import http.server
import threading
from collections.abc import Iterator

from common import BUILD


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


@contextlib.contextmanager
def served() -> Iterator[str]:
    handler = functools.partial(_Quiet, directory=str(BUILD))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/render.html"
    finally:
        server.shutdown()


def open_film(browser, url: str, scale: float = 1.0):  # noqa: ANN001, ANN201
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.add_init_script(f"window.__SCALE__ = {scale};")
    page.goto(url)
    page.wait_for_function("window.__READY__ === true || !!window.__ERROR__", timeout=120_000)
    error = page.evaluate("window.__ERROR__ || ''")
    if error:
        raise SystemExit(f"the film did not load: {error}")
    return page


def info(browser, url: str) -> dict:  # noqa: ANN001
    page = open_film(browser, url, 0.25)
    try:
        return page.evaluate("filmInfo()")
    finally:
        page.close()
