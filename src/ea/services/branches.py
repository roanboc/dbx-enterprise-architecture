"""Branches: create, list, diff, merge item by item, abandon.

A branch is an overlay on `main` (decision 0006). This service is what the app,
the CLI and the Propose module call; the store does the reading and writing.
"""

from __future__ import annotations

from typing import Any

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, branch_id_from_name, current_branch, use_branch
from ea.metamodel.registry import Registry
from ea.models import Branch, ChangeItem, ChangeSet, ConflictError, Forbidden, MergeResult, NotFoundError
from ea.services.roles import current_role, require


class BranchService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend = backend
        self.registry = registry

    # -------------------------------------------------------------- reads
    def current(self) -> str:
        return current_branch()

    def get(self, branch_id: str) -> Branch:
        b = self.backend.get_branch(branch_id)
        if b is None:
            raise NotFoundError(branch_id)
        return b

    def list(self, status: str | None = None) -> list[Branch]:
        return self.backend.list_branches(status)

    def open(self) -> list[Branch]:
        return self.backend.list_branches("open")

    def diff(self, branch_id: str) -> ChangeSet:
        return self.backend.diff_branch(branch_id)

    # ------------------------------------------------------------- writes
    def create(
        self,
        name: str,
        actor: str,
        description: str = "",
        work_package: str = "",
        branch_id: str | None = None,
    ) -> Branch:
        require("create_branch", what="create a branch")
        bid = branch_id or branch_id_from_name(name)
        if bid == MAIN:
            raise ConflictError("'main' is the model itself, not a branch")
        if work_package and self.backend.get_element(work_package) is None:
            raise NotFoundError(work_package)
        return self.backend.create_branch(
            Branch(
                branch_id=bid, name=name.strip() or bid, description=description, work_package=work_package
            ),
            actor,
        )

    def merge(
        self,
        branch_id: str,
        actor: str,
        include: set[str] | None = None,
        resolutions: dict[str, str] | None = None,
    ) -> MergeResult:
        """Merge the ticked items (all when `include` is None); conflicts need a resolution.

        An architect merges an approved branch; an admin may merge any open branch, and the
        change log then says the merge happened without a review (decision 0009)."""
        require("merge", what="merge a branch")
        b = self.get(branch_id)
        if b.status != "approved":
            require("merge_without_review", what="merge a branch that is not approved")
            if b.status in ("open", "in_review"):
                self.backend._log(
                    "branch", branch_id, "merge_without_review", actor, None, {"status": b.status}, None, MAIN
                )  # noqa: SLF001
        return self.backend.merge_branch(branch_id, actor, include, resolutions)

    def abandon(self, branch_id: str, actor: str) -> Branch:
        require("abandon_branch", what="abandon a branch")
        b = self.get(branch_id)
        if current_role() != "admin" and b.created_by != actor:
            raise Forbidden("an architect may abandon only their own branch")
        return self.backend.abandon_branch(branch_id, actor)

    # ------------------------------------------------------------ helpers
    def use(self, branch_id: str | None):
        """A context manager that runs its body on the given branch (`None` = main)."""
        return use_branch(branch_id)

    def item_rows(self, change_set: ChangeSet) -> list[dict[str, Any]]:
        """The change set as flat rows for a grid: one per item, with the merge-log columns."""
        rows = []
        for it in change_set.items:
            rows.append(
                {
                    "key": it.key,
                    "kind": it.kind,
                    "entity_id": it.entity_id,
                    "label": self._label(it),
                    "change": it.change,
                    "fields": ", ".join(it.fields_changed) if it.change == "changed" else "",
                    "base_version": it.base_version,
                    "main_version": it.main_version,
                    # The word, not a boolean: a grid draws a boolean as a checkbox, and a
                    # checkbox in this row reads as one more thing to tick.
                    "conflict": "conflict" if it.conflict else "",
                    "resolution": "branch" if it.conflict else "",
                    "include": True,
                }
            )
        return rows

    def _label(self, it: ChangeItem) -> str:
        if it.kind == "element":
            row = it.after or it.before or {}
            t = self.registry.get_type(row.get("type_id", ""))
            return f"{row.get('name', it.entity_id)} ({t.name if t else row.get('type_id', '')})"
        row = it.after or it.before or {}
        rt = self.registry.rel_types.get(row.get("rel_type_id", ""))
        src = self.backend.get_element(row.get("src_id", ""))
        dst = self.backend.get_element(row.get("dst_id", ""))
        q = f" ({row['qualifier']})" if row.get("qualifier") else ""
        return (
            f"{src.name if src else row.get('src_id')} {rt.name if rt else row.get('rel_type_id')}{q} "
            f"{dst.name if dst else row.get('dst_id')}"
        )

    @staticmethod
    def field_diff(it: ChangeItem) -> list[tuple[str, Any, Any]]:
        """(field, main value, branch value) for what differs, in a stable order."""
        skip = {"version", "created_at", "created_by", "updated_at", "updated_by"}
        before, after = it.before or {}, it.after or {}
        keys = [k for k in list(after) + [k for k in before if k not in after] if k not in skip]
        out = []
        for k in keys:
            if it.change == "changed" and before.get(k) == after.get(k):
                continue
            out.append((k, before.get(k), after.get(k)))
        return out
