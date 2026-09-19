"""Organisations: the enterprises whose architecture the store holds, one of them the default,
each applying one version of the metamodel (decision 0014).

The default organisation is what the application opens. Another one is where a version of
the metamodel is tried: created from a copy of the default's content, given the version to
try, worked on as any organisation is, and deleted when the trial is over. Applying a
version anywhere goes through the compatibility check of `MetamodelService`.
"""

from __future__ import annotations

from ea.backend.base import DatabaseBackend
from ea.backend.organisations import DEFAULT_ORG, current_org, org_id_from_name, validate_org_id
from ea.models import CompatibilityReport, ConflictError, NotFoundError, Organisation, Pack
from ea.services.metamodel import MetamodelService
from ea.services.roles import require


class OrganisationService:
    def __init__(self, backend: DatabaseBackend, metamodels: MetamodelService | None = None):
        self.backend = backend
        self.metamodels = metamodels or MetamodelService(backend)

    # -------------------------------------------------------------- reads
    def list(self) -> list[Organisation]:
        return self.backend.list_organisations()

    def current(self) -> Organisation:
        return self.get(current_org())

    def default(self) -> Organisation | None:
        return self.backend.default_organisation()

    def ensure_default(self, pack: Pack, actor: str = "system") -> Organisation:
        """The default organisation, created applying the pack when the store holds none yet."""
        org = self.backend.default_organisation()
        if org is not None:
            return org
        if not self.backend.list_pack_versions(pack.id) or not any(
            v.version == pack.version for v in self.backend.list_pack_versions(pack.id)
        ):
            self.backend.save_pack(pack, actor)
        existing = self.backend.get_organisation(DEFAULT_ORG)
        org = existing or Organisation(org_id=DEFAULT_ORG, name="Default organisation")
        org.pack_id, org.pack_version, org.is_default = pack.id, pack.version, True
        return self.backend.save_organisation(org, actor)

    def applied_pack(self, org_id: str | None = None) -> Pack:
        """The version the organisation applies, loaded."""
        org = self.get(org_id or current_org())
        pack = self.backend.load_pack(org.pack_id, org.pack_version) if org.pack_id else None
        if pack is None:
            raise NotFoundError(org.pack_ref or "(none)", "metamodel version")
        return pack

    # ------------------------------------------------------------- writes
    def create(
        self,
        name: str,
        actor: str,
        description: str = "",
        pack_ref: str = "",
        copy_from: str | None = None,
        org_id: str | None = None,
        make_default: bool = False,
    ) -> Organisation:
        """A new organisation applying a version: the one named, else the one the copied or the
        default organisation applies. With `copy_from`, its main content is copied over."""
        require("manage_organisations", what="create an organisation")
        oid = validate_org_id(org_id) if org_id else org_id_from_name(name)
        if self.backend.get_organisation(oid) is not None:
            raise ConflictError(f"organisation {oid} already exists")
        source = self.get(copy_from) if copy_from else None
        if pack_ref:
            pack_id, version = self.metamodels.resolve(pack_ref)
        elif source is not None and source.pack_id:
            pack_id, version = source.pack_id, source.pack_version
        else:
            default = self.backend.default_organisation()
            if default is None or not default.pack_id:
                raise ConflictError("name the metamodel version the organisation applies (pack@version)")
            pack_id, version = default.pack_id, default.pack_version
        org = Organisation(
            org_id=oid,
            name=name.strip() or oid,
            description=description,
            pack_id=pack_id,
            pack_version=version,
            is_default=make_default or self.backend.default_organisation() is None,
            copied_from=source.org_id if source else "",
        )
        org = self.backend.save_organisation(org, actor)
        if source is not None:
            self.backend.copy_organisation_content(source.org_id, org.org_id, actor)
        return self.get(org.org_id)

    def get(self, org_id: str) -> Organisation:
        """The organisation, with what it holds counted."""
        org = next((o for o in self.backend.list_organisations() if o.org_id == org_id), None)
        if org is None:
            raise NotFoundError(org_id, "organisation")
        return org

    def update(
        self, org_id: str, actor: str, name: str | None = None, description: str | None = None
    ) -> Organisation:
        require("manage_organisations", what="rename an organisation")
        org = self.get(org_id)
        if name is not None and name.strip():
            org.name = name.strip()
        if description is not None:
            org.description = description
        return self.backend.save_organisation(org, actor)

    def set_default(self, org_id: str, actor: str) -> Organisation:
        require("manage_organisations", what="name the default organisation")
        org = self.get(org_id)
        org.is_default = True
        return self.backend.save_organisation(org, actor)

    def delete(self, org_id: str, actor: str) -> None:
        """Remove an organisation and everything in it. The default one stays."""
        require("manage_organisations", what="delete an organisation")
        org = self.get(org_id)
        if org.is_default:
            raise ConflictError(f"{org.org_id} is the default organisation; name another default first")
        self.backend.delete_organisation(org.org_id, actor)

    # ------------------------------------------------------ the metamodel
    def check(self, org_id: str, pack_ref: str) -> CompatibilityReport:
        """What the organisation's content would say under the version, without applying it."""
        org = self.get(org_id)
        return self.metamodels.compatibility(org.org_id, self.metamodels.get(pack_ref))

    def apply(self, org_id: str, pack_ref: str, actor: str, force: bool = False) -> CompatibilityReport:
        """Make the organisation apply the version. Refused on errors in the compatibility report
        unless forced; the report is returned either way, and the change is logged."""
        require("apply_metamodel", what="apply a metamodel version")
        org = self.get(org_id)
        pack = self.metamodels.get(pack_ref)
        if pack.status == "retired":
            raise ConflictError(f"{pack.ref} is retired")
        report = self.metamodels.compatibility(org.org_id, pack)
        if report.errors and not force:
            raise ConflictError(
                f"{pack.ref} leaves {len(report.errors)} error(s) on {org.org_id}: {report.summary()}; "
                "fix the content or the version, or apply with force"
            )
        org.pack_id, org.pack_version = pack.id, pack.version
        self.backend.save_organisation(org, actor)
        return report
