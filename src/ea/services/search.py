"""Search and filter elements: the store narrows, ranks and pages; this says why each row is here.

The store does the work (`ElementFilter` in, one page of rows out) because it is the only
layer that can see every matching row. Ranking a page in Python would rank only the rows
that page happened to hold, so the best match for a query with forty thousand hits could
never reach the first screen. What is left here is the reason a row matched — the field
and the snippet a reader needs to understand a hit they did not expect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import Element, ElementFilter

SNIPPET_CHARS = 140


@dataclass
class SearchHit:
    element: Element
    rank: int  # 0 name starts with the query, 1 name, key or id holds every word, 2 elsewhere
    matched_in: str  # name | key | id | description | attribute:<name>
    snippet: str = ""
    words: list[str] = field(default_factory=list)


def words_of(query: str) -> list[str]:
    return [w for w in re.split(r"\s+", (query or "").strip().lower()) if w]


def _snippet(text: str, words: list[str]) -> str:
    low = text.lower()
    pos = min((low.find(w) for w in words if low.find(w) >= 0), default=-1)
    if pos < 0:
        return text[:SNIPPET_CHARS] + ("…" if len(text) > SNIPPET_CHARS else "")
    start = max(0, pos - SNIPPET_CHARS // 3)
    end = min(len(text), start + SNIPPET_CHARS)
    out = text[start:end].replace("\n", " ")
    return ("…" if start > 0 else "") + out + ("…" if end < len(text) else "")


def rank_hit(e: Element, words: list[str]) -> SearchHit:
    """Where the words matched and how well: name first, then key or identifier, then description, then an attribute.

    The rank agrees with the one the store sorted on; it is recomputed here only to label
    the row. A row the store matched on an attribute *name* reports that name rather than
    the blank it used to, because a hit with no stated reason reads as a bug.
    """
    name, query = e.name.lower(), " ".join(words)
    if name.startswith(query):
        return SearchHit(e, 0, "name", e.name, words)
    if all(w in name for w in words):
        return SearchHit(e, 1, "name", e.name, words)
    for label, text in (("key", e.key or ""), ("id", e.element_id)):
        if all(w in text.lower() for w in words):
            return SearchHit(e, 1, label, text, words)
    desc = e.description_md or ""
    if any(w in desc.lower() for w in words):
        return SearchHit(e, 2, "description", _snippet(desc, words), words)
    for k, v in (e.attrs or {}).items():
        text = str(v)
        if any(w in text.lower() for w in words):
            return SearchHit(e, 2, f"attribute:{k}", _snippet(text, words), words)
        if any(w in k.lower() for w in words):
            # The store matches the attributes as JSON, names included. Saying which
            # attribute carried the word is the difference between a hit a reader can
            # act on and a row that looks like it does not belong in the list.
            return SearchHit(e, 2, f"attribute:{k}", _snippet(text, words), words)
    return SearchHit(e, 3, "", "", words)


class SearchService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend = backend
        self.registry = registry

    def search(self, filt: ElementFilter | None = None, limit: int = 200, offset: int = 0) -> list[SearchHit]:
        """One page of the rows the filter matches, each labelled with why it is here."""
        f = filt or ElementFilter()
        rows = self.backend.find_elements(f, limit=limit, offset=offset)
        if not f.words:
            return [SearchHit(e, 3, "", "", []) for e in rows]
        return [rank_hit(e, f.words) for e in rows]

    def count(self, filt: ElementFilter | None = None) -> int:
        """How many rows match in total — the honest number behind the page."""
        return self.backend.count_elements(filt)

    def values(self, column: str) -> list[str]:
        """The values one filterable column holds, for a filter control's options."""
        return self.backend.distinct_values(column)

    @staticmethod
    def rows(hits: list[SearchHit], registry: Registry) -> list[dict[str, Any]]:
        """Grid rows for the Browse page."""
        out = []
        for h in hits:
            e = h.element
            t = registry.get_type(e.type_id)
            out.append(
                {
                    "element_id": e.element_id,
                    "name": e.name,
                    "type": t.name if t else e.type_id,
                    "type_id": e.type_id,
                    "key": e.key,
                    "status": e.status,
                    "current_state": e.current_state,
                    "target_state": e.target_state,
                    "target_work_package": e.target_work_package,
                    "lifecycle_status": e.lifecycle_status,
                    "source_system": e.source_system,
                    "updated_at": str(e.updated_at)[:16] if e.updated_at else "",
                    "updated_by": e.updated_by,
                    # The field the words were found in, beside the text they were found in:
                    # the column used to be headed 'matched in' and hold only the text.
                    "matched_in": h.matched_in,
                    "snippet": h.snippet if h.matched_in not in ("name", "") else "",
                }
            )
        return out
