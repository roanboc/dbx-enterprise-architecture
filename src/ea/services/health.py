"""The model's health: freshness per source system and completeness per element type.

Every figure comes with the identifiers behind it, so a page can send the reader
from a number to the rows to fix. Computed on the current branch, in Python,
from the store's ordinary reads; nothing here is stored.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import Element, Relationship

STALE_DAYS = (30, 90, 180)
ACTIVITY_WEEKS = 12
COMPLETENESS_FACETS = ("description", "links", "relationships", "attributes", "target")


def _naive(ts: Any) -> datetime | None:
    if ts is None or isinstance(ts, str) and not ts:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return None
    if not isinstance(ts, datetime):
        try:
            ts = ts.to_pydatetime()
        except AttributeError:
            return None
    return ts.replace(tzinfo=None) if ts.tzinfo else ts


class HealthService:
    def __init__(self, backend: DatabaseBackend, registry: Registry, now: datetime | None = None):
        self.backend = backend
        self.registry = registry
        self._pinned = now

    @property
    def now(self) -> datetime:
        """Read when it is asked for.

        The service is built once and answers for the life of the process, so a moment
        captured at construction is the moment the application started — and every figure
        measured against it drifts a little further from true with every hour it runs.
        """
        return self._pinned or datetime.now(UTC).replace(tzinfo=None)

    # ------------------------------------------------------------ freshness
    def freshness(self) -> dict[str, Any]:
        """Per source system: counts, last load, rows not updated in 30/90/180 days, never-updated rows; plus weekly activity."""
        elements = self.backend.find_elements(limit=1_000_000)
        rels = self.backend.find_relationships(limit=1_000_000)
        by_source: dict[str, dict[str, Any]] = {}
        for e in elements:
            src = e.source_system or "(authored)"
            row = by_source.setdefault(src, self._empty_source(src))
            self._count(row, e, e.element_id)
        for r in rels:
            src = r.source_system or "(authored)"
            row = by_source.setdefault(src, self._empty_source(src))
            row["relationships"] += 1
        rows = sorted(by_source.values(), key=lambda r: -r["elements"])
        for row in rows:
            row["last_updated"] = str(row["last_updated"])[:16] if row["last_updated"] else ""
            row["first_loaded"] = str(row["first_loaded"])[:16] if row["first_loaded"] else ""
        return {"sources": rows, "activity": self.activity(), "as_of": self.now.isoformat(timespec="minutes")}

    def _empty_source(self, src: str) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source": src,
            "elements": 0,
            "relationships": 0,
            "last_updated": None,
            "first_loaded": None,
            "never_updated": 0,
            "never_updated_ids": [],
        }
        for days in STALE_DAYS:
            d[f"stale_{days}"] = 0
            d[f"stale_{days}_ids"] = []
        return d

    def _count(self, row: dict[str, Any], e: Element, eid: str) -> None:
        row["elements"] += 1
        upd, cre = _naive(e.updated_at), _naive(e.created_at)
        if upd and (row["last_updated"] is None or upd > row["last_updated"]):
            row["last_updated"] = upd
        if cre and (row["first_loaded"] is None or cre < row["first_loaded"]):
            row["first_loaded"] = cre
        if upd and cre and abs((upd - cre).total_seconds()) < 1 and e.version <= 1:
            row["never_updated"] += 1
            row["never_updated_ids"].append(eid)
        if upd:
            age = (self.now - upd).days
            for days in STALE_DAYS:
                if age >= days:
                    row[f"stale_{days}"] += 1
                    row[f"stale_{days}_ids"].append(eid)

    def activity(self, weeks: int = ACTIVITY_WEEKS) -> list[dict[str, Any]]:
        """Change-log entries per ISO week for the last `weeks` weeks, by kind of operation."""
        first = self.now - timedelta(weeks=weeks - 1)
        since = first - timedelta(days=first.weekday())  # the Monday the first week begins on
        counts: dict[str, Counter] = defaultdict(Counter)
        for h in self.backend.history(None, 20_000):
            ts = _naive(h.get("changed_at"))
            if ts is None or ts < since:
                continue
            year, week, _ = ts.isocalendar()
            counts[f"{year}-W{week:02d}"][h.get("op") or "?"] += 1
        out = []
        cursor = first
        while cursor <= self.now:
            y, w, _ = cursor.isocalendar()
            key = f"{y}-W{w:02d}"
            c = counts.get(key, Counter())
            out.append({"week": key, "total": sum(c.values()), "by_op": dict(c)})
            cursor += timedelta(weeks=1)
        seen = set()
        return [r for r in out if not (r["week"] in seen or seen.add(r["week"]))]

    # --------------------------------------------------------- completeness
    def completeness(self) -> dict[str, Any]:
        """Per element type: how many have a description, a link, a relationship, every required attribute, a decided target."""
        elements = self.backend.find_elements(limit=1_000_000)
        linked = set(self.backend.linked_element_ids())
        related: set[str] = set()
        for row in self.backend.edges_frame().itertuples(index=False):
            related.add(row.src_id)
            related.add(row.dst_id)
        by_type: dict[str, list[Element]] = defaultdict(list)
        for e in elements:
            by_type[e.type_id].append(e)
        rows = []
        for type_id, els in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
            t = self.registry.get_type(type_id)
            required = [a.name for a in self.registry.attributes_for(type_id) if a.required]
            missing: dict[str, list[str]] = {k: [] for k in COMPLETENESS_FACETS}
            for e in els:
                if not (e.description_md or "").strip():
                    missing["description"].append(e.element_id)
                if e.element_id not in linked:
                    missing["links"].append(e.element_id)
                if e.element_id not in related:
                    missing["relationships"].append(e.element_id)
                if any(e.attrs.get(a) in (None, "") for a in required):
                    missing["attributes"].append(e.element_id)
                if e.target_state == "undecided":
                    missing["target"].append(e.element_id)
            n = len(els)
            row: dict[str, Any] = {
                "type_id": type_id,
                "type": t.name if t else type_id,
                "domain": t.domain if t else "",
                "elements": n,
                "required_attributes": required,
            }
            for k in COMPLETENESS_FACETS:
                row[f"{k}_missing"] = len(missing[k])
                row[f"{k}_pct"] = round(100 * (n - len(missing[k])) / n) if n else 0
                row[f"{k}_ids"] = missing[k]
            rows.append(row)
        totals = {k: sum(r[f"{k}_missing"] for r in rows) for k in COMPLETENESS_FACETS}
        return {"types": rows, "elements": len(elements), "missing": totals}

    def relationship_coverage(self) -> list[dict[str, Any]]:
        """Declared relationship types with no instance at all, per element type with content."""
        by_rel = self.backend.count_by_rel_type()
        out = []
        for r in self.registry.pack.relationship_types:
            if by_rel.get(r.id, 0) == 0:
                out.append({"rel_type_id": r.id, "name": r.name, "source": r.source, "target": r.target})
        return out

    # --------------------------------------------------------------- filters
    def ids_for(
        self, facet: str, type_id: str | None = None, source: str | None = None, days: int = 90
    ) -> set[str]:
        """The element ids behind one figure: a completeness facet per type, or a staleness bucket per source."""
        if facet in COMPLETENESS_FACETS:
            out: set[str] = set()
            for row in self.completeness()["types"]:
                if type_id and row["type_id"] != type_id:
                    continue
                out.update(row[f"{facet}_ids"])
            return out
        if facet in ("stale", "never_updated"):
            key = f"stale_{days}_ids" if facet == "stale" else "never_updated_ids"
            out = set()
            for row in self.freshness()["sources"]:
                if source and row["source"] != source:
                    continue
                out.update(row.get(key, []))
            return out
        return set()

    @staticmethod
    def relationship_ids(rels: list[Relationship]) -> list[str]:
        return [r.relationship_id for r in rels]
