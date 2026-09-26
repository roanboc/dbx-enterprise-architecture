"""The tools an agent may call. Every number and identifier in an answer must come from here."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, current_branch
from ea.metamodel.registry import Registry
from ea.models import ElementFilter, NotFoundError
from ea.services import GraphService, RepositoryService

MAX_RESULT_CHARS = 12_000


def _element_brief(e) -> dict[str, Any]:
    return {
        "element_id": e.element_id,
        "type_id": e.type_id,
        "name": e.name,
        "key": e.key,
        "status": e.status,
        "lifecycle_status": e.lifecycle_status,
        "current_state": e.current_state,
        "target_state": e.target_state,
        "target_work_package": e.target_work_package,
        "description": (e.description_md or "")[:400],
        "attrs": e.attrs,
    }


class ToolBox:
    """Read-only tools over the repository, described once for any provider."""

    def __init__(
        self,
        backend: DatabaseBackend,
        registry: Registry,
        repo: RepositoryService,
        graph: GraphService,
        connected: Callable[[], Any] | None = None,
    ):
        self.backend, self.registry, self.repo, self.graph = backend, registry, repo, graph
        self.seen_ids: set[str] = set()
        self.requested_views: list[dict[str, Any]] = []  # views the model asked for, drawn by the app
        # The enterprise's connected systems (initiative 26): `connected()` makes the reader of
        # one answer, for the person and organisation of the request; `reader` is that answer's.
        self.connected = connected
        self.reader: Any = None

    def begin(self) -> None:
        """A new answer: what the last one read is forgotten, and the connected systems are read afresh."""
        self.seen_ids.clear()
        self.requested_views.clear()
        self.reader = None
        if self.connected is not None:
            try:
                self.reader = self.connected()
            except Exception:  # noqa: BLE001 — the model's own tools answer without them
                self.reader = None

    # ------------------------------------------------------------- specs
    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_types",
                "description": "List the element types and relationship types of the loaded metamodel, with counts of instances. Call this first when unsure what exists.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "search_elements",
                "description": "Find elements by name, key, id or description text, optionally restricted to a type. Returns at most `limit` matches.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "search text (case-insensitive substring)"},
                        "type_id": {"type": "string", "description": "optional element type id or name"},
                        "limit": {"type": "integer", "default": 25},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_element",
                "description": "Full detail of one element: description, attributes, links and every relationship in and out with the other element's id, type and name.",
                "input_schema": {
                    "type": "object",
                    "properties": {"element_id": {"type": "string"}},
                    "required": ["element_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "neighbours",
                "description": "Elements within N hops of an element (both directions by default).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string"},
                        "depth": {"type": "integer", "default": 1},
                        "direction": {"type": "string", "enum": ["both", "in", "out"], "default": "both"},
                    },
                    "required": ["element_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "trace",
                "description": "Transitive reach along relationship direction. direction='in' answers 'what depends on this?' (upstream dependants); 'out' answers 'what does this depend on?'. Each row carries the relationship labels walked.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string"},
                        "direction": {"type": "string", "enum": ["in", "out"], "default": "in"},
                        "max_depth": {"type": "integer", "default": 4},
                    },
                    "required": ["element_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "impact",
                "description": "Blast radius of changing an element: upstream dependants and downstream dependencies grouped by type, plus a completeness footer saying which relationship types for that element type have no instances at all.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string"},
                        "max_depth": {"type": "integer", "default": 3},
                    },
                    "required": ["element_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "allowed_relationships",
                "description": "The relationship types the metamodel allows from one element type to another, with their names, inverse names and qualifiers. Call it before proposing a relationship between two types.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source_type": {"type": "string", "description": "element type id or name"},
                        "target_type": {"type": "string", "description": "element type id or name"},
                    },
                    "required": ["source_type", "target_type"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "branch_changes",
                "description": "What the branch being read already changes against main: elements and relationships added, changed or deleted, with their target states. Empty on main.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "propose_view",
                "description": (
                    "Ask for an architecture diagram of the named elements to be included in the answer document. "
                    "Call it once you know the element ids that matter (after search, get_element, impact or trace). "
                    "The app draws the diagram from the model; you only name the elements and a title."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title for the diagram"},
                        "element_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Element ids to show (2 to 40)",
                        },
                    },
                    "required": ["title", "element_ids"],
                },
            },
            {
                "name": "run_sql",
                "description": "Read-only SQL over tables element(element_id, type_id, key, name, description_md, status, lifecycle_status, source_system, attrs JSON text), relationship(relationship_id, rel_type_id, src_id, dst_id, qualifier, status), element_link(element_id, url, label), meta_element_type, meta_relationship_type. The tables read as the organisation you are answering for and the metamodel version it applies; no filter on organisation or version is needed. Use for counts and set questions the other tools do not cover.",
                "input_schema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}, "limit": {"type": "integer", "default": 200}},
                    "required": ["sql"],
                    "additionalProperties": False,
                },
            },
        ]

    def all_specs(self) -> list[dict[str, Any]]:
        """The model's tools, and the connected systems' this answer may read."""
        specs = self.specs()
        if self.reader is not None:
            specs = specs + self.reader.specs()
        return specs

    # ---------------------------------------------------------- dispatch
    def call(self, name: str, args: dict[str, Any]) -> str:
        if self.reader is not None and self.reader.has(name):
            # what a connected system says is cited as the system's: never remembered as an
            # identifier the model returned, so the grounding check does not count it (P6)
            text = json.dumps(self.reader.call(name, args or {}), ensure_ascii=False, default=str)
            return text[:MAX_RESULT_CHARS]
        try:
            result = getattr(self, "tool_" + name)(**(args or {}))
        except NotFoundError as exc:
            result = {"error": str(exc)}
        except AttributeError:
            result = {"error": f"unknown tool {name}"}
        except Exception as exc:  # noqa: BLE001 — the model must see the failure, not the process
            result = {"error": f"{type(exc).__name__}: {exc}"}
        self._remember(result)
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + '... [truncated; narrow the query]"}'
        return text

    def _remember(self, obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("element_id", "src_id", "dst_id", "relationship_id") and isinstance(v, str):
                    self.seen_ids.add(v)
                else:
                    self._remember(v)
        elif isinstance(obj, list):
            for v in obj:
                self._remember(v)

    # ------------------------------------------------------------- tools
    def tool_propose_view(self, title: str, element_ids: list[str]) -> dict[str, Any]:
        ids = [i for i in (element_ids or []) if isinstance(i, str)]
        # asked of the store, not the in-process graph: that one is refused past the size the
        # application builds it at, and a view of forty elements needs forty rows (decision 0019)
        known = {e.element_id for e in self.backend.elements_by_ids(ids)}
        accepted = [i for i in ids if i in known][:40]
        unknown = [i for i in ids if i not in known]
        if accepted:
            self.requested_views.append({"title": (title or "View")[:120], "element_ids": accepted})
        return {"accepted": accepted, "unknown": unknown, "views_requested": len(self.requested_views)}

    def tool_allowed_relationships(self, source_type: str, target_type: str) -> dict[str, Any]:
        src, dst = self.registry.resolve_type(source_type), self.registry.resolve_type(target_type)
        if src is None or dst is None:
            return {
                "error": f"unknown type {(source_type if src is None else target_type)!r}",
                "hint": "call list_types",
            }
        return {
            "source_type": src.id,
            "target_type": dst.id,
            "relationships": [
                {"id": r.id, "name": r.name, "inverse": r.inverse, "qualifiers": list(r.qualifiers or [])}
                for r in self.registry.allowed_rel_types(src.id, dst.id)
            ],
        }

    #: The most rows `branch_changes` returns; a longer change set says it was cut.
    MAX_BRANCH_ROWS = 200

    def tool_branch_changes(self) -> dict[str, Any]:
        branch = current_branch()
        if branch == MAIN:
            return {"branch": MAIN, "changes": [], "note": "reading main: there is no branch to compare"}
        items = self.backend.diff_branch(branch).items
        rows = []
        for it in items[: self.MAX_BRANCH_ROWS]:
            row = it.after or it.before or {}
            rows.append(
                {
                    "kind": it.kind,
                    "change": it.change,
                    # named the way the grounding record reads an identifier (`_remember`)
                    ("element_id" if it.kind == "element" else "relationship_id"): it.entity_id,
                    "name": row.get("name") or "",
                    "type_id": row.get("type_id") or row.get("rel_type_id") or "",
                    "src_id": row.get("src_id") or "",
                    "dst_id": row.get("dst_id") or "",
                    "target_state": row.get("target_state") or "",
                }
            )
        return {"branch": branch, "changes": rows, "truncated": len(items) > self.MAX_BRANCH_ROWS}

    def tool_list_types(self) -> dict[str, Any]:
        s = self.repo.stats()
        return {
            "pack": self.registry.pack.name,
            "element_types": [r for r in s["by_type"] if r["active"] or r["count"]],
            "relationship_types": [r for r in s["by_rel_type"] if r["count"]],
            "totals": {"elements": s["elements"], "relationships": s["relationships"]},
        }

    def tool_search_elements(self, text: str, type_id: str | None = None, limit: int = 25) -> dict[str, Any]:
        t = self.registry.resolve_type(type_id) if type_id else None
        if type_id and t is None:
            return {"error": f"unknown type {type_id!r}", "hint": "call list_types"}
        rows = self.repo.search(
            ElementFilter(text=text or "", type_ids=[t.id] if t else []),
            limit=max(1, min(int(limit or 25), 100)),
        )
        return {"matches": [_element_brief(e) for e in rows], "count": len(rows)}

    def tool_get_element(self, element_id: str) -> dict[str, Any]:
        d = self.repo.element_detail(element_id)
        e = d["element"]
        return {
            "element": dict(
                _element_brief(e),
                description=e.description_md,
                type_name=d["type"].name if d["type"] else e.type_id,
            ),
            "links": [{"url": ln.url, "label": ln.label} for ln in d["links"]],
            "outgoing": [
                {
                    "relationship": r["label"],
                    "qualifier": r["relationship"].qualifier,
                    "element_id": r["relationship"].dst_id,
                    "name": r["other"].name if r["other"] else None,
                    "type_id": r["other"].type_id if r["other"] else None,
                }
                for r in d["outgoing"]
            ],
            "incoming": [
                {
                    "relationship": r["label"],
                    "qualifier": r["relationship"].qualifier,
                    "element_id": r["relationship"].src_id,
                    "name": r["other"].name if r["other"] else None,
                    "type_id": r["other"].type_id if r["other"] else None,
                }
                for r in d["incoming"]
            ],
        }

    def tool_neighbours(self, element_id: str, depth: int = 1, direction: str = "both") -> dict[str, Any]:
        sub = self.graph.neighbours(element_id, max(1, min(int(depth or 1), 4)), direction, max_nodes=150)
        return {
            "centre": sub["centre"],
            "nodes": sub["nodes"],
            "edges": sub["edges"],
            "truncated": sub["truncated"],
        }

    def tool_trace(self, element_id: str, direction: str = "in", max_depth: int = 4) -> dict[str, Any]:
        rows = self.graph.trace(element_id, direction, max(1, min(int(max_depth or 4), 8)))
        return {
            "element_id": element_id,
            "direction": direction,
            "rows": [{k: v for k, v in r.items() if k != "path"} for r in rows],
            "count": len(rows),
        }

    def tool_impact(self, element_id: str, max_depth: int = 3) -> dict[str, Any]:
        res = self.graph.impact(element_id, max(1, min(int(max_depth or 3), 6)))

        def slim(rows):
            return [
                {
                    "element_id": r["element_id"],
                    "name": r["name"],
                    "type_name": r["type_name"],
                    "depth": r["depth"],
                    "via": r["rel_labels"],
                }
                for r in rows
            ]

        return {
            "element": res["element"],
            "upstream_dependants": slim(res["upstream"]),
            "downstream_dependencies": slim(res["downstream"]),
            "by_type": res["by_type"],
            "completeness": {k: v for k, v in res["completeness"].items() if k != "rows"},
        }

    def tool_run_sql(self, sql: str, limit: int = 200) -> dict[str, Any]:
        df = self.backend.query(sql, limit=max(1, min(int(limit or 200), 1000)))
        return {
            "columns": list(df.columns),
            "rows": df.astype(object).where(df.notna(), None).values.tolist()[:limit],
            "row_count": len(df),
        }
