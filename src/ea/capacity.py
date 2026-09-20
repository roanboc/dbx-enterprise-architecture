"""The size the application has been assessed for, in one place (decision 0019).

The store was measured at `ASSESSED_ELEMENTS` and `ASSESSED_RELATIONSHIPS` when the
traversal became a walk (decisions 0016 to 0018). That figure is **assessed capacity**,
not a forecast of anybody's estate: today's content is a few thousand elements.

The figures live here rather than in the services that read them, so the assumption has
one home a reader can find, a test can assert and a measurement can move. A service that
would read the whole model into one request asks `too_large_to_hold` first, and the one
place that may still do it anyway says so out loud.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

#: What the store is assessed to hold and answer — the figure decisions 0016 to 0018 measured.
ASSESSED_ELEMENTS = 100_000
ASSESSED_RELATIONSHIPS = 600_000

#: Above this many elements the in-process graph is not built. Initiative 15 measured the
#: whole graph at about 470 MB and seven seconds at `ASSESSED_ELEMENTS`, against the 6 GB an
#: app on the platform is given by default; a fifth of that is the most one request may spend
#: on a cache, and it is still five times today's curriculum slice.
GRAPH_MAX_ELEMENTS = 20_000

#: The most rows a bounded whole-model read pulls into one request before it answers from
#: counts instead. Comfortably above today's content, far below the assessed capacity.
READ_CHUNK = 5_000


def too_large_to_hold(elements: int, limit: int = GRAPH_MAX_ELEMENTS) -> bool:
    """Whether a model this size may be held in a request, rather than answered from the store."""
    return elements > limit


def headroom(elements: int, relationships: int) -> dict[str, object]:
    """How large the model is against what the application is assessed for — what the Health page shows."""
    return {
        "elements": elements,
        "relationships": relationships,
        "assessed_elements": ASSESSED_ELEMENTS,
        "assessed_relationships": ASSESSED_RELATIONSHIPS,
        "elements_pct": round(100.0 * elements / ASSESSED_ELEMENTS, 1) if ASSESSED_ELEMENTS else 0.0,
        "relationships_pct": (
            round(100.0 * relationships / ASSESSED_RELATIONSHIPS, 1) if ASSESSED_RELATIONSHIPS else 0.0
        ),
        "graph_limit": GRAPH_MAX_ELEMENTS,
        "graph_held": not too_large_to_hold(elements),
    }


def pages(fetch: Any, chunk: int = READ_CHUNK) -> Iterator[list[Any]]:
    """Read a whole table in pages, so no caller holds all of it at once.

    `fetch(limit, offset)` returns a page. The iterator stops on the first short page, which
    is how a store says there is no more; a service that has to see every row folds each page
    into its accumulator and lets the page go.
    """
    offset = 0
    while True:
        page = fetch(chunk, offset)
        if not page:
            return
        yield page
        if len(page) < chunk:
            return
        offset += len(page)
