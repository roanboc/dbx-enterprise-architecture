"""Word-by-word search over names, identifiers, descriptions and attributes, ranked.

The store narrows the rows (every word must match somewhere); this module ranks
them and says where each matched, so a reader knows why a row is in the list.
No index: a few thousand rows scan in milliseconds on DuckDB and Postgres alike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import Element

SCAN_LIMIT = 5000
SNIPPET_CHARS = 140


@dataclass
class SearchHit:
    element: Element
    rank: int  # 0 name starts with the query, 1 name holds every word, 2 elsewhere
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
    """Where the words matched and how well: name first, then key or identifier, then description, then an attribute."""
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
    return SearchHit(e, 3, "", "", words)


class SearchService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend = backend
        self.registry = registry

    def search(
        self,
        query: str | None,
        type_id: str | list[str] | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SearchHit]:
        """Ranked hits for `query` (every word must match); without a query, the plain listing in name order."""
        words = words_of(query or "")
        if not words:
            rows = self.backend.find_elements(None, type_id, status, limit=limit, offset=offset)
            return [SearchHit(e, 3, "", "", []) for e in rows]
        rows = self.backend.find_elements(" ".join(words), type_id, status, limit=SCAN_LIMIT)
        hits = [rank_hit(e, words) for e in rows]
        hits.sort(key=lambda h: (h.rank, h.element.name.lower(), h.element.element_id))
        return hits[offset : offset + limit]

    def count(
        self, query: str | None, type_id: str | list[str] | None = None, status: str | None = None
    ) -> int:
        words = words_of(query or "")
        return self.backend.count_elements(type_id, " ".join(words) if words else None, status)

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
                    "status": e.status,
                    "current_state": e.current_state,
                    "target_state": e.target_state,
                    "lifecycle_status": e.lifecycle_status,
                    "source_system": e.source_system,
                    "matched_in": h.matched_in,
                    "snippet": h.snippet if h.matched_in not in ("name", "") else "",
                }
            )
        return out
