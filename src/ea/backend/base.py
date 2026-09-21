"""The repository contract. The only place SQL is allowed is a backend implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from ea.models import (
    Branch,
    ChangeSet,
    Element,
    Link,
    MergeResult,
    Organisation,
    Pack,
    PackVersion,
    Proposal,
    Relationship,
    Review,
    SourceFeed,
)


class DatabaseBackend(ABC):
    """Everything the services and the UI need from storage.

    Writes take an `actor` for the audit trail. Updates carry the version the
    caller read; a mismatch raises ConflictError and never overwrites.
    """

    # ------------------------------------------------------------ lifecycle
    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    # ------------------------------------------------------------ metamodel
    # A pack is stored in versions (decision 0015): a draft is replaced in place, a published
    # version is frozen, and an organisation applies exactly one.
    @abstractmethod
    def save_pack(self, pack: Pack, actor: str = "") -> None:
        """Store this version of the pack: a new one, or a draft replaced in place.

        Storing a published version again with the same content changes nothing; with
        different content it raises ConflictError, because what was validated against a
        published version must stay validated."""

    @abstractmethod
    def load_pack(self, pack_id: str, version: str | None = None) -> Pack | None:
        """One stored version, or the most recently loaded version of the pack when none is named."""

    @abstractmethod
    def list_pack_versions(self, pack_id: str | None = None) -> list[PackVersion]:
        """Every stored version, newest first, each naming the organisations that apply it."""

    @abstractmethod
    def set_pack_status(self, pack_id: str, version: str, status: str, actor: str) -> PackVersion: ...

    @abstractmethod
    def delete_pack_version(self, pack_id: str, version: str, actor: str) -> None: ...

    # -------------------------------------------------------- organisations
    # Every read and write above honours the current organisation (ea.backend.organisations);
    # these manage the organisations themselves (decision 0014).
    @abstractmethod
    def list_organisations(self) -> list[Organisation]: ...

    @abstractmethod
    def get_organisation(self, org_id: str) -> Organisation | None: ...

    @abstractmethod
    def default_organisation(self) -> Organisation | None: ...

    @abstractmethod
    def save_organisation(self, org: Organisation, actor: str) -> Organisation:
        """Insert the organisation, or replace its row (name, description, applied version, default flag)."""

    @abstractmethod
    def delete_organisation(self, org_id: str, actor: str) -> None:
        """Remove the organisation and every row that belongs to it."""

    @abstractmethod
    def copy_organisation_content(self, src_org: str, dst_org: str, actor: str) -> dict[str, int]:
        """Copy the main content of one organisation (elements, relationships, links, reviewer
        assignments) into another, which must be empty. Branches, proposals and reviews are not copied."""

    # ------------------------------------------------------------- elements
    @abstractmethod
    def get_element(self, element_id: str) -> Element | None: ...

    @abstractmethod
    def find_elements(
        self,
        text: str | None = None,
        type_id: str | list[str] | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Element]: ...

    @abstractmethod
    def count_elements(
        self, type_id: str | None = None, text: str | None = None, status: str | None = None
    ) -> int: ...

    @abstractmethod
    def linked_element_ids(self) -> list[str]:
        """Ids of the elements that carry at least one link."""

    @abstractmethod
    def count_by_type(self) -> dict[str, int]: ...

    @abstractmethod
    def insert_element(self, element: Element, actor: str) -> Element: ...

    @abstractmethod
    def update_element(
        self, element: Element, actor: str, expected_version: int | None = None
    ) -> Element: ...

    @abstractmethod
    def upsert_elements(self, elements: list[Element], actor: str) -> tuple[int, int, int]:
        """Bulk load by element_id. Returns (inserted, updated, unchanged).

        A row identical to what the branch already holds is left alone and counted as
        unchanged, not as updated — a nightly refresh that re-sends the whole source would
        otherwise report every row as written every night."""

    @abstractmethod
    def set_links(self, element_id: str, links: list[Link], actor: str) -> list[Link]: ...

    @abstractmethod
    def get_links(self, element_id: str) -> list[Link]: ...

    # -------------------------------------------------------- relationships
    @abstractmethod
    def get_relationship(self, relationship_id: str) -> Relationship | None: ...

    @abstractmethod
    def relationships_of(self, element_id: str, direction: str = "both") -> list[Relationship]: ...

    @abstractmethod
    def find_relationships(
        self, rel_type_id: str | None = None, limit: int = 500, offset: int = 0
    ) -> list[Relationship]: ...

    @abstractmethod
    def count_relationships(self, rel_type_id: str | None = None) -> int: ...

    @abstractmethod
    def count_by_rel_type(self) -> dict[str, int]: ...

    @abstractmethod
    def insert_relationship(self, rel: Relationship, actor: str) -> Relationship: ...

    @abstractmethod
    def update_relationship(
        self, rel: Relationship, actor: str, expected_version: int | None = None
    ) -> Relationship: ...

    @abstractmethod
    def delete_relationship(self, relationship_id: str, actor: str) -> None: ...

    @abstractmethod
    def upsert_relationships(self, rels: list[Relationship], actor: str) -> tuple[int, int, int]:
        """Bulk load by relationship_id. Returns (inserted, updated, unchanged)."""

    # ---------------------------------------------------------------- graph
    @abstractmethod
    def trace(self, element_id: str, direction: str = "out", max_depth: int = 5) -> list[dict[str, Any]]:
        """Reachable elements with depth, node path and relationship-type path."""

    @abstractmethod
    def elements_by_ids(self, ids: list[str]) -> list[Element]:
        """The elements these identifiers name, in one read per chunk (decision 0019)."""

    @abstractmethod
    def elements_by_keys(self, keys: list[str]) -> list[Element]:
        """The elements carrying these human keys, in one read per chunk.

        A key is what a source system calls the thing (`DT007`), and it is not the store's
        identity — nothing constrains it to be unique, so a caller that merges on it decides
        what to do when one key names two elements."""

    @abstractmethod
    def edges_among(self, ids: list[str]) -> list[Relationship]:
        """Every live relationship with both ends inside this set of elements."""

    @abstractmethod
    def edges_frame(self) -> pd.DataFrame:
        """All non-retired relationships as (src_id, dst_id, rel_type_id, qualifier, relationship_id)."""

    # ---------------------------------------------------------------- audit
    @abstractmethod
    def history(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]: ...

    # ------------------------------------------------------------- branches
    # Overlays on the same schema, see decision 0006. Every read and write above honours
    # the current branch (ea.backend.branching); these manage the branches themselves.
    @abstractmethod
    def create_branch(self, branch: Branch, actor: str) -> Branch: ...

    @abstractmethod
    def get_branch(self, branch_id: str) -> Branch | None: ...

    @abstractmethod
    def list_branches(self, status: str | None = None) -> list[Branch]: ...

    @abstractmethod
    def diff_branch(self, branch_id: str) -> ChangeSet: ...

    @abstractmethod
    def merge_branch(
        self,
        branch_id: str,
        actor: str,
        include: set[str] | None = None,
        resolutions: dict[str, str] | None = None,
    ) -> MergeResult: ...

    @abstractmethod
    def abandon_branch(self, branch_id: str, actor: str) -> Branch: ...

    @abstractmethod
    def set_branch_status(self, branch_id: str, status: str, actor: str) -> Branch: ...

    # -------------------------------------------------------------- reviews
    @abstractmethod
    def add_review(self, review: Review) -> Review: ...

    @abstractmethod
    def list_reviews(self, branch_id: str) -> list[Review]: ...

    @abstractmethod
    def list_reviewer_assignments(self) -> dict[str, list[str]]: ...

    @abstractmethod
    def set_reviewer_assignment(self, type_id: str, reviewers: list[str], actor: str) -> None: ...

    # ------------------------------------------------------------ proposals
    # What an architect handed in and where it went (initiative 5).
    @abstractmethod
    def save_proposal(self, p: Proposal) -> Proposal: ...

    @abstractmethod
    def list_proposals(self, branch_id: str | None = None) -> list[Proposal]: ...

    # ---------------------------------------------------------------- feeds
    @abstractmethod
    def save_feed(self, feed: SourceFeed, actor: str) -> SourceFeed:
        """Store a feed's configuration, by feed_id, in the current organisation."""

    @abstractmethod
    def list_feeds(self) -> list[SourceFeed]: ...

    @abstractmethod
    def get_feed(self, feed_id: str) -> SourceFeed | None: ...

    @abstractmethod
    def delete_feed(self, feed_id: str, actor: str) -> None: ...

    # -------------------------------------------------------------- staging
    @abstractmethod
    def staging_tables(self) -> list[str]:
        """The tables waiting in the staging schema, which the store creates and never fills.

        What puts rows there is outside the application — a platform job writing Postgres, or a
        catalogue table replicated into it. The contract with a source is the shape of the
        table and nothing else (decision 0020)."""

    @abstractmethod
    def read_staging(self, table: str, limit: int, offset: int) -> pd.DataFrame:
        """One page of a staging table, in the order the source wrote it."""

    @abstractmethod
    def clear_staging(self, table: str) -> int:
        """Empty a staging table once its rows are loaded. Returns how many rows went."""

    # ------------------------------------------------------------------ sql
    @abstractmethod
    def query(
        self, sql: str, params: list[Any] | None = None, limit: int = 1000, scoped: bool = True
    ) -> pd.DataFrame:
        """Read-only SQL for power users and the agent. Anything but a SELECT is refused.

        Scoped, the content tables read as the current organisation's main and the metamodel
        tables as the version it applies, so `select count(*) from element` answers for the
        organisation the reader is in; unscoped, the tables are read as they are."""
