"""Who holds which role: the deployment's grants and the grants an admin keeps (initiative 28, DOBJ3.13).

A role comes from the signed-in person's workspace groups (decision 0008). Two things say which
group gives which role (decision 0028):

* **the deployment's grants** — `EA_ROLE_GROUPS`, matched by a group's name, read-only here and
  never changed by the application, so an admin group named there is always the way back in;
* **the grants an admin keeps in the store** — one per workspace group, application-wide, kept by
  the workspace's identifier for the group and named as the directory names it; one granted by a
  typed name, where the directory could not be searched, is matched by that exact name, in any
  case, until the group is picked from it.

A person's role is the highest either gives; a person no grant reaches is a Reader. The store's
grants are kept a minute per process and forgotten at once by the process that changes one. An
admin cannot lock the application out: not their own Admin, not the last admin grant where the
deployment names no admin group, and never Admin to every person in the workspace — refused when
it is granted, and ignored when a role is resolved, whatever wrote it.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ea.backend.base import DatabaseBackend
from ea.models import GRANTABLE_ROLES, Forbidden, GroupRef, NotFoundError, RoleGrant
from ea.services.identity import (
    ALL_USERS_GROUPS,
    UNSEARCHABLE,
    Directory,
    DirectoryUnavailable,
    as_group_ref,
    directory_for,
)
from ea.services.roles import LABELS, RANK, parse_role_groups, require

log = logging.getLogger(__name__)

GRANT_TTL_SECONDS = 60  # a grant is felt within a minute in every process (decision 0028)
HISTORY_SHOWN = 20
MAX_GROUP_TEXT = 256  # a group's name or identifier; the workspace's own are far shorter


@dataclass(frozen=True)
class Reason:
    """Why a person holds a role: which of their groups gives it, and who said so."""

    role: str
    group: str
    source: str  # "deployment" — EA_ROLE_GROUPS; "grant" — kept in the store
    granted_by: str = ""
    checked: bool = True  # matched by the workspace's identifier; false where by a name

    def how(self) -> str:
        if self.source == "deployment":
            return "set by the deployment"
        return f"granted by {self.granted_by or 'an admin'}" + (
            "" if self.checked else ", matched by its name"
        )


@dataclass
class GrantRow:
    """One line of the grants an admin reads: the deployment's first, then the store's."""

    group: str
    role: str
    source: str  # "deployment" | "grant"
    group_id: str = ""
    note: str = ""
    granted_by: str = ""
    granted_at: datetime | None = None
    checked: bool = True
    missing: bool = False  # the workspace no longer holds a group with this identifier
    now_called: str = ""  # the name the workspace gives the group now, where it was renamed
    ignored: bool = False  # a stored role no grant gives, which counts for nothing


@dataclass
class PersonCheck:
    """What an admin reads when they check someone: the role they get and which group gives it."""

    email: str
    found: bool
    role: str = "reader"
    reasons: list[Reason] = field(default_factory=list)
    groups: list[GroupRef] = field(default_factory=list)
    problem: str = ""


@dataclass
class GrantChange:
    """One change to the grants, as the change log keeps it."""

    when: Any
    actor: str
    op: str  # grant | change | revoke
    group: str
    role: str
    was: str = ""  # the role the group had before a change
    note: str = ""


def is_all_users(name: str | None) -> bool:
    """Whether a group's name is one of the workspace's groups of every person in it."""
    return (name or "").casefold() in ALL_USERS_GROUPS


def _reached_through(grant: RoleGrant, refs: Sequence[GroupRef]) -> tuple[list[GroupRef], bool]:
    """The person's groups a stored grant reaches them through, and whether by the identifier.

    A checked grant is kept by the workspace's identifier, so a group whose identifier is known
    meets it by that alone: a renamed group keeps its role, and a new group given the old name
    does not inherit it. A group known by its name alone — the groups header of a proxy of ours
    carries no identifiers — meets it by the name it was granted under, in any case, or no grant
    picked from the directory would reach anyone there. A typed grant is matched by its name.
    """
    if grant.checked:
        by_id = [r for r in refs if r.id and r.id == grant.group_id]
        if by_id:
            return by_id, True
        called = (grant.group_name or "").casefold()
        return [r for r in refs if called and not r.id and r.name.casefold() == called], False
    typed = grant.group_id.casefold()
    return [r for r in refs if r.name and r.name.casefold() == typed], False


def role_for(
    groups: Iterable[GroupRef | str], deployment: dict[str, set[str]], grants: Iterable[RoleGrant]
) -> tuple[str, list[Reason]]:
    """The highest role these groups give, and every reason, the highest first.

    The deployment's grants match a group by name, in any case. A grant kept in the store matches
    by the workspace's identifier, or by a name where that is all there is (`_reached_through`).
    Only Reviewer, Architect and Admin are given; anything else counts for nothing, so a role
    stored by hand never lifts anyone. Nor does an Admin grant reaching a person through the
    workspace's all-users group, whatever wrote it: every person in the workspace is in it.
    """
    refs = [as_group_ref(g) for g in groups]
    names = {r.name.casefold() for r in refs if r.name}
    reasons: list[Reason] = []
    for role, wanted in deployment.items():
        if role not in GRANTABLE_ROLES:
            continue
        reasons += [Reason(role, g, "deployment") for g in sorted(wanted) if g.casefold() in names]
    for g in grants:
        if g.role not in GRANTABLE_ROLES:
            continue
        through, by_id = _reached_through(g, refs)
        if g.role == "admin":
            everyone = is_all_users(g.group_name or g.group_id)
            through = [] if everyone else [r for r in through if not is_all_users(r.name)]
        if through:
            reasons.append(Reason(g.role, g.group_name or g.group_id, "grant", g.granted_by, by_id))
    reasons.sort(key=lambda r: (-RANK[r.role], r.source != "deployment", r.group.casefold()))
    return (reasons[0].role if reasons else "reader"), reasons


def in_words(role: str, reasons: Sequence[Reason], whose: str = "their") -> str:
    """`Architect — from the group solution-architects (granted by ada)`, or why a Reader is one."""
    label = LABELS.get(role, role)
    top = [r for r in reasons if r.role == role]
    if not top:
        return f"{label} — none of {whose} groups holds a role"
    said = " and ".join(f"{r.group} ({r.how()})" for r in top)
    return f"{label} — from the group{'s' if len(top) > 1 else ''} {said}"


def change_in_words(c: GrantChange) -> str:
    """`ada granted Architect to solution-architects — they design`, as the history reads."""
    role = LABELS.get(c.role, c.role)
    if c.op == "revoke":
        said = f"{c.actor} removed the {role} grant of {c.group}"
    elif c.op == "change":
        said = f"{c.actor} changed {c.group} from {LABELS.get(c.was, c.was)} to {role}"
    else:
        said = f"{c.actor} granted {role} to {c.group}"
    return said + (f" — {c.note}" if c.note and c.op != "revoke" else "")


class AccessService:
    """The role a request is given, and the grants an admin keeps.

    `web` is the web application's service: its role may be a debug persona (decision 0008),
    which never writes grants into the platform's store. The command line acts as its `--as`
    role, with no groups of its own.
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        settings: Any,
        directory: Directory | None = None,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = GRANT_TTL_SECONDS,
        web: bool = False,
    ):
        self.backend, self.settings = backend, settings
        self.directory = directory if directory is not None else directory_for(settings)
        self._clock, self._ttl, self.web = clock, ttl, web
        self._kept: tuple[float, list[RoleGrant]] | None = None
        #: How many times the kept grants were forgotten: a read that began before a change is
        #: not kept after it, or the writer would read the old grants for another minute.
        self._forgotten = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ the deployment's grants
    def deployment(self) -> dict[str, set[str]]:
        """`EA_ROLE_GROUPS`, the roles a grant gives only."""
        return {r: g for r, g in parse_role_groups(self.settings.role_groups).items() if r in GRANTABLE_ROLES}

    def deployment_grants(self) -> list[tuple[str, str]]:
        """(role, group) as the deployment names them, the highest role first."""
        return [
            (role, group)
            for role, groups in sorted(self.deployment().items(), key=lambda kv: -RANK[kv[0]])
            for group in sorted(groups, key=str.casefold)
        ]

    # ------------------------------------------------------------------- the role a request gets
    def _stored(self) -> list[RoleGrant]:
        """The store's grants, kept a minute. A store that cannot be read leaves the deployment's
        grants to decide alone, and says so in the log: nobody is made a Reader by a hiccup when
        the deployment names their group, and nothing is kept, so the next request asks again."""
        now = self._clock()
        with self._lock:
            if self._kept is not None and self._kept[0] > now:
                return self._kept[1]
            began = self._forgotten
        try:
            grants = self.backend.list_role_grants()
        except Exception as exc:  # noqa: BLE001 — the store is down: the deployment's grants stand
            log.warning("could not read the role grants; the deployment's grants decide alone: %s", exc)
            return []
        with self._lock:
            if self._forgotten == began:
                self._kept = (now + self._ttl, grants)
        return grants

    def forget(self) -> None:
        """Drop the kept grants: the next request reads them afresh."""
        with self._lock:
            self._kept = None
            self._forgotten += 1

    def resolve(self, groups: Iterable[GroupRef | str]) -> tuple[str, list[Reason]]:
        """The role these groups give, and why — what every request is given on the platform."""
        return role_for(groups, self.deployment(), self._stored())

    def my_role(self, groups: Iterable[GroupRef | str]) -> tuple[str, list[Reason]]:
        """The signed-in person's own role and where it comes from: anyone reads their own."""
        return self.resolve(groups)

    # --------------------------------------------------------------------------- what admins read
    def grants(self) -> tuple[list[GrantRow], str]:
        """Every grant, the deployment's first, and why the workspace could not be asked whether
        the groups granted to still exist, when it could not."""
        require("grant_roles", what="see who holds which role")
        rows = [GrantRow(group=g, role=r, source="deployment") for r, g in self.deployment_grants()]
        stored = self.backend.list_role_grants()
        known: dict[str, str] | None = None
        problem = ""
        ids = [g.group_id for g in stored if g.checked]
        if ids:
            try:
                known = self.directory.groups_by_id(ids)
            except DirectoryUnavailable as exc:
                problem = f"{UNSEARCHABLE}: {exc}"
        for g in stored:
            now = known.get(g.group_id, "") if known is not None and g.checked else ""
            rows.append(
                GrantRow(
                    group=g.group_name or g.group_id,
                    role=g.role,
                    source="grant",
                    group_id=g.group_id,
                    note=g.note,
                    granted_by=g.granted_by,
                    granted_at=g.granted_at,
                    checked=g.checked,
                    missing=known is not None and g.checked and g.group_id not in known,
                    now_called=now if now and now != g.group_name else "",
                    ignored=g.role not in GRANTABLE_ROLES,
                )
            )
        return rows, problem

    def history(self, limit: int = HISTORY_SHOWN) -> list[GrantChange]:
        """The latest changes to the grants, newest first."""
        require("grant_roles", what="see who holds which role")
        out = []
        for e in self.backend.role_grant_history(max(1, int(limit))):
            before = json.loads(e["before_json"]) if e.get("before_json") else {}
            after = json.loads(e["after_json"]) if e.get("after_json") else {}
            said = after or before
            out.append(
                GrantChange(
                    when=e["changed_at"],
                    actor=e["actor"] or "",
                    op=e["op"],
                    group=said.get("group") or e["entity_id"],
                    role=said.get("role", ""),
                    was=before.get("role", "") if after else "",
                    note=said.get("note", "") or "",
                )
            )
        return out

    def matching(self, name_or_id: str) -> list[RoleGrant]:
        """The store's grants a group's name or identifier means, the surest reading first: the
        grant with exactly that identifier; else those with exactly that name; else those whose
        identifier or name it is in any case. Two groups may share a name, up to its case or
        exactly, so more than one is for the caller to settle by an identifier."""
        require("grant_roles", what="see who holds which role")
        text = " ".join((name_or_id or "").split())
        key = text.casefold()
        held = self.backend.list_role_grants()
        for reading in (
            lambda g: g.group_id == text,
            lambda g: g.group_name == text,
            lambda g: key in (g.group_id.casefold(), g.group_name.casefold()),
        ):
            found = [g for g in held if reading(g)]
            if found:
                return found
        return []

    def find(self, name_or_id: str) -> RoleGrant | None:
        """The one grant a group's name or identifier means, or None; refused where it means
        several, naming each by its identifier."""
        found = self.matching(name_or_id)
        if len(found) > 1:
            raise ValueError(
                f"{len(found)} grants match {name_or_id!r}: "
                + ", ".join(f"{g.group_name or g.group_id} [{g.group_id}]" for g in found)
                + "; name one by its identifier"
            )
        return found[0] if found else None

    def search(self, text: str) -> tuple[list[GroupRef], str]:
        """The workspace's groups whose name holds the text, or why they cannot be searched."""
        require("grant_roles", what="search the workspace's groups")
        try:
            return self.directory.search_groups(text), ""
        except DirectoryUnavailable as exc:
            return [], f"{UNSEARCHABLE}: {exc}"

    def check_person(self, email: str) -> PersonCheck:
        """The role a person gets and which group gives it, from the grants as they stand now."""
        require("grant_roles", what="check another person's role")
        email = (email or "").strip()
        if not email:
            raise ValueError("type the e-mail the person signs in with")
        try:
            groups = self.directory.person_groups(email)
        except DirectoryUnavailable as exc:
            return PersonCheck(email, False, problem=f"{UNSEARCHABLE}: {exc}")
        if groups is None:
            return PersonCheck(email, False, problem=f"nobody signs in as {email} in {self.directory.label}")
        role, reasons = role_for(groups, self.deployment(), self.backend.list_role_grants())
        return PersonCheck(email, True, role, reasons, groups)

    # ------------------------------------------------------------------------------ the changes
    def local_persona_refusal(self) -> str:
        """Why this service writes no grant, or empty. A debug persona is the role locally
        (decision 0008); pointed at the platform's store, it must not grant there."""
        if self.web and self.settings.auth != "databricks" and self.backend.engine == "lakebase":
            return (
                "a local debug persona may not change the role grants in the platform's store: "
                "grant roles where the platform signs people in, or with `ea roles`"
            )
        return ""

    def _refuse_a_local_persona(self) -> None:
        if refusal := self.local_persona_refusal():
            raise Forbidden(refusal)

    def _refuse_the_sample_groups(self) -> None:
        """The sample groups stand in only for a local store: a `sample-…` identifier matches no
        workspace group, so kept in the platform's store it would give nobody the role, and would
        have the workspace's real grants read as gone."""
        if getattr(self.directory, "sample", False) and self.backend.engine == "lakebase":
            raise Forbidden(
                "the sample groups stand in only for a local store, and this is the platform's: "
                "its grants are to the workspace's own groups, searched where a workspace is configured"
            )

    def _named_by_the_directory(self, group_id: str, called: str) -> str:
        """The name the directory gives the group with this identifier. A checked grant is one the
        directory vouches for, so the identifier is what is checked — the all-users rule with it —
        and the name kept beside it is the directory's, never the caller's."""
        try:
            name = self.directory.groups_by_id([group_id]).get(group_id, "")
        except DirectoryUnavailable as exc:
            raise ValueError(
                f"{UNSEARCHABLE} ({exc}), so the identifier {group_id!r} cannot be checked: grant the "
                "group by its exact name instead, or again once they can be searched"
            ) from exc
        if not name:
            given = f" (given for {called!r})" if called and called != group_id else ""
            raise NotFoundError(
                group_id,
                "group",
                f"no group in {self.directory.label} has the identifier {group_id!r}{given}: "
                "pick the group from the list, or check its identifier",
            )
        return self._text(name, "the group's name")

    def _keep_an_admin(
        self, before: list[RoleGrant], after: list[RoleGrant], acting: Sequence[GroupRef | str] | None
    ) -> None:
        """Nobody locks the application out by accident (decision 0028)."""
        deployment = self.deployment()
        if acting is not None:
            was, _ = role_for(acting, deployment, before)
            now, _ = role_for(acting, deployment, after)
            if was == "admin" and now != "admin":
                raise Forbidden(
                    "an admin may not remove or lower the grant their own Admin rests on: "
                    "another admin can, if it is meant"
                )
        if not deployment.get("admin"):
            # an Admin grant to the all-users group lifts nobody (`role_for`), so it keeps no admin
            def admits(g: RoleGrant) -> bool:
                return g.role == "admin" and not is_all_users(g.group_name or g.group_id)

            if any(admits(g) for g in before) and not any(admits(g) for g in after):
                raise Forbidden(
                    "the last admin grant stays: the deployment names no admin group, so without it "
                    "nobody could administer the application — grant Admin to another group first"
                )

    @staticmethod
    def _text(value: str | None, what: str) -> str:
        text = " ".join((value or "").split())
        if len(text) > MAX_GROUP_TEXT:
            raise ValueError(f"{what} is longer than any the workspace gives ({MAX_GROUP_TEXT} characters)")
        return text

    def grant(
        self,
        group_id: str,
        group_name: str,
        role: str,
        note: str,
        checked: bool,
        actor: str,
        acting: Sequence[GroupRef | str] | None = None,
    ) -> RoleGrant:
        """Grant a role to a workspace group, or replace the role it holds.

        `checked` says the group was picked from the directory, by its identifier: the directory
        is asked again for the group with that identifier, which it must still hold, and its name
        is the one kept. Unchecked, the exact name typed is the identifier and the name, and it is
        matched by that name in any case. `group_name` is only what the caller called the group,
        so a value that came back from a browser is never believed. A grant typed with the name
        this one also means — the group picked from the directory, or the same name typed in
        another case — is replaced by it. `acting` is the groups of the admin making the change,
        where they are known, so their own Admin is kept.
        """
        require("grant_roles", what="grant a role")
        self._refuse_a_local_persona()
        self._refuse_the_sample_groups()
        role = (role or "").strip().lower()
        if role not in GRANTABLE_ROLES:
            raise ValueError(
                f"{role or 'nothing'} is not a role a grant gives: grant Reviewer, Architect or Admin "
                "— Reader is everybody's, and Agent is the assistant's"
            )
        group_id = self._text(group_id, "the group's identifier")
        if not group_id:
            raise ValueError("name the workspace group the role is granted to")
        if checked:
            group_name = self._named_by_the_directory(group_id, " ".join((group_name or "").split()))
        else:
            group_name = group_id
        if role == "admin" and is_all_users(group_name):
            raise Forbidden(
                f"Admin is never granted to {group_name}, the workspace's group of every person in it: "
                "it would make every person in the workspace an admin"
            )
        new = RoleGrant(group_id, group_name, role, " ".join((note or "").split()), bool(checked))
        with self.backend.transaction():
            held = self.backend.list_role_grants(lock=True)
            typed = [
                g
                for g in held
                if not g.checked and g.group_id != group_id and g.group_id.casefold() == group_name.casefold()
            ]
            after = [g for g in held if g.group_id != group_id and g not in typed] + [new]
            self._keep_an_admin(held, after, acting)
            for g in typed:
                self.backend.delete_role_grant(g.group_id, actor)
            kept = self.backend.set_role_grant(new, actor)
        self.forget()
        return kept

    def revoke(self, group_id: str, actor: str, acting: Sequence[GroupRef | str] | None = None) -> RoleGrant:
        """Remove a group's grant; the change log keeps what it was and who removed it."""
        require("grant_roles", what="remove a role grant")
        self._refuse_a_local_persona()
        self._refuse_the_sample_groups()
        with self.backend.transaction():
            held = self.backend.list_role_grants(lock=True)
            gone = next((g for g in held if g.group_id == group_id), None)
            if gone is None:
                raise NotFoundError(group_id, "role grant", f"no role is granted to the group {group_id!r}")
            self._keep_an_admin(held, [g for g in held if g.group_id != group_id], acting)
            self.backend.delete_role_grant(group_id, actor)
        self.forget()
        return gone
