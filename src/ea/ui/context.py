"""One application context: settings, store, registry, services, agent, current user and role."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from ea.agent import Agent
from ea.agent.proposal import ProposalService
from ea.agent.tools import ToolBox
from ea.backend import DatabaseBackend, backend_from_settings
from ea.backend.branching import MAIN, current_branch
from ea.config import Settings
from ea.metamodel import Registry, load_pack
from ea.models import User
from ea.services import (
    BranchService,
    GraphService,
    HealthService,
    RepositoryService,
    ReviewService,
    SearchService,
    TargetStateService,
)
from ea.services.identity import WorkspaceGroups, forwarded_identity
from ea.services.roles import LABELS, allowed, current_role, parse_role_groups, role_from_groups

log = logging.getLogger(__name__)
_lock = threading.Lock()
_context: AppContext | None = None

# The debug personas of mock authentication: a fixed name and group per role, so a review can be
# walked locally by switching persona (decision 0008). Never used on the platform.
PERSONAS = {
    "admin": User("admin@example.edu", "Ada (Admin)", ["ea-admins"], "admin"),
    "architect": User("architect@example.edu", "Arjun (Architect)", ["ea-architects"], "architect"),
    "reviewer": User("reviewer@example.edu", "Rae (Reviewer)", ["ea-reviewers"], "reviewer"),
    "reader": User("reader@example.edu", "Ren (Reader)", [], "reader"),
    "agent": User("assistant@example.edu", "The assistant (Agent)", [], "agent"),
}


def persona_user(persona: str) -> User:
    return PERSONAS.get(persona, PERSONAS["admin"])


@dataclass
class AppContext:
    settings: Settings
    backend: DatabaseBackend
    registry: Registry
    repo: RepositoryService = field(init=False)
    graph: GraphService = field(init=False)
    branches: BranchService = field(init=False)
    target: TargetStateService = field(init=False)
    search: SearchService = field(init=False)
    health: HealthService = field(init=False)
    reviews: ReviewService = field(init=False)
    identity: WorkspaceGroups = field(default_factory=WorkspaceGroups)
    _agent: Agent | None = field(default=None, init=False)
    _proposals: ProposalService | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._wire()

    def _wire(self) -> None:
        self.repo = RepositoryService(self.backend, self.registry)
        self.graph = GraphService(self.backend, self.registry)
        self.branches = BranchService(self.backend, self.registry)
        self.target = TargetStateService(self.backend, self.registry)
        self.search = SearchService(self.backend, self.registry)
        self.health = HealthService(self.backend, self.registry)
        self.reviews = ReviewService(self.backend, self.registry, self.branches)

    @property
    def agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(ToolBox(self.backend, self.registry, self.repo, self.graph), self.settings)
        return self._agent

    @property
    def proposals(self) -> ProposalService:
        if self._proposals is None:
            self._proposals = ProposalService(
                self.backend,
                self.registry,
                self.repo,
                self.branches,
                self.target,
                self.settings,
                ToolBox(self.backend, self.registry, self.repo, self.graph),
            )
        return self._proposals

    def reload_registry(self) -> Registry:
        """After the metamodel changed: re-read the stored pack and rebuild everything that depends on it."""
        pack = self.backend.load_pack(self.registry.pack.id) or self.registry.pack
        self.registry = Registry(pack)
        self._wire()
        self._agent = None
        self._proposals = None
        return self.registry

    # ------------------------------------------------------------ branch
    def branch(self) -> str:
        """The branch this request reads and writes (set from the session before the request)."""
        return current_branch()

    def on_branch(self) -> bool:
        return current_branch() != MAIN

    def frozen_reason(self) -> str:
        """Why a write here would be refused before anything is typed, or empty.

        `RepositoryService.check_write` refuses a branch that is in review one layer down.
        A page that offers Save anyway makes the reader type the change first and read the
        refusal afterwards; the reason belongs beside the control, before the typing.
        """
        if not self.on_branch():
            return ""
        b = self.backend.get_branch(current_branch())
        if b is not None and b.status in ("in_review", "approved"):
            return (
                f"Branch {b.branch_id} is {b.status.replace('_', ' ')}: frozen until the review "
                "is decided, so nothing on it can be changed."
            )
        return ""

    def branch_options(self) -> list[dict[str, str]]:
        """`main` and the open branches, for the header selector."""
        opts = [{"value": MAIN, "label": "main"}]
        for b in self.branches.list():
            if b.status in ("open", "in_review", "approved"):
                suffix = f" · {b.status.replace('_', ' ')}" if b.status != "open" else ""
                opts.append({"value": b.branch_id, "label": f"{b.name} ({b.changes}){suffix}"})
        return opts

    def work_package_options(self) -> list[dict[str, str]]:
        return [
            {"value": w.element_id, "label": f"{w.name} [{w.element_id}]"}
            for w in self.target.work_packages()
        ]

    # -------------------------------------------------------------- role
    def role(self) -> str:
        return current_role()

    def can(self, action: str) -> bool:
        return allowed(action)

    def role_label(self) -> str:
        return LABELS.get(current_role(), current_role())

    def debug_personas(self) -> bool:
        """Whether the header offers the persona switcher: mock authentication only, never on the platform."""
        return self.settings.auth != "databricks"

    def base_url(self) -> str:
        """The URL the app is reached at, for links inside exported files; empty when unknown."""
        try:
            from flask import has_request_context, request

            if has_request_context():
                return request.url_root.rstrip("/")
        except Exception:  # noqa: BLE001 — links are a courtesy, never a failure
            pass
        return ""

    def current_user(self) -> User:
        """Who is asking: on the platform the forwarded identity and its workspace groups; locally the debug persona."""
        if self.settings.auth == "databricks":
            try:
                from flask import has_request_context, request

                if has_request_context():
                    return self.user_from_headers(request.headers)
            except Exception:  # noqa: BLE001
                log.exception("could not read the forwarded identity")
            return User(username="anonymous", display_name="Anonymous", role="reader")
        return persona_user(self.persona())

    def user_from_headers(self, headers: Any) -> User:
        """The user the platform forwarded, with the groups it holds them in and the role those grant.

        The platform forwards no groups, so they are looked up in the workspace (`identity`),
        with the user's own token when the app is granted one. A groups header is believed only
        where `EA_TRUST_GROUPS_HEADER` says a proxy of ours sets it, and nobody signed in is a Reader.
        """
        email, groups, token = forwarded_identity(headers, self.settings.trust_groups_header)
        if not email:
            return User(username="anonymous", display_name="Anonymous", role="reader")
        if groups is None:
            groups = self.identity.groups(email, token)
        role = role_from_groups(groups, parse_role_groups(self.settings.role_groups))
        return User(username=email, display_name=email.split("@")[0], groups=groups, role=role)

    def persona(self) -> str:
        """The debug persona kept in the session; Admin by default."""
        try:
            from flask import has_request_context, session

            if has_request_context():
                return session.get("persona") or "admin"
        except Exception:  # noqa: BLE001
            pass
        return "admin"

    @property
    def actor(self) -> str:
        return self.current_user().username


def get_context() -> AppContext:
    global _context
    with _lock:
        if _context is None:
            settings = Settings.from_env()
            backend = backend_from_settings(settings)
            packs = backend.list_packs()
            if packs:
                pack = backend.load_pack(packs[0]["pack_id"])
            else:
                pack = load_pack(settings.pack_path)
                backend.save_pack(pack)
                log.info("loaded pack %s from %s", pack.id, settings.pack_path)
            _context = AppContext(settings, backend, Registry(pack))
        return _context
