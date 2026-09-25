"""The deep dive catalogue (ASVC14, decision 0024): keeping, finding, rating and withdrawing.

A deep dive is kept the moment it is written, filed under the element types and domains of
what it is about, and read back from the organisation's own store. Who may do what is the
roles module's to say; this service asks it on every write, and adds the one rule the table
cannot hold — that a deep dive is withdrawn by its author, or by an admin.
"""

from __future__ import annotations

from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import DeepDive, DeepDiveRating, Forbidden, NotFoundError
from ea.services.roles import LABELS, a_role, current_role, require


class DeepDiveService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend = backend
        self.registry = registry

    # ------------------------------------------------------------- keeping
    def catalogue_entry(self, element_ids: list[str]) -> tuple[list[str], list[str]]:
        """(domains, element types) of the elements a deep dive is about, as the catalogue files it."""
        types: set[str] = set()
        for e in self.backend.elements_by_ids(sorted(set(element_ids))):
            types.add(e.type_id)
        domains = {self.registry.get_type(t).domain for t in types if self.registry.get_type(t) is not None}
        return sorted(d for d in domains if d), sorted(types)

    def keep(self, d: DeepDive, actor: str) -> DeepDive:
        require("keep_deep_dive", what="keep a deep dive")
        d.created_by = actor
        subject = [e.element_id for e in d.elements if e.role == "subject"] or list(
            d.brief.get("subject") or []
        )
        if not (d.domain_ids and d.type_ids):
            d.domain_ids, d.type_ids = self.catalogue_entry(subject)
        return self.backend.save_deep_dive(d)

    # ------------------------------------------------------------- reading
    def get(self, deep_dive_id: str) -> DeepDive | None:
        return self.backend.get_deep_dive(deep_dive_id)

    def catalogue(self, **narrow) -> tuple[list[DeepDive], int]:
        """One page of the catalogue: see `DatabaseBackend.list_deep_dives` for what narrows it."""
        return self.backend.list_deep_dives(**narrow)

    def on_element(self, element_id: str, limit: int = 20) -> list[DeepDive]:
        """The kept deep dives that cite an element, best rated first — what its page lists."""
        return self.backend.deep_dives_for_elements([element_id], limit)

    def earlier(self, element_ids: list[str], limit: int = 5) -> list[DeepDive]:
        """The kept deep dives on any of these elements, best rated first — what a new one weighs."""
        return self.backend.deep_dives_for_elements(element_ids, limit)

    def ratings(self, deep_dive_id: str) -> list[DeepDiveRating]:
        return self.backend.deep_dive_ratings(deep_dive_id)

    # ------------------------------------------------------------- judging
    def rate(self, deep_dive_id: str, actor: str, stars: int, comment: str = "") -> None:
        require("rate_deep_dive", what="rate a deep dive")
        self.backend.rate_deep_dive(DeepDiveRating(deep_dive_id, actor, int(stars), (comment or "").strip()))

    def withdraw(self, deep_dive_id: str, actor: str) -> None:
        require("withdraw_deep_dive", what="withdraw a deep dive")
        held = self.get(deep_dive_id)
        if held is None:
            raise NotFoundError(deep_dive_id, "deep dive")
        role = current_role()
        if role != "admin" and held.created_by != actor:
            raise Forbidden(
                f"{a_role(LABELS.get(role, role))} may withdraw only a deep dive of their own; "
                f"this one is {held.created_by or 'somebody else'}'s, and an admin may withdraw it"
            )
        self.backend.set_deep_dive_status(deep_dive_id, "withdrawn", actor)
