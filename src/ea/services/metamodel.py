"""The metamodel's lifecycle: versions of a pack, drafts, publishing, the diff between two
versions, and what an organisation's content would say under one (decision 0015).

A pack id names a framework; a version names one stored definition of it, whether it
succeeds the version before or is a variant tried beside it. A draft is edited in place;
a published version is frozen; a retired one is kept for the record. An organisation
applies exactly one version, and applying one is preceded by a compatibility check that
validates every element and relationship of the organisation's main against it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ea import capacity
from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, use_branch
from ea.backend.organisations import use_org
from ea.metamodel.diff import PackDiff, diff_packs
from ea.metamodel.registry import Registry
from ea.models import (
    PACK_ID_PREFIX,
    CompatibilityReport,
    ConflictError,
    Issue,
    NotFoundError,
    Pack,
    PackVersion,
    slugify,
    split_pack_ref,
    validate_version,
)
from ea.services.roles import require

#: How many characters of an identifier, past its prefix, a person has to give before the
#: service will act on it. Six of a Crockford base32 alphabet is thirty bits — unmistakable in
#: any store worth the name, and short enough to read off a screen and type back.
MIN_ID_PREFIX = 6

#: The most issues one compatibility report keeps. Past it the report counts rather than
#: lists: a reader deciding whether to apply a version needs the shape of the damage, and
#: `by_code()` still totals every issue found (decision 0019).
MAX_ISSUES = 2_000


class MetamodelService:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    # -------------------------------------------------------------- reads
    def versions(self, pack_id: str | None = None) -> list[PackVersion]:
        return self.backend.list_pack_versions(pack_id)

    def version(self, ref: str) -> PackVersion:
        pack_id, version = self.resolve(ref)
        for v in self.backend.list_pack_versions(pack_id):
            if v.version == version:
                return v
        raise NotFoundError(ref, "metamodel version")

    def resolve_pack(self, text: str) -> str:
        """The pack a person means, from an identifier or from a name.

        An identifier is opaque now (decision 0021), so nobody types one in full: the rule is
        one look at the first characters. A token beginning `mm_` is an identifier — exact, or
        a prefix long enough to be unmistakable, the way a commit is named by its first few
        characters. Anything else is a name, matched through `slugify` so that
        `Higher Education EA Metamodel`, `higher education ea metamodel` and
        `higher_education_ea_metamodel` all reach the same pack.

        Two packs matching is a refusal that lists them, never a silent pick: choosing one for
        somebody who was ambiguous is how the wrong metamodel gets applied to an organisation.
        """
        token = (text or "").strip()
        if not token:
            raise NotFoundError("(empty)", "metamodel")
        held = self.backend.list_pack_versions()
        if token.startswith(PACK_ID_PREFIX):
            if len(token) < len(PACK_ID_PREFIX) + MIN_ID_PREFIX:
                raise NotFoundError(
                    token, f"metamodel (an identifier needs {MIN_ID_PREFIX} characters after the prefix)"
                )
            matches = {v.pack_id for v in held if v.pack_id.startswith(token)}
        else:
            wanted = slugify(token) if any(c.isalnum() for c in token) else token
            matches = {v.pack_id for v in held if v.name and slugify(v.name) == wanted}
        if not matches:
            raise NotFoundError(token, "metamodel")
        if len(matches) > 1:
            named = sorted({f"{v.name or v.pack_id} ({v.short_id})" for v in held if v.pack_id in matches})
            raise ConflictError(f"{token!r} names more than one metamodel: " + ", ".join(named))
        return matches.pop()

    def resolve(self, ref: str) -> tuple[str, str]:
        """A reference to the canonical `(pack id, version)` pair; refused when unknown.

        The pack half is whatever `resolve_pack` accepts; the version half, when it is left
        off, is the most recently loaded version of that pack.
        """
        token, version = split_pack_ref(ref)
        if not token:
            raise NotFoundError(ref or "(empty)", "metamodel version")
        try:
            pack_id = self.resolve_pack(token)
        except NotFoundError:
            raise NotFoundError(ref, "metamodel version") from None
        held = self.backend.list_pack_versions(pack_id)
        if not held:
            raise NotFoundError(ref, "metamodel version")
        if not version:
            return pack_id, held[0].version
        if not any(v.version == version for v in held):
            raise NotFoundError(ref, "metamodel version")
        return pack_id, version

    def get(self, ref: str) -> Pack:
        pack_id, version = self.resolve(ref)
        pack = self.backend.load_pack(pack_id, version)
        if pack is None:
            raise NotFoundError(ref, "metamodel version")
        return pack

    def diff(self, ref_a: str, ref_b: str) -> PackDiff:
        return diff_packs(self.get(ref_a), self.get(ref_b))

    def suggest_version(self, pack_id: str) -> str:
        """A version name nobody holds yet: today's date, numbered when the day already has one."""
        taken = {v.version for v in self.backend.list_pack_versions(pack_id)}
        today = datetime.now(UTC).date().isoformat()
        if today not in taken:
            return today
        n = 1
        while f"{today}-{n}" in taken:
            n += 1
        return f"{today}-{n}"

    # ------------------------------------------------------------- writes
    def save(self, pack: Pack, actor: str) -> Pack:
        """Store a version: a new one, or a draft replaced in place; a published one is refused by the store."""
        require("edit_metamodel", what="change the metamodel")
        Registry(pack)  # references and cycles, before anything is stored
        self.backend.save_pack(pack, actor)
        return pack

    def draft(self, from_ref: str, actor: str, version: str | None = None, notes: str = "") -> Pack:
        """A new draft copied from a stored version, to be edited and tried before it is published."""
        require("edit_metamodel", what="start a draft of the metamodel")
        source = self.get(from_ref)
        new_version = validate_version(version or self.suggest_version(source.id), "version")
        if any(v.version == new_version for v in self.backend.list_pack_versions(source.id)):
            raise ConflictError(f"version {new_version} of pack {source.id} already exists")
        draft = self.backend.load_pack(source.id, source.version)  # a fresh copy, not the caller's object
        assert draft is not None
        draft.version = new_version
        draft.status = "draft"
        draft.derived_from = source.ref
        draft.notes = notes or draft.notes
        self.backend.save_pack(draft, actor)
        return draft

    def rename(self, ref: str, name: str, actor: str) -> PackVersion:
        """Correct what a version is called, whatever its status (decision 0022).

        A freeze is on what a version *defines*, and a name defines nothing: nothing keys off
        it, because the identifier does that and it is opaque (decision 0021). So a published
        version — or a retired one, kept to be read by whoever applied it — is renamed where it
        is wrong, rather than by copying a whole definition into a new version to carry the
        correction. The rename is recorded in the change log with the name it had.
        """
        require("edit_metamodel", what="rename a metamodel version")
        wanted = (name or "").strip()
        if not wanted:
            raise ValueError("a metamodel needs a name — it is what a reader sees")
        pack = self.get(ref)
        if pack.name != wanted:
            pack.name = wanted
            # Through `save_pack`, not around it: on a draft this rewrites the row like any
            # other edit, and on a frozen version it takes the one path that writes a name.
            self.backend.save_pack(pack, actor)
        return self.version(f"{pack.id}@{pack.version}")

    def publish(self, ref: str, actor: str) -> PackVersion:
        """Freeze a draft: from now on its content cannot change, only be copied into a new draft."""
        require("publish_metamodel", what="publish a metamodel version")
        pack = self.get(ref)
        if pack.status == "published":
            return self.version(ref)
        if pack.status == "retired":
            raise ConflictError(f"{pack.ref} is retired; start a draft from it instead")
        Registry(pack)
        return self.backend.set_pack_status(pack.id, pack.version, "published", actor)

    def retire(self, ref: str, actor: str) -> PackVersion:
        """Take a version out of use. One an organisation still applies stays."""
        require("publish_metamodel", what="retire a metamodel version")
        v = self.version(ref)
        if v.applied_by:
            raise ConflictError(
                f"{v.ref} is applied by {', '.join(v.applied_by)}; apply another version there first"
            )
        return self.backend.set_pack_status(v.pack_id, v.version, "retired", actor)

    def delete(self, ref: str, actor: str) -> None:
        """Remove a draft nobody applies. A published version is never deleted: it is retired."""
        require("edit_metamodel", what="delete a metamodel draft")
        v = self.version(ref)
        if v.status == "published":
            raise ConflictError(f"{v.ref} is published; a published version is retired, not deleted")
        if v.applied_by:
            raise ConflictError(
                f"{v.ref} is applied by {', '.join(v.applied_by)}; apply another version there first"
            )
        self.backend.delete_pack_version(v.pack_id, v.version, actor)

    # ------------------------------------------------------ compatibility
    def compatibility(self, org_id: str, pack: Pack) -> CompatibilityReport:
        """Every element and relationship on the organisation's main, validated against the pack.

        The report says what applying the version would leave invalid — a type the version
        dropped or made inactive, a required attribute nobody filled, a relationship whose
        ends the version no longer allows — before anything is applied.
        """
        registry = Registry(pack)
        report = CompatibilityReport(
            org_id=org_id, pack_id=pack.id, pack_name=pack.name, version=pack.version
        )

        def keep(issue: Issue) -> None:
            # what a pack does not declare is kept, as the importer keeps it
            if issue.code == "extra_attribute":
                return
            report.counts[issue.code] = report.counts.get(issue.code, 0) + 1
            if issue.level == "error":
                report.error_count += 1
            if len(report.issues) < MAX_ISSUES:
                report.issues.append(issue)
            else:
                report.truncated = True

        # Paged rather than read whole: the check runs over an organisation's entire main, and
        # the application is assessed for a hundred thousand elements (decision 0019). Only the
        # type of each element is carried forward, because that is all the relationship pass
        # needs — not the elements themselves.
        with use_org(org_id), use_branch(MAIN):
            types: dict[str, str] = {}
            offset = 0
            while True:
                page = self.backend.find_elements(limit=capacity.READ_CHUNK, offset=offset)
                if not page:
                    break
                for e in page:
                    report.elements += 1
                    types[e.element_id] = e.type_id
                    for issue in registry.validate_element(e.type_id, e.attrs, entity=e.element_id):
                        keep(issue)
                offset += len(page)
                if len(page) < capacity.READ_CHUNK:
                    break
            offset = 0
            while True:
                page = self.backend.find_relationships(limit=capacity.READ_CHUNK, offset=offset)
                if not page:
                    break
                for r in page:
                    report.relationships += 1
                    src, dst = types.get(r.src_id), types.get(r.dst_id)
                    if src is None or dst is None:
                        continue  # a dangling edge is the content's problem, not the version's
                    for issue in registry.validate_relationship(
                        r.rel_type_id, src, dst, r.qualifier, entity=r.relationship_id, attrs=r.attrs
                    ):
                        keep(issue)
                offset += len(page)
                if len(page) < capacity.READ_CHUNK:
                    break
        return report
