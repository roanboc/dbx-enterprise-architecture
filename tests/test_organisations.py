"""Organisations: a partition of one store, one of them the default, each applying one version.

Every read and write of the store honours the current organisation (decision 0014), so
two organisations may hold the same identifiers and never see each other's rows; a
sandbox is a copy of the default's main; applying a version is preceded by the
compatibility check; the roles guard the lot.
"""

from __future__ import annotations

import re

import duckdb
import pytest
from tests.conftest import HIGHER_ED, new_schema_name

from ea.backend.branching import use_branch
from ea.backend.duckdb_backend import DuckDBBackend
from ea.backend.lakebase_backend import LakebaseBackend
from ea.backend.organisations import DEFAULT_ORG, current_org, org_id_from_name, use_org
from ea.backend.sql import schema_of, schemas
from ea.backend.sql_backend import SqlBackend
from ea.metamodel import Registry
from ea.metamodel.loader import pack_to_dict
from ea.models import ConflictError, Element, Forbidden, NotFoundError, Relationship, RoleGrant
from ea.services import (
    BranchService,
    MetamodelService,
    OrganisationService,
    RepositoryService,
    ReviewService,
    use_role,
)

PUBLISHED = f"{HIGHER_ED}@2026-08-11"


@pytest.fixture
def orgs(loaded):
    return OrganisationService(loaded)


def test_ids_come_from_names():
    assert org_id_from_name("Trial: Lean information / 2026") == "trial-lean-information-2026"
    with pytest.raises(ValueError):
        org_id_from_name("!!!")


def test_the_default_organisation_applies_the_pack(loaded, pack, orgs):
    default = orgs.default()
    assert default is not None and default.org_id == DEFAULT_ORG and default.is_default
    assert default.pack_ref == pack.ref == PUBLISHED
    assert current_org() == DEFAULT_ORG
    assert [o.org_id for o in orgs.list()] == [DEFAULT_ORG]
    assert orgs.get(DEFAULT_ORG).elements == 47
    assert orgs.applied_pack().ref == PUBLISHED


def test_content_is_scoped_by_organisation(loaded, registry, orgs):
    trial = orgs.create("Trial", "ada", description="an empty one")
    assert trial.org_id == "trial" and not trial.is_default and trial.elements == 0
    repo = RepositoryService(loaded, registry)
    with use_org("trial"):
        assert loaded.count_elements() == 0 and loaded.count_relationships() == 0
        assert loaded.get_element("LDC-CURR") is None
        # the same identifier as the default organisation's, held apart from it
        loaded.insert_element(Element("LDC-CURR", "logical_data_component", "Curriculum, tried"), "ada")
        loaded.insert_element(Element("DE-X", "data_entity", "X"), "ada")
        loaded.insert_relationship(
            Relationship("r-x", "logical_data_component__encapsulates__data_entity", "LDC-CURR", "DE-X"),
            "ada",
        )
        assert loaded.get_element("LDC-CURR").name == "Curriculum, tried"
        assert loaded.count_elements() == 2 and len(loaded.relationships_of("LDC-CURR")) == 1
        assert {r["element_id"] for r in loaded.trace("LDC-CURR", "out", 3)} == {"DE-X"}
        assert [h["entity_id"] for h in loaded.history()][:1] == ["r-x"]
        assert loaded.linked_element_ids() == []
    # nothing moved in the default organisation
    assert loaded.get_element("LDC-CURR").name == "Curriculum"
    assert loaded.count_elements() == 47 and loaded.get_element("DE-X") is None
    assert loaded.get_relationship("r-x") is None
    assert all(h["entity_id"] != "r-x" for h in loaded.history(limit=1000))
    assert repo.stats()["elements"] == 47


def test_branches_reviews_and_reviewers_belong_to_their_organisation(loaded, registry, orgs):
    orgs.create("Trial", "ada")
    branches = BranchService(loaded, registry)
    reviews = ReviewService(loaded, registry, branches)
    branches.create("shared name", "ada")
    reviews.set_assignment("data_entity", ["ana"], "ada")
    with use_org("trial"):
        assert branches.list() == [] and reviews.assignments() == {}
        b = branches.create("shared name", "ada")  # the same id, in another organisation
        assert b.branch_id == "shared-name"
        with use_branch(b.branch_id):
            loaded.insert_element(Element("DE-T", "data_entity", "T"), "ada")
        assert branches.get(b.branch_id).changes == 1
        reviews.set_assignment("data_entity", ["trial-steward"], "ada")
        assert reviews.assignments() == {"data_entity": ["trial-steward"]}
    assert branches.get("shared-name").changes == 0
    assert reviews.assignments() == {"data_entity": ["ana"]}
    with use_branch("shared-name"):
        assert loaded.get_element("DE-T") is None


def test_a_sandbox_is_a_copy_of_the_main_content(loaded, registry, orgs):
    ReviewService(loaded, registry, BranchService(loaded, registry)).set_assignment(
        "data_entity", ["ana"], "ada"
    )
    sandbox = orgs.create("Sandbox", "ada", copy_from=DEFAULT_ORG)
    assert (sandbox.elements, sandbox.relationships, sandbox.copied_from) == (47, 99, DEFAULT_ORG)
    assert sandbox.pack_ref == PUBLISHED
    repo = RepositoryService(loaded, registry)
    with use_org("sandbox"):
        cms = loaded.get_element("PAC-CMS")
        assert [ln.url for ln in cms.links] == ["https://example.edu/cmdb/cms"]
        repo.update_element("PAC-CMS", "ada", cms.version, name="CMS, tried")
        assert loaded.list_reviewer_assignments() == {"data_entity": ["ana"]}
        assert loaded.count_elements() == 47
    assert loaded.get_element("PAC-CMS").name == "Curriculum Management System"
    # a copy needs an empty destination
    with pytest.raises(ConflictError):
        loaded.copy_organisation_content(DEFAULT_ORG, "sandbox", "ada")
    with pytest.raises(NotFoundError):
        loaded.copy_organisation_content(DEFAULT_ORG, "nowhere", "ada")


def test_the_default_moves_and_a_deleted_organisation_leaves_nothing(loaded, registry, orgs):
    sandbox = orgs.create("Sandbox", "ada", copy_from=DEFAULT_ORG)
    with pytest.raises(ConflictError):
        orgs.create("Sandbox", "ada")  # the id is taken
    with pytest.raises(ConflictError):
        orgs.delete(DEFAULT_ORG, "ada")  # the default stays
    orgs.set_default("sandbox", "ada")
    assert orgs.default().org_id == "sandbox" and not orgs.get(DEFAULT_ORG).is_default
    orgs.set_default(DEFAULT_ORG, "ada")
    with use_org("sandbox"), use_branch("main"):
        BranchService(loaded, registry).create("wp", "ada")
    orgs.delete(sandbox.org_id, "ada")
    with pytest.raises(NotFoundError):
        orgs.get("sandbox")
    with use_org("sandbox"):
        assert loaded.count_elements() == 0 and loaded.list_branches() == []
    assert loaded.count_elements() == 47
    renamed = orgs.update(DEFAULT_ORG, "ada", name="Sample University", description="the demo")
    assert (renamed.name, renamed.description) == ("Sample University", "the demo")


def test_applying_a_version_checks_the_content_first(loaded, registry, orgs):
    metamodels = MetamodelService(loaded)
    draft = metamodels.draft(PUBLISHED, "ada", version="lean")
    # the draft drops a type the content uses, and makes an attribute the content lacks required
    draft.element_types = [t for t in draft.element_types if t.id != "measure"]
    draft.relationship_types = [r for r in draft.relationship_types if "measure" not in (r.source, r.target)]
    entity = next(t for t in draft.element_types if t.id == "data_entity")
    entity.attributes.append(type(entity.attributes[0])(name="steward", required=True))
    metamodels.save(draft, "ada")
    report = orgs.check(DEFAULT_ORG, draft.ref)
    assert report.elements == 47 and report.relationships == 99
    codes = report.by_code()
    assert codes["unknown_type"] == 2  # the two measures
    assert codes["missing_attribute"] == 7  # every data entity lacks a steward
    assert codes["unknown_relationship_type"] >= 1  # the edges the measures carried
    assert not report.ok
    with pytest.raises(ConflictError, match="error"):
        orgs.apply(DEFAULT_ORG, draft.ref, "ada")
    assert orgs.get(DEFAULT_ORG).pack_ref == PUBLISHED  # refused: nothing applied
    forced = orgs.apply(DEFAULT_ORG, draft.ref, "ada", force=True)
    assert forced.errors and orgs.get(DEFAULT_ORG).pack_ref == draft.ref
    assert orgs.applied_pack().ref == draft.ref
    assert [v.applied_by for v in metamodels.versions(HIGHER_ED) if v.version == "lean"] == [[DEFAULT_ORG]]
    # the version that fits applies without a word
    clean = orgs.apply(DEFAULT_ORG, PUBLISHED, "ada")
    assert clean.ok and not clean.issues


def test_a_sandbox_applies_the_version_it_is_created_with(loaded, orgs):
    metamodels = MetamodelService(loaded)
    draft = metamodels.draft(PUBLISHED, "ada", version="trial-1", notes="try things")
    trial = orgs.create("Trial", "ada", pack_ref=draft.ref, copy_from=DEFAULT_ORG)
    assert trial.pack_ref == draft.ref
    with use_org("trial"):
        assert orgs.applied_pack().notes == "try things"
        assert Registry(orgs.applied_pack()).pack.status == "draft"
    with pytest.raises(NotFoundError):
        orgs.create("Nowhere", "ada", pack_ref=f"{HIGHER_ED}@nope")


def test_the_roles_guard_organisations_and_versions(loaded, orgs):
    metamodels = MetamodelService(loaded)
    with use_role("architect"):
        with pytest.raises(Forbidden):
            orgs.create("No", "arjun")
        with pytest.raises(Forbidden):
            orgs.apply(DEFAULT_ORG, PUBLISHED, "arjun")
        with pytest.raises(Forbidden):
            metamodels.draft(PUBLISHED, "arjun")
        with pytest.raises(Forbidden):
            metamodels.publish(PUBLISHED, "arjun")
        assert orgs.check(DEFAULT_ORG, PUBLISHED).ok  # checking is reading
    with use_role("reader"):
        with pytest.raises(Forbidden):
            orgs.set_default(DEFAULT_ORG, "ren")


def test_a_readers_sql_answers_for_the_organisation_and_its_version(loaded, orgs):
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "One"), "ada")
        assert int(loaded.query("select count(*) as n from element")["n"][0]) == 1
    assert int(loaded.query("select count(*) as n from element")["n"][0]) == 47
    assert int(loaded.query("with c as (select * from element) select count(*) as n from c")["n"][0]) == 47
    assert int(loaded.query("select count(*) as n from meta_element_type")["n"][0]) == 59
    assert int(loaded.query("select count(*) as n from element", scoped=False)["n"][0]) == 48


def test_a_readers_sql_cannot_name_a_schema_and_read_past_its_organisation(loaded, orgs):
    """The scoping shadows the content tables by their bare names, and only by those.

    A qualified name — `<prefix>_content.element`, or the catalog before it — resolved to the
    base table instead, so a reader standing in one organisation read every organisation's
    rows, and a reader standing on a branch read main's. The system catalogues are how the
    schema names were found, so they are refused with them.
    """
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "Only ours"), "ada")
        schema = schemas(loaded.schema_prefix)[1]  # the content group
        for query in (
            f"select count(*) as n from {schema}.element",
            f"select count(*) as n from memory.{schema}.element",
            f"with c as (select * from {schema}.element) select count(*) as n from c",
            f"select (select count(*) from {schema}.element) as n",
            f"select name from element union all select name from {schema}.element",
            f"select count(*) as n from {schema.upper()}.ELEMENT",
            "select table_name from information_schema.tables",
        ):
            with pytest.raises(ValueError, match="name the table on its own"):
                loaded.query(query)
        # the bare name still answers, and answers for this organisation alone
        assert int(loaded.query("select count(*) as n from element")["n"][0]) == 1


def test_a_readers_sql_cannot_hide_a_schema_in_quotes_or_behind_a_comment(loaded, orgs):
    """The check for a qualified name read the query as written, not as the engine reads it.

    A schema name in double quotes (`"ea_content".element`) or cut from its dot by a block
    comment (`ea_content/**/.element`) was not seen, and read every organisation's rows. The
    query is now read the way the engine reads it — comments dropped, quotes taken off a name —
    before it is checked; and the forms whose extent the engines read differently from any
    such reading (an escape string, a dollar-quoted string, a Unicode escape) are refused.
    """
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "Only ours"), "ada")
        schema = schemas(loaded.schema_prefix)[1]  # the content group
        catalog = loaded._fetch_all("select current_database()")[0][0]
        for query in (
            f'select count(*) as n from "{schema}".element',
            f'select count(*) as n from "{schema}"."element"',
            f'select count(*) as n from "{schema.upper()}".element',
            f'select count(*) as n from"{schema}".element',
            f"select count(*) as n from {schema}/**/.element",
            f"select count(*) as n from {schema}/* one /* nested */ comment */.element",
            f"select count(*) as n from {schema} -- a comment\n.element",
            f"select count(*) as n from {schema}\n\t.\nelement",
            f'select count(*) as n from "{catalog}"."{schema}"."element"',
            f"select count(*) as n from {catalog}.{schema}.element",
            'select count(*) as n from "pg_catalog".pg_class',
            'select count(*) as n from "information_schema".tables',
        ):
            with pytest.raises(ValueError, match="name the table on its own"):
                loaded.query(query)
        unicode_name = "".join(f"\\{ord(c):04x}" for c in schema)
        for query in (
            f"select E'\\'' as a, (select count(*) from {schema}.element) as n, 1 as \"'\"",
            f"select $$'$$ as a, (select count(*) from {schema}.element) as n, 1 as \"'\"",
            f'select count(*) as n from U&"{unicode_name}".element',
        ):
            with pytest.raises(ValueError, match="would hide what the query names"):
                loaded.query(query)
        assert int(loaded.query("select count(*) as n from element")["n"][0]) == 1


def test_a_readers_sql_cannot_reach_a_table_or_a_file_named_in_a_string(loaded, orgs):
    """`query_table('ea_content.element')` read the base table: the scoping shadows the names a
    query is written with, and a name inside a string is a value it cannot see.

    The functions that take a table, a query or a file by a string are refused by name, on both
    engines whichever engine the function belongs to; so are the database's own catalogues and
    functions, reached without naming a schema (`pg_stats` holds sample values of every
    organisation's columns, `pragma_storage_info` the least and greatest of each).
    """
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "Only ours"), "ada")
        table = f"{schemas(loaded.schema_prefix)[1]}.element"
        for query in (
            f"select count(*) as n from query_table('{table}')",
            f"select * from query('select count(*) as n from {table}')",
            f"select count(*) as n from \"QUERY_TABLE\" /* spaced */ ('{table}')",
            f"select * from json_execute_serialized_sql(json_serialize_sql('select count(*) from {table}'))",
            f"select query_to_xml('select count(*) from {table}', true, false, '') as n",
            f"select table_to_xml('{table}', true, false, '') as n",
            "select database_to_xml(true, false, '') as n",
            f"select count(*) as n from ts_stat('select to_tsvector(name) from {table}')",
            "select count(*) as n from read_csv('data/sample/elements.csv')",
            "select count(*) as n from read_text('pyproject.toml')",
            "select count(*) as n from sniff_csv('data/sample/elements.csv')",
            "select count(*) as n from glob('*')",
        ):
            with pytest.raises(ValueError, match="named in a string"):
                loaded.query(query)
        for query in (
            "select count(*) as n from pg_stats",
            "select count(*) as n from pg_class",
            "select pg_read_file('/etc/hostname') as n",
            "select count(*) as n from pragma_storage_info('element')",
            "select count(*) as n from duckdb_tables()",
            "select count(*) as n from sqlite_master",
        ):
            with pytest.raises(ValueError, match="the database's own"):
                loaded.query(query)


def test_a_readers_ordinary_sql_still_answers_for_its_organisation(loaded, orgs):
    """What the stricter reading must not refuse: a quoted name or alias, a string that holds a
    dot, a schema's name or a function's, comments, WITH — each answered for the reader's
    organisation alone."""
    orgs.create("Trial", "ada")
    schema = schemas(loaded.schema_prefix)[1]
    with use_org("trial"):
        loaded.insert_element(
            Element("E1", "capability", "Only ours", description_md=f"{schema}.element"), "ada"
        )

        def n(query: str) -> int:
            return int(loaded.query(query)["n"][0])

        assert n("select count(*) as n from element") == 1
        assert n('select count(*) as "n" from "element" as "e"') == 1
        assert n('select count(*) as n from (select name as "Element name" from element) as s') == 1
        assert n(f"select count(*) as n from element where description_md = '{schema}.element'") == 1
        assert (
            n("select count(*) as n from element where name <> 'a.b' and name <> 'query_table(''x'')'") == 1
        )
        assert (
            n("select count(*) as n from element where name not in ('a--b', '/* c */', 'pg_stats', '$$')")
            == 1
        )
        assert n("select count(*) as n from element e where e.name = 'Only ours'") == 1
        assert n("with c as (select * from element) select count(*) as n from c") == 1
        assert n("select count(*) as n -- how many\nfrom element /* ours */;") == 1
        assert loaded.query("select 'it''s -- not a comment' as x")["x"][0] == "it's -- not a comment"


def _duckdb_macros_that_read_a_name_in_a_string() -> list[str]:
    """DuckDB's own macros that reach `query_table()` or `query()`, however many macros deep.

    Read from DuckDB itself, on a connection of the test's own, so a version of DuckDB that
    ships another such macro fails the test below until the deny-list names it too."""
    con = duckdb.connect()
    try:
        macros = con.execute(
            "SELECT DISTINCT function_name, macro_definition FROM duckdb_functions() "
            "WHERE function_type IN ('macro', 'table_macro') AND macro_definition IS NOT NULL"
        ).fetchall()
    finally:
        con.close()
    readers = {"query_table", "query"}
    while True:
        calls = re.compile(r'(?<![\w$])"?(?:' + "|".join(map(re.escape, readers)) + r')"?\s*\(', re.I)
        more = {name for name, body in macros if name not in readers and calls.search(body)}
        if not more:
            return sorted(readers - {"query_table", "query"})
        readers |= more


def test_a_readers_sql_cannot_reach_a_table_through_one_of_duckdbs_own_macros(loaded, orgs):
    """`histogram_values('ea_content.element', …)` is a macro DuckDB ships, and it reads the table
    named in its string through `query_table()`: every organisation's rows, and the role grants
    only admins read. Every macro of DuckDB's own that reaches `query_table()` or `query()` is
    refused by name, on both engines, as the functions it calls are."""
    found = _duckdb_macros_that_read_a_name_in_a_string()
    assert {"histogram", "histogram_values"} <= set(found), "the listing still finds what it is for"
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "Only ours"), "ada")
        content, governance = schemas(loaded.schema_prefix)[1], schema_of("role_grant", loaded.schema_prefix)
        for name in found:
            for query in (
                f"select * from {name}('{content}.element', org_id || '|' || element_id)",
                f"select * from {name}('{governance}.role_grant', group_id, bin_count := 1000)",
                f"select count(*) as n from element, lateral {name}('{content}.element', name)",
                f"select * from \"{name.upper()}\" /* spaced */ ('{content}.element', org_id)",
                f"select {name}('{content}.element', org_id) as n",
            ):
                with pytest.raises(ValueError, match="named in a string"):
                    loaded.query(query)
        assert int(loaded.query("select count(*) as n from element")["n"][0]) == 1


@pytest.mark.parametrize("engine", ["duckdb", "lakebase"])
def test_a_readers_sql_cannot_read_another_deployments_schemas_in_a_database_they_share(
    engine, request, pack, tmp_path
):
    """Two deployments may share one database, each under its own prefix (decision 0018).

    The qualified-name check knew only the store's own schemas, so a reader of one deployment
    read the other's by naming them — every organisation's rows, and its role grants — and
    `public.` was never refused at all. Every schema and catalogue the connection can see is
    refused before a dot, read from the database when the query is checked.
    """
    if engine == "duckdb":
        path = tmp_path / "shared.duckdb"

        def open_store(prefix: str) -> SqlBackend:
            return DuckDBBackend(path, schema_prefix=prefix)
    else:
        dsn = request.getfixturevalue("postgres_dsn")

        def open_store(prefix: str) -> SqlBackend:
            return LakebaseBackend.from_dsn(dsn, schema=prefix)

    prod_prefix, dev_prefix = new_schema_name(), new_schema_name()
    prod = open_store(prod_prefix)
    prod.save_pack(pack)
    OrganisationService(prod).ensure_default(pack)
    prod.insert_element(Element("PROD-SECRET", "capability", "Prod's own"), "ada")
    prod.set_role_grant(RoleGrant("prod-admins", "Prod admins", "admin"), "ada")
    prod.close()  # a DuckDB file has one process's connection at a time; Postgres does not mind
    dev = open_store(dev_prefix)
    try:
        dev.save_pack(pack)
        OrganisationService(dev).ensure_default(pack)
        prod_content, prod_governance = schemas(prod_prefix)[1], schema_of("role_grant", prod_prefix)
        assert len(dev.query(f"select element_id from {prod_content}.element", scoped=False)) == 1, (
            "the other deployment's rows are there to be read"
        )
        for query in (
            f"select element_id, name, org_id from {prod_content}.element",
            f"select group_id, role from {prod_governance}.role_grant",
            f'select element_id from "{prod_content}"."element"',
            f"select count(*) as n from {prod_content.upper()} . element",
            "select count(*) as n from public.element",
        ):
            with pytest.raises(ValueError, match="name the table on its own"):
                dev.query(query)
        assert int(dev.query("select count(*) as n from element")["n"][0]) == 0
        assert int(dev.query("select count(*) as n from element e where e.name <> 'x'")["n"][0]) == 0
    finally:
        for prefix in (prod_prefix, dev_prefix):
            for schema in schemas(prefix):
                dev._execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        dev.close()


def test_a_readers_recursive_sql_answers_for_its_organisation_on_both_engines(loaded, orgs):
    """The scope is laid around the reader's statement, not merged into its WITH list.

    Merged, a reader's `WITH RECURSIVE` made every scope expression recursive as well, and
    Postgres refused each of them (`element AS (SELECT * FROM element …)` names itself), so no
    recursive query ran on Lakebase. Around it, a name the reader's own WITH gives again
    (`WITH element AS (SELECT * FROM element)`) still reads the scoped rows."""
    default_ids = sorted(loaded.query("select element_id from element")["element_id"])
    walk = (
        "with recursive reach(id, depth) as ("
        " select element_id, 0 from element"
        " union"
        " select r.dst_id, reach.depth + 1 from relationship r join reach on r.src_id = reach.id"
        " where reach.depth < 3"
        ") select count(distinct id) as n from reach"
    )
    assert int(loaded.query(walk)["n"][0]) == len(default_ids) == 47
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "Only ours"), "ada")

        def n(query: str) -> int:
            return int(loaded.query(query)["n"][0])

        series = "with recursive r(n) as (select 1 union all select n + 1 from r where n < 5) select n from r"
        assert list(loaded.query(series + " order by n desc limit 3")["n"]) == [5, 4, 3]
        assert n(walk) == 1
        assert n("with element as (select * from element) select count(*) as n from element") == 1
        assert n("with recursive ids as (select element_id from element) select count(*) as n from ids") == 1
        assert (
            n("select count(*) as n from (with element as (select * from element) select * from element) s")
            == 1
        )
        found = loaded.query(
            "select element_id from element where name = ? and element_id <> ?", ["Only ours", "X"]
        )
        assert list(found["element_id"]) == ["E1"]
    ordered = loaded.query("select element_id from element order by element_id desc limit 3")
    assert list(ordered["element_id"]) == default_ids[::-1][:3]
    assert (
        list(loaded.query("select element_id from element order by element_id", limit=4)["element_id"])
        == (default_ids[:4])
    )


def test_an_older_store_is_given_its_organisation(backend, pack):
    """Rows from before organisations and versions belong to the default organisation, and the
    default organisation applies the pack most recently loaded."""
    backend.insert_element(Element("OLD-1", "capability", "From before"), "ada")
    backend._execute("UPDATE element SET org_id = NULL")
    backend._execute("UPDATE meta_element_type SET pack_version = NULL")
    backend._execute("UPDATE meta_pack SET status = NULL")
    backend._execute("DELETE FROM organisation")
    backend.init_schema()
    assert backend.get_element("OLD-1") is not None
    default = backend.default_organisation()
    assert default is not None and default.pack_ref == pack.ref
    stored = backend.load_pack(pack.id, pack.version)
    assert stored is not None and len(stored.element_types) == len(pack.element_types)
    assert pack_to_dict(stored)["element_types"] == pack_to_dict(pack)["element_types"]
    assert stored.status == "draft"  # a migrated store's pack was edited in place: it stays editable
