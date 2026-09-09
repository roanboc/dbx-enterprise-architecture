"""Review before merge: a second person approves a branch, per element type (decision 0009).

A branch goes open -> in_review -> approved -> merged, or back to open when sent
back. The element types its change set touches decide who must approve: the
reviewer assignments per type name users or groups; a type nobody is assigned
to may be approved by any Reviewer. The author never approves their own branch.
"""

from __future__ import annotations

from typing import Any

from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import Branch, ConflictError, Forbidden, NotFoundError, Review
from ea.services.branches import BranchService
from ea.services.roles import current_role, require


class ReviewService:
    def __init__(self, backend: DatabaseBackend, registry: Registry, branches: BranchService):
        self.backend = backend
        self.registry = registry
        self.branches = branches

    # ---------------------------------------------------------- assignments
    def assignments(self) -> dict[str, list[str]]:
        return self.backend.list_reviewer_assignments()

    def set_assignment(self, type_id: str, reviewers: list[str], actor: str) -> None:
        require("assign_reviewers", what="assign reviewers")
        if self.registry.get_type(type_id) is None:
            raise NotFoundError(type_id, "element type")
        self.backend.set_reviewer_assignment(type_id, reviewers, actor)

    def reviewers_for(self, type_id: str) -> list[str]:
        return self.assignments().get(type_id, [])

    def covers(self, type_id: str, actor: str, groups: list[str] | None = None) -> bool:
        """Whether `actor` (with these groups) may approve this type: assigned to it, or nobody is."""
        assigned = self.reviewers_for(type_id)
        if not assigned:
            return True
        mine = {actor, *(groups or [])}
        return bool(mine & set(assigned))

    # ------------------------------------------------------------- reading
    def touched_types(self, branch_id: str) -> list[str]:
        """The element types the branch's change set touches (a relationship counts for both ends)."""
        cs = self.branches.diff(branch_id)
        types: list[str] = []
        for it in cs.items:
            row = it.after or it.before or {}
            if it.kind == "element":
                t = row.get("type_id")
                if t and t not in types:
                    types.append(t)
            else:
                for end in (row.get("src_id"), row.get("dst_id")):
                    e = self.backend.get_element(end) if end else None
                    if e and e.type_id not in types:
                        types.append(e.type_id)
        return types

    def requirements(self, branch_id: str) -> list[dict[str, Any]]:
        """Per touched type: who may approve it and who has, in the current round."""
        approvals = self._current_round(branch_id)
        out = []
        for t in self.touched_types(branch_id):
            typ = self.registry.get_type(t)
            by = sorted({r.reviewer for r in approvals if t in r.type_ids})
            out.append(
                {
                    "type_id": t,
                    "type": typ.name if typ else t,
                    "reviewers": self.reviewers_for(t),
                    "approved_by": by,
                    "approved": bool(by),
                }
            )
        return out

    def _current_round(self, branch_id: str) -> list[Review]:
        """Approvals since the last send-back (a send-back ends a round)."""
        out: list[Review] = []
        for r in self.backend.list_reviews(branch_id):
            if r.decision == "send_back":
                out = []
            elif r.decision == "approve":
                out.append(r)
        return out

    def is_approved(self, branch_id: str) -> bool:
        reqs = self.requirements(branch_id)
        return bool(reqs) and all(r["approved"] for r in reqs)

    def reviews(self, branch_id: str) -> list[Review]:
        return self.backend.list_reviews(branch_id)

    def can_merge(self, branch_id: str, actor: str) -> tuple[bool, str]:
        b = self.branches.get(branch_id)
        if b.status in ("merged", "abandoned"):
            return False, f"the branch is {b.status}"
        role = current_role()
        if role == "admin":
            return (
                True,
                "" if b.status == "approved" else "an admin may merge without a review; the log will say so",
            )
        if role != "architect":
            return False, "only an architect (an approved branch) or an admin may merge"
        if b.status != "approved":
            return False, "the branch must be approved by its reviewers first"
        return True, ""

    # ------------------------------------------------------------- writing
    def request(self, branch_id: str, actor: str) -> Branch:
        require("request_review", what="request a review")
        b = self.branches.get(branch_id)
        if b.status != "open":
            raise ConflictError(f"branch {branch_id} is {b.status}")
        if current_role() != "admin" and b.created_by != actor:
            raise Forbidden("only the branch's author or an admin may request its review")
        if b.changes == 0:
            raise ConflictError("nothing on the branch to review")
        return self.backend.set_branch_status(branch_id, "in_review", actor)

    def approve(
        self,
        branch_id: str,
        actor: str,
        type_ids: list[str] | None = None,
        comment: str = "",
        groups: list[str] | None = None,
    ) -> dict[str, Any]:
        """Approve the given types (default: every touched type the actor covers). Returns what is still pending."""
        require("review", what="approve a branch")
        b = self.branches.get(branch_id)
        if b.status != "in_review":
            raise ConflictError(f"branch {branch_id} is {b.status}, not in review")
        if b.created_by == actor:
            raise Forbidden("the author of a branch may not approve it")
        touched = self.touched_types(branch_id)
        if type_ids:
            wanted = [t for t in type_ids if t in touched]
            if not wanted:
                raise ConflictError("none of the given types is in the branch's change set")
        else:  # every touched type this reviewer covers
            wanted = [t for t in touched if current_role() == "admin" or self.covers(t, actor, groups)]
            if not wanted:
                raise Forbidden(f"{actor} is not a reviewer of any type this branch touches")
        refused = [t for t in wanted if not self.covers(t, actor, groups)]
        if refused and current_role() != "admin":
            names = ", ".join(
                self.registry.get_type(t).name if self.registry.get_type(t) else t for t in refused
            )
            raise Forbidden(f"{actor} is not a reviewer of: {names}")
        self.backend.add_review(
            Review(
                review_id="",
                branch_id=branch_id,
                reviewer=actor,
                decision="approve",
                type_ids=wanted,
                comment=comment,
            )
        )
        reqs = self.requirements(branch_id)
        complete = all(r["approved"] for r in reqs)
        if complete:
            self.backend.set_branch_status(branch_id, "approved", actor)
        return {
            "approved_types": wanted,
            "pending": [r["type_id"] for r in reqs if not r["approved"]],
            "complete": complete,
        }

    def send_back(self, branch_id: str, actor: str, comment: str) -> Branch:
        require("review", what="send a branch back")
        b = self.branches.get(branch_id)
        if b.status not in ("in_review", "approved"):
            raise ConflictError(f"branch {branch_id} is {b.status}")
        if not (comment or "").strip():
            raise ConflictError("say what must change: a send-back needs a comment")
        self.backend.add_review(
            Review(
                review_id="",
                branch_id=branch_id,
                reviewer=actor,
                decision="send_back",
                type_ids=self.touched_types(branch_id),
                comment=comment,
            )
        )
        return self.backend.set_branch_status(branch_id, "open", actor)
