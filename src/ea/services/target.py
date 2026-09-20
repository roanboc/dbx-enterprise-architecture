"""Target state: current versus intended state of every artefact, analysed per work package.

The pack says which element type plays the work package through its notation
(`archimate: WorkPackage`); nothing here names a type.
"""

from __future__ import annotations

from typing import Any

from ea import capacity
from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import CURRENT_STATES, TARGET_STATES, Element, Relationship

# Colours and glyphs for the target states, shared by the badges, the Mermaid and the draw.io markers.
TARGET_STYLE: dict[str, dict[str, str]] = {
    "undecided": {"colour": "gray", "hex": "#868e96", "glyph": "?", "label": "Undecided"},
    "keep": {"colour": "blue", "hex": "#1c7ed6", "glyph": "=", "label": "Keep"},
    "new": {"colour": "green", "hex": "#2f9e44", "glyph": "+", "label": "New"},
    "change": {"colour": "orange", "hex": "#e8590c", "glyph": "Δ", "label": "Change"},
    "decommission": {"colour": "red", "hex": "#c92a2a", "glyph": "×", "label": "Decommission"},
    "merge": {"colour": "violet", "hex": "#7048e8", "glyph": "⇒", "label": "Merge"},
}
CURRENT_STYLE: dict[str, dict[str, str]] = {
    "proposed": {"colour": "grape", "label": "Proposed"},
    "planned": {"colour": "violet", "label": "Planned"},
    "in_implementation": {"colour": "yellow", "label": "In implementation"},
    "live": {"colour": "green", "label": "Live"},
    "retired": {"colour": "red", "label": "Retired"},
    "non_existent": {"colour": "gray", "label": "Non-existent"},
}
# Current states in which the artefact is not (yet, or any more) real: drawn dashed.
NOT_REAL = {"proposed", "planned", "in_implementation", "non_existent"}


def state_label(state: str, vocabulary: dict[str, dict[str, str]]) -> str:
    return vocabulary.get(state, {}).get("label") or state.replace("_", " ")


class TargetStateService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend = backend
        self.registry = registry

    # ----------------------------------------------------- work packages
    def work_package_type(self) -> str | None:
        """The element type that plays the work package, from the pack's notation."""
        for t in self.registry.pack.element_types:
            if (t.notation or {}).get("archimate") == "WorkPackage":
                return t.id
        for t in self.registry.pack.element_types:
            if t.id == "work_package":
                return t.id
        return None

    def work_packages(self) -> list[Element]:
        wp_type = self.work_package_type()
        if not wp_type:
            return []
        return sorted(self.backend.find_elements(type_id=wp_type, limit=10_000), key=lambda e: e.name.lower())

    # ------------------------------------------------------------ queries
    #: The most rows one answer carries back. The page draws them into a table, and a table
    #: nobody can read is not a bound (decision 0019); `truncated_at` says when one was cut.
    MAX_ROWS = 5_000

    def elements(self, work_package: str | None = None, only_changes: bool = False) -> list[Element]:
        """The elements a work package changes. Read in pages and filtered as they arrive, so
        the whole model is never held to answer about a part of it."""
        rows: list[Element] = []
        for page in capacity.pages(
            lambda limit, offset: self.backend.find_elements(limit=limit, offset=offset)
        ):
            for e in page:
                if work_package and e.target_work_package != work_package:
                    continue
                if only_changes and e.target_state in ("undecided", "keep"):
                    continue
                rows.append(e)
            if len(rows) >= self.MAX_ROWS:
                break
        rows.sort(key=lambda e: (TARGET_STATES.index(e.target_state), e.type_id, e.name.lower()))
        return rows[: self.MAX_ROWS]

    def relationships(
        self, work_package: str | None = None, only_changes: bool = False
    ) -> list[Relationship]:
        rows: list[Relationship] = []
        for page in capacity.pages(
            lambda limit, offset: self.backend.find_relationships(limit=limit, offset=offset)
        ):
            for r in page:
                if work_package and r.target_work_package != work_package:
                    continue
                if only_changes and r.target_state in ("undecided", "keep"):
                    continue
                rows.append(r)
            if len(rows) >= self.MAX_ROWS:
                break
        rows.sort(key=lambda r: (TARGET_STATES.index(r.target_state), r.rel_type_id, r.src_id))
        return rows[: self.MAX_ROWS]

    def summary(self, work_package: str | None = None) -> dict[str, Any]:
        """Counts by target state, by current state, and the current-by-target matrix, for a work package or all.

        Counted over every row, page by page — never over what :meth:`elements` hands back,
        which is capped at `MAX_ROWS` because a page has to draw it. A summary that counted
        the capped list would under-report exactly when the model got big enough to matter.
        """
        by_target = {s: 0 for s in TARGET_STATES}
        by_current = {s: 0 for s in CURRENT_STATES}
        matrix = {c: {t: 0 for t in TARGET_STATES} for c in CURRENT_STATES}
        elements = changes = 0
        for page in capacity.pages(
            lambda limit, offset: self.backend.find_elements(limit=limit, offset=offset)
        ):
            for e in page:
                if work_package and e.target_work_package != work_package:
                    continue
                elements += 1
                by_target[e.target_state] += 1
                by_current[e.current_state] += 1
                matrix[e.current_state][e.target_state] += 1
                if e.target_state not in ("undecided", "keep"):
                    changes += 1
        rel_by_target = {s: 0 for s in TARGET_STATES}
        relationships = 0
        for page in capacity.pages(
            lambda limit, offset: self.backend.find_relationships(limit=limit, offset=offset)
        ):
            for r in page:
                if work_package and r.target_work_package != work_package:
                    continue
                relationships += 1
                rel_by_target[r.target_state] += 1
        return {
            "work_package": work_package or "",
            "elements": elements,
            "relationships": relationships,
            "by_target": by_target,
            "by_current": by_current,
            "matrix": matrix,
            "relationships_by_target": rel_by_target,
            "changes": changes,
        }

    def scope_ids(self, work_package: str | None, max_nodes: int = 60) -> list[str]:
        """The elements a target-state view shows: the work package itself, then what it changes, then what it keeps."""
        els = self.elements(work_package)
        changing = [e.element_id for e in els if e.target_state not in ("undecided", "keep")]
        kept = [e.element_id for e in els if e.target_state in ("keep",)]
        undecided = [e.element_id for e in els if e.target_state == "undecided"] if work_package else []
        ids = ([work_package] if work_package else []) + changing + kept + undecided
        return ids[:max_nodes]
