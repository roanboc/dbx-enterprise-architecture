"""One application context: settings, store, the services per organisation, agent, current user and role.

The organisation a request is in decides which metamodel version is read and which
content the services see (decision 0014), so the registry and the services are held
in one bundle per organisation, built from the version the organisation applies and
rebuilt when the metamodel changes.
"""

from __future__ import annotations

import logging
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from ea.agent import Agent
from ea.agent.proposal import ProposalService
from ea.agent.tools import ToolBox
from ea.backend import DatabaseBackend, backend_from_settings
from ea.backend.branching import MAIN, current_branch
from ea.backend.organisations import current_org
from ea.config import Settings
from ea.metamodel import Registry, load_pack
from ea.models import Organisation, User
from ea.services import (
    BranchService,
    ChangeImpactService,
    DeepDiveService,
    GraphService,
    HealthService,
    MetamodelService,
    OrganisationService,
    RepositoryService,
    ReviewService,
    SearchService,
    TargetStateService,
    TemplateService,
)
from ea.services.branches import refusal_for_writing
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


#: The Ask conversations one organisation keeps at once; past it the least recently used is
#: let go, and its reader's next question starts a new one.
CONVERSATIONS_KEPT = 200


def persona_user(persona: str) -> User:
    return PERSONAS.get(persona, PERSONAS["admin"])


@dataclass
class Bundle:
    """The registry and the services of one organisation, on the version it applies."""

    registry: Registry
    repo: RepositoryService
    graph: GraphService
    branches: BranchService
    target: TargetStateService
    search: SearchService
    health: HealthService
    reviews: ReviewService
    templates: TemplateService
    impact: ChangeImpactService
    deep_dives: DeepDiveService
    # One Ask agent per conversation, never one per organisation: what a follow-up needs
    # (the messages so far, the identifiers the tools returned) is one reader's own.
    agents: OrderedDict[str, Agent] = field(default_factory=OrderedDict)
    proposals: ProposalService | None = None

    @classmethod
    def build(cls, backend: DatabaseBackend, registry: Registry) -> Bundle:
        branches = BranchService(backend, registry)
        return cls(
            registry=registry,
            repo=RepositoryService(backend, registry),
            graph=GraphService(backend, registry),
            branches=branches,
            target=TargetStateService(backend, registry),
            search=SearchService(backend, registry),
            health=HealthService(backend, registry),
            reviews=ReviewService(backend, registry, branches),
            templates=TemplateService(backend, registry),
            impact=ChangeImpactService(backend, registry),
            deep_dives=DeepDiveService(backend, registry),
        )


@dataclass
class AppContext:
    settings: Settings
    backend: DatabaseBackend
    identity: WorkspaceGroups = field(default_factory=WorkspaceGroups)
    metamodels: MetamodelService = field(init=False)
    orgs: OrganisationService = field(init=False)
    _bundles: dict[str, Bundle] = field(default_factory=dict, init=False)
    _bundle_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _agent_provider: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.metamodels = MetamodelService(self.backend)
        self.orgs = OrganisationService(self.backend, self.metamodels)

    # ------------------------------------------------------------ bundle
    def _bundle(self) -> Bundle:
        """The services of the organisation this request is in, built on first use."""
        org = current_org()
        with self._bundle_lock:
            b = self._bundles.get(org)
            if b is None:
                b = Bundle.build(self.backend, Registry(self.orgs.applied_pack(org)))
                self._bundles[org] = b
            return b

    @property
    def registry(self) -> Registry:
        return self._bundle().registry

    @property
    def repo(self) -> RepositoryService:
        return self._bundle().repo

    @property
    def graph(self) -> GraphService:
        return self._bundle().graph

    @property
    def branches(self) -> BranchService:
        return self._bundle().branches

    @property
    def target(self) -> TargetStateService:
        return self._bundle().target

    @property
    def search(self) -> SearchService:
        return self._bundle().search

    @property
    def health(self) -> HealthService:
        return self._bundle().health

    @property
    def reviews(self) -> ReviewService:
        return self._bundle().reviews

    @property
    def agent(self) -> Agent:
        """The Ask agent of the conversation this request belongs to.

        Held per organisation, because its tools read that organisation's metamodel, and per
        conversation inside it — the signed-in reader and their session — so one reader's
        question is never answered in the context of another's, and a Reset clears one
        conversation. The least recently used is let go past `CONVERSATIONS_KEPT`.
        """
        b = self._bundle()
        key = self._conversation()
        with self._bundle_lock:
            agent = b.agents.get(key)
            if agent is None:
                if self._agent_provider is None:
                    self._agent_provider = Agent.make_provider(self.settings)
                toolbox = ToolBox(self.backend, b.registry, b.repo, b.graph)
                agent = b.agents[key] = Agent(toolbox, self.settings, self._agent_provider)
                while len(b.agents) > CONVERSATIONS_KEPT:
                    b.agents.popitem(last=False)
            else:
                b.agents.move_to_end(key)
            return agent

    def _conversation(self) -> str:
        """The reader and their session, named once in the signed session cookie; one outside a request."""
        try:
            from flask import has_request_context, session

            if has_request_context():
                if not session.get("conversation"):
                    session["conversation"] = secrets.token_hex(8)
                return f"{self.current_user().username}:{session['conversation']}"
        except RuntimeError:  # a session without a secret key cannot be written: one conversation
            log.warning("no session to hold an Ask conversation in; using the shared one")
        return "local"

    @property
    def templates(self) -> TemplateService:
        return self._bundle().templates

    @property
    def impact(self) -> ChangeImpactService:
        return self._bundle().impact

    @property
    def deep_dives(self) -> DeepDiveService:
        return self._bundle().deep_dives

    @property
    def proposals(self) -> ProposalService:
        b = self._bundle()
        if b.proposals is None:
            b.proposals = ProposalService(
                self.backend,
                b.registry,
                b.repo,
                b.branches,
                b.target,
                self.settings,
                ToolBox(self.backend, b.registry, b.repo, b.graph),
                b.templates,
                b.impact,
            )
        return b.proposals

    def reload_registry(self) -> Registry:
        """After the metamodel or an organisation changed: every bundle is rebuilt on its next use."""
        with self._bundle_lock:
            self._bundles.clear()
        return self.registry

    # ------------------------------------------------------ organisation
    def org(self) -> str:
        """The organisation this request reads and writes (set from the session before the request)."""
        return current_org()

    def organisation(self) -> Organisation:
        return self.orgs.get(current_org())

    def org_options(self) -> list[dict[str, str]]:
        """Every organisation, the default first, for the header selector."""
        return [{"value": o.org_id, "label": o.name} for o in self.orgs.list()]

    def pack_label(self) -> str:
        """What the header says of the metamodel: the version and, unless published, its state.

        The pack is named only where the store holds more than one, as the version selector
        does: repeating one pack's name in the header costs the width the organisation's own
        name needs, and says nothing the page does not.
        """
        p = self.registry.pack
        several = len({v.pack_id for v in self.metamodels.versions()}) > 1
        # The NAME where there is a choice, never the identifier: it is opaque now
        # (decision 0021), so in the header it would be a string nobody can act on in the
        # width the organisation's own name needs.
        return (
            (f"{p.name} · " if several else "")
            + p.version
            + ("" if p.status == "published" else f" · {p.status}")
        )

    # ------------------------------------------------------------ branch
    def branch(self) -> str:
        """The branch this request reads and writes (set from the session before the request)."""
        return current_branch()

    def on_branch(self) -> bool:
        return current_branch() != MAIN

    def frozen_reason(self) -> str:
        """Why a write here would be refused before anything is typed, or empty.

        `RepositoryService.check_write` refuses the same branches one layer down, through
        the same function. A page that offers Save anyway makes the reader type the change
        first and read the refusal afterwards; the reason belongs beside the control,
        before the typing.
        """
        reason = refusal_for_writing(self.backend)
        return f"{reason[0].upper()}{reason[1:]}." if reason else ""

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


def open_context(settings: Settings | None = None) -> AppContext:
    """The store opened and the default organisation in place, applying the pack the settings name
    when the store holds none yet. What the app and the command line both do first."""
    settings = settings or Settings.from_env()
    backend = backend_from_settings(settings)
    ctx = AppContext(settings, backend)
    if ctx.orgs.default() is None:
        pack = load_pack(settings.pack_path)
        ctx.orgs.ensure_default(pack)
        log.info("loaded pack %s from %s", pack.ref, settings.pack_path)
    return ctx


def get_context() -> AppContext:
    global _context
    with _lock:
        if _context is None:
            _context = open_context()
        return _context
