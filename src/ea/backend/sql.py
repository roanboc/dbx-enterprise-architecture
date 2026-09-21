"""Portable DDL. One schema, two engines: DuckDB locally, Lakebase (Postgres) on Databricks.

Every row of content belongs to an organisation (`org_id`, decision 0014) and every
metamodel row to one version of a pack (`pack_version`, decision 0015).

Types are kept to the four both engines read as written (`VARCHAR`, `INTEGER`,
`BOOLEAN`, `TIMESTAMP`). JSON is stored as text and parsed in Python, which
keeps the DDL identical and the rows readable from any SQL client.

These tables are modelled in `architecture/3_information/3_logical-data-model.md`
— keys, references and what each column carries. A change here changes that page
in the same commit.
"""

import re

META_TABLES = [
    "meta_pack",
    "meta_domain",
    "meta_attribute_group",
    "meta_element_type",
    "meta_attribute",
    "meta_relationship_type",
]
CONTENT_TABLES = ["element", "relationship", "element_link", "change_log"]
BRANCH_TABLES = [
    "branch",
    "branch_element",
    "branch_relationship",
    "branch_link",
    "proposal",
    "branch_review",
    "reviewer_assignment",
]
# Where content arrives from, and what arrived: a feed's configuration and the history of every
# run of it. Neither is content and neither hangs off a branch — they belong to the organisation
# directly.
FEED_TABLES = ["source_feed", "import_run"]
# Every table whose rows belong to one organisation (decision 0014): the content, the change
# log, the branches and everything that hangs off a branch, the feeds and their history. The
# organisation table itself and the metamodel tables are shared by every organisation.
ORG_TABLES = CONTENT_TABLES + BRANCH_TABLES + FEED_TABLES
# What an organisation's deletion leaves behind. The change log is kept because it is the one
# append-only record of what was done to the store. A run is *not* kept with it: an org_id may
# be taken again by a later organisation, and a run carries the actor names, file names, issue
# messages and whole mapping of the organisation that is gone — which would reappear as the new
# organisation's own history. The change log has always had that hole; this does not widen it.
AUDIT_TABLES = ["change_log"]

# The tables are grouped the way `architecture/3_information/3_logical-data-model.md` groups
# them, and each group is a schema of its own, named `<prefix>_<group>`. Someone who opens the
# database with a SQL client meets the model rather than seventeen tables in a heap, and a
# grant can be given per group — the audit trail read by more people than may write content.
# The prefix is `EA_SCHEMA` (`ea` by default), so two deployments can share one database.
SCHEMA_GROUPS: dict[str, list[str]] = {
    "metamodel": list(META_TABLES),
    "content": ["organisation", "element", "relationship", "element_link"],
    "branch": ["branch", "branch_element", "branch_relationship", "branch_link"],
    # A feed's configuration sits with the other things that govern how content arrives
    # and is reviewed, rather than with the content itself.
    "governance": ["branch_review", "reviewer_assignment", "proposal", "source_feed"],
    # A run is what happened, beside the change log's what changed. Both are read by more
    # people than may write content, which is what the group is for.
    "audit": ["change_log", "import_run"],
    # The store creates the schema and never a table in it. What lands here is put there
    # from outside — a platform job writing Postgres, or a catalogue table replicated into
    # it — and the application's contract with a source is the shape of the table, nothing
    # more (decision 0020).
    "staging": [],
}
TABLE_GROUP: dict[str, str] = {t: g for g, tables in SCHEMA_GROUPS.items() for t in tables}


def schemas(prefix: str) -> list[str]:
    """Every schema of a store, in the order the search path reads them."""
    return [f"{prefix}_{group}" for group in SCHEMA_GROUPS]


def staging_schema(prefix: str) -> str:
    """Where a source's rows wait to be read. The one schema the store does not own."""
    return f"{prefix}_staging"


def schema_of(table: str, prefix: str) -> str:
    return f"{prefix}_{TABLE_GROUP[table]}"


def qualified(table: str, prefix: str) -> str:
    """`<schema>.<table>`. Every statement that makes or alters a table names it this way: an
    unqualified one would land in whichever schema the search path reads first."""
    return f"{schema_of(table, prefix)}.{table}"


# Columns added after a table first shipped. The store applies them to an existing
# one on start-up (ADD COLUMN IF NOT EXISTS, which both engines read), so an older
# store keeps working. A column may be declared anywhere in the DDL: a store that
# gained it by migration holds it physically last, and every write names its columns
# rather than counting on their order.
MIGRATIONS: list[tuple[str, str, str]] = [
    ("meta_domain", "notation", "VARCHAR"),
    ("meta_element_type", "notation", "VARCHAR"),
    ("element", "current_state", "VARCHAR"),
    ("element", "target_state", "VARCHAR"),
    ("element", "target_work_package", "VARCHAR"),
    ("element", "target_note", "VARCHAR"),
    ("relationship", "current_state", "VARCHAR"),
    ("relationship", "target_state", "VARCHAR"),
    ("relationship", "target_work_package", "VARCHAR"),
    ("relationship", "target_note", "VARCHAR"),
    ("change_log", "branch_id", "VARCHAR"),
    # initiative 15: the metamodel in versions, the content in organisations
    ("meta_pack", "status", "VARCHAR"),
    ("meta_pack", "derived_from", "VARCHAR"),
    ("meta_pack", "notes", "VARCHAR"),
    ("meta_pack", "properties", "VARCHAR"),
    ("meta_pack", "created_by", "VARCHAR"),
    ("meta_pack", "created_at", "TIMESTAMP"),
    ("meta_pack", "published_by", "VARCHAR"),
    ("meta_pack", "published_at", "TIMESTAMP"),
    ("meta_domain", "pack_version", "VARCHAR"),
    ("meta_domain", "properties", "VARCHAR"),
    ("meta_element_type", "pack_version", "VARCHAR"),
    ("meta_element_type", "abstract", "BOOLEAN"),
    ("meta_element_type", "properties", "VARCHAR"),
    ("meta_attribute", "pack_version", "VARCHAR"),
    ("meta_attribute", "rel_type_id", "VARCHAR"),
    ("meta_attribute", "extra", "VARCHAR"),
    ("meta_relationship_type", "pack_version", "VARCHAR"),
    ("meta_relationship_type", "properties", "VARCHAR"),
    # initiative 19: the row as main held it when the branch first touched it, so a merge can
    # tell what the branch changed apart from what main changed, rather than only that both did
    ("branch_element", "base_row", "VARCHAR"),
    ("branch_relationship", "base_row", "VARCHAR"),
] + [(table, "org_id", "VARCHAR") for table in ORG_TABLES]

STATE_COLUMNS_DDL = """,
            current_state VARCHAR,
            target_state VARCHAR,
            target_work_package VARCHAR,
            target_note VARCHAR"""
BRANCH_EXTRA_DDL = """,
            branch_id VARCHAR NOT NULL,
            base_version INTEGER NOT NULL,
            op VARCHAR NOT NULL,
            base_row VARCHAR"""
ORG_COLUMN_DDL = """,
            org_id VARCHAR"""

DDL: dict[str, str] = {
    "meta_pack": """
        CREATE TABLE IF NOT EXISTS meta_pack (
            pack_id VARCHAR NOT NULL,
            name VARCHAR,
            version VARCHAR,
            description VARCHAR,
            source VARCHAR,
            provenance_values VARCHAR,
            loaded_at TIMESTAMP,
            status VARCHAR,
            derived_from VARCHAR,
            notes VARCHAR,
            properties VARCHAR,
            created_by VARCHAR,
            created_at TIMESTAMP,
            published_by VARCHAR,
            published_at TIMESTAMP
        )""",
    "meta_domain": """
        CREATE TABLE IF NOT EXISTS meta_domain (
            pack_id VARCHAR NOT NULL,
            domain_id VARCHAR NOT NULL,
            name VARCHAR,
            description VARCHAR,
            sort_order INTEGER,
            notation VARCHAR,
            pack_version VARCHAR,
            properties VARCHAR
        )""",
    "meta_attribute_group": """
        CREATE TABLE IF NOT EXISTS meta_attribute_group (
            pack_id VARCHAR NOT NULL,
            group_id VARCHAR NOT NULL,
            name VARCHAR,
            description VARCHAR,
            sort_order INTEGER,
            pack_version VARCHAR,
            properties VARCHAR
        )""",
    "meta_element_type": """
        CREATE TABLE IF NOT EXISTS meta_element_type (
            pack_id VARCHAR NOT NULL,
            type_id VARCHAR NOT NULL,
            name VARCHAR,
            plural VARCHAR,
            supertype_id VARCHAR,
            active BOOLEAN,
            deactivation_reason VARCHAR,
            domain_id VARCHAR,
            provenance VARCHAR,
            prefix VARCHAR,
            description VARCHAR,
            examples VARCHAR,
            source_of_record VARCHAR,
            type_owner VARCHAR,
            instance_owner VARCHAR,
            sort_order INTEGER,
            notation VARCHAR,
            pack_version VARCHAR,
            abstract BOOLEAN,
            properties VARCHAR
        )""",
    "meta_attribute": """
        CREATE TABLE IF NOT EXISTS meta_attribute (
            pack_id VARCHAR NOT NULL,
            type_id VARCHAR,
            name VARCHAR NOT NULL,
            label VARCHAR,
            datatype VARCHAR,
            required BOOLEAN,
            enum_values VARCHAR,
            description VARCHAR,
            sensitivity VARCHAR,
            sort_order INTEGER,
            pack_version VARCHAR,
            rel_type_id VARCHAR,
            extra VARCHAR
        )""",
    "meta_relationship_type": """
        CREATE TABLE IF NOT EXISTS meta_relationship_type (
            pack_id VARCHAR NOT NULL,
            rel_type_id VARCHAR NOT NULL,
            name VARCHAR,
            inverse_name VARCHAR,
            source_type_id VARCHAR,
            target_type_id VARCHAR,
            provenance VARCHAR,
            qualifiers VARCHAR,
            diagrams VARCHAR,
            description VARCHAR,
            src_max INTEGER,
            dst_max INTEGER,
            sort_order INTEGER,
            pack_version VARCHAR,
            properties VARCHAR
        )""",
    "organisation": """
        CREATE TABLE IF NOT EXISTS organisation (
            org_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            description VARCHAR,
            pack_id VARCHAR,
            pack_version VARCHAR,
            is_default BOOLEAN,
            copied_from VARCHAR,
            created_by VARCHAR,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )""",
    "element": """
        CREATE TABLE IF NOT EXISTS element (
            element_id VARCHAR NOT NULL,
            type_id VARCHAR NOT NULL,
            key VARCHAR,
            name VARCHAR NOT NULL,
            description_md VARCHAR,
            status VARCHAR NOT NULL,
            lifecycle_status VARCHAR,
            source_system VARCHAR,
            source_ref VARCHAR,
            external_ids VARCHAR,
            attrs VARCHAR,
            origin VARCHAR,
            _version INTEGER NOT NULL,
            created_at TIMESTAMP,
            created_by VARCHAR,
            updated_at TIMESTAMP,
            updated_by VARCHAR"""
    + STATE_COLUMNS_DDL
    + ORG_COLUMN_DDL
    + """
        )""",
    "relationship": """
        CREATE TABLE IF NOT EXISTS relationship (
            relationship_id VARCHAR NOT NULL,
            rel_type_id VARCHAR NOT NULL,
            src_id VARCHAR NOT NULL,
            dst_id VARCHAR NOT NULL,
            qualifier VARCHAR,
            attrs VARCHAR,
            status VARCHAR NOT NULL,
            origin VARCHAR,
            source_system VARCHAR,
            source_ref VARCHAR,
            _version INTEGER NOT NULL,
            created_at TIMESTAMP,
            created_by VARCHAR,
            updated_at TIMESTAMP,
            updated_by VARCHAR"""
    + STATE_COLUMNS_DDL
    + ORG_COLUMN_DDL
    + """
        )""",
    "element_link": """
        CREATE TABLE IF NOT EXISTS element_link (
            link_id VARCHAR NOT NULL,
            element_id VARCHAR NOT NULL,
            url VARCHAR NOT NULL,
            label VARCHAR,
            sort_order INTEGER,
            org_id VARCHAR
        )""",
    "change_log": """
        CREATE TABLE IF NOT EXISTS change_log (
            change_id VARCHAR NOT NULL,
            entity_kind VARCHAR NOT NULL,
            entity_id VARCHAR NOT NULL,
            op VARCHAR NOT NULL,
            actor VARCHAR,
            changed_at TIMESTAMP,
            before_json VARCHAR,
            after_json VARCHAR,
            version INTEGER,
            branch_id VARCHAR,
            org_id VARCHAR
        )""",
    "branch": """
        CREATE TABLE IF NOT EXISTS branch (
            branch_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            description VARCHAR,
            work_package VARCHAR,
            status VARCHAR NOT NULL,
            created_by VARCHAR,
            created_at TIMESTAMP,
            closed_by VARCHAR,
            closed_at TIMESTAMP,
            org_id VARCHAR
        )""",
    "branch_element": """
        CREATE TABLE IF NOT EXISTS branch_element (
            element_id VARCHAR NOT NULL,
            type_id VARCHAR NOT NULL,
            key VARCHAR,
            name VARCHAR NOT NULL,
            description_md VARCHAR,
            status VARCHAR NOT NULL,
            lifecycle_status VARCHAR,
            source_system VARCHAR,
            source_ref VARCHAR,
            external_ids VARCHAR,
            attrs VARCHAR,
            origin VARCHAR,
            _version INTEGER NOT NULL,
            created_at TIMESTAMP,
            created_by VARCHAR,
            updated_at TIMESTAMP,
            updated_by VARCHAR"""
    + STATE_COLUMNS_DDL
    + BRANCH_EXTRA_DDL
    + ORG_COLUMN_DDL
    + """
        )""",
    "branch_relationship": """
        CREATE TABLE IF NOT EXISTS branch_relationship (
            relationship_id VARCHAR NOT NULL,
            rel_type_id VARCHAR NOT NULL,
            src_id VARCHAR NOT NULL,
            dst_id VARCHAR NOT NULL,
            qualifier VARCHAR,
            attrs VARCHAR,
            status VARCHAR NOT NULL,
            origin VARCHAR,
            source_system VARCHAR,
            source_ref VARCHAR,
            _version INTEGER NOT NULL,
            created_at TIMESTAMP,
            created_by VARCHAR,
            updated_at TIMESTAMP,
            updated_by VARCHAR"""
    + STATE_COLUMNS_DDL
    + BRANCH_EXTRA_DDL
    + ORG_COLUMN_DDL
    + """
        )""",
    "branch_link": """
        CREATE TABLE IF NOT EXISTS branch_link (
            link_id VARCHAR NOT NULL,
            element_id VARCHAR NOT NULL,
            url VARCHAR NOT NULL,
            label VARCHAR,
            sort_order INTEGER,
            branch_id VARCHAR NOT NULL,
            org_id VARCHAR
        )""",
    "branch_review": """
        CREATE TABLE IF NOT EXISTS branch_review (
            review_id VARCHAR NOT NULL,
            branch_id VARCHAR NOT NULL,
            reviewer VARCHAR NOT NULL,
            decision VARCHAR NOT NULL,
            type_ids VARCHAR,
            comment VARCHAR,
            decided_at TIMESTAMP,
            org_id VARCHAR
        )""",
    "reviewer_assignment": """
        CREATE TABLE IF NOT EXISTS reviewer_assignment (
            type_id VARCHAR NOT NULL,
            reviewer VARCHAR NOT NULL,
            added_by VARCHAR,
            added_at TIMESTAMP,
            org_id VARCHAR
        )""",
    "proposal": """
        CREATE TABLE IF NOT EXISTS proposal (
            proposal_id VARCHAR NOT NULL,
            branch_id VARCHAR NOT NULL,
            title VARCHAR,
            sources_json VARCHAR,
            result_json VARCHAR,
            pushback_json VARCHAR,
            status VARCHAR,
            created_by VARCHAR,
            created_at TIMESTAMP,
            org_id VARCHAR
        )""",
    "source_feed": """
        CREATE TABLE IF NOT EXISTS source_feed (
            feed_id VARCHAR NOT NULL,
            name VARCHAR,
            source_system VARCHAR,
            elements_table VARCHAR,
            relationships_table VARCHAR,
            links_table VARCHAR,
            mapping_yaml VARCHAR,
            target_branch VARCHAR,
            clear_after BOOLEAN,
            enabled BOOLEAN,
            schedule VARCHAR,
            schedule_timezone VARCHAR,
            last_run_at TIMESTAMP,
            last_run_status VARCHAR,
            last_run_summary VARCHAR,
            created_at TIMESTAMP,
            created_by VARCHAR,
            updated_at TIMESTAMP,
            updated_by VARCHAR,
            org_id VARCHAR
        )""",
    # What a run was, kept after the request that produced it has gone. The counts are columns
    # rather than a payload because a person opening the database with a SQL client is meant to
    # be able to ask what last night loaded; only the issue sample and the per-code totals,
    # which have no fixed shape, are JSON.
    "import_run": """
        CREATE TABLE IF NOT EXISTS import_run (
            run_id VARCHAR NOT NULL,
            source_system VARCHAR,
            trigger_kind VARCHAR,
            feed_id VARCHAR,
            feed_name VARCHAR,
            actor VARCHAR,
            branch_id VARCHAR,
            inputs VARCHAR,
            mapping_yaml VARCHAR,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            status VARCHAR,
            summary VARCHAR,
            message VARCHAR,
            elements_created INTEGER,
            elements_updated INTEGER,
            elements_unchanged INTEGER,
            elements_retired INTEGER,
            relationships_created INTEGER,
            relationships_updated INTEGER,
            relationships_unchanged INTEGER,
            relationships_retired INTEGER,
            links_loaded INTEGER,
            error_count INTEGER,
            warning_count INTEGER,
            issues_json VARCHAR,
            issue_counts_json VARCHAR,
            truncated BOOLEAN,
            org_id VARCHAR
        )""",
}

ELEMENT_COLUMNS = [
    "element_id",
    "type_id",
    "key",
    "name",
    "description_md",
    "status",
    "lifecycle_status",
    "source_system",
    "source_ref",
    "external_ids",
    "attrs",
    "origin",
    "_version",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "current_state",
    "target_state",
    "target_work_package",
    "target_note",
]
RELATIONSHIP_COLUMNS = [
    "relationship_id",
    "rel_type_id",
    "src_id",
    "dst_id",
    "qualifier",
    "attrs",
    "status",
    "origin",
    "source_system",
    "source_ref",
    "_version",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "current_state",
    "target_state",
    "target_work_package",
    "target_note",
]
STATE_COLUMNS = ["current_state", "target_state", "target_work_package", "target_note"]

# Recursive traversal over `relationship`, as a walk: a node is visited once, not once per
# path that reaches it. The recursive term dedupes with UNION, so a cycle ends of itself and
# a hub does not multiply — where enumerating paths is bounded by nothing, this is bounded by
# the nodes reached. Each row carries the edge that reached it, so one shortest path per node
# is rebuilt from the rows themselves rather than by reading the relationships a second time:
# measured on 100,000 elements and 600,000 relationships, carrying the edge costs a few
# milliseconds and looking it up afterwards costs seconds, because the second pass plans as a
# join against the whole table.
#
# The walk never steps back onto the element it started from: a cycle would otherwise return
# it as a node reached by way of itself, and anything beyond it is reachable from the start
# in fewer hops anyway. Every string column is cast in both terms of the recursion because
# Postgres holds the recursive term to the types of the first one; ROW_NUMBER over a window reads the same on
# both engines, where MIN_BY does not. `{rel}` is the scoped relationship source, `{step}` the
# end the walk stands on and `{take}` the end it moves to, substituted by the backend.
TRACE_SQL = """
WITH RECURSIVE walk(node_id, depth, via_id, rel_type_id) AS (
    SELECT CAST(? AS VARCHAR), 0, CAST('' AS VARCHAR), CAST('' AS VARCHAR)
    UNION
    SELECT CAST(r.{take} AS VARCHAR), w.depth + 1,
           CAST(w.node_id AS VARCHAR), CAST(r.rel_type_id AS VARCHAR)
    FROM walk w JOIN {rel} r ON r.{step} = w.node_id
    WHERE w.depth < ? AND r.status <> 'retired' AND r.{take} <> ?
)
SELECT node_id, depth, via_id, rel_type_id FROM (
    SELECT node_id, depth, via_id, rel_type_id,
           ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY depth, via_id, rel_type_id) AS pick
    FROM walk WHERE depth > 0
) AS picked WHERE pick = 1 ORDER BY depth, node_id
"""

# Which end of a relationship the walk stands on, and which it moves to.
TRACE_ENDS: dict[str, tuple[str, str]] = {"out": ("src_id", "dst_id"), "in": ("dst_id", "src_id")}

# The same walk ignoring direction, for a neighbourhood: a reader asking what sits around an
# element means both ways round, and a path may turn — out of one element and into the next.
# Each edge is read twice, once from each end, so the step still joins on an indexed column
# rather than on an OR the planner cannot use.
TRACE_SQL_BOTH = """
WITH RECURSIVE walk(node_id, depth, via_id, rel_type_id) AS (
    SELECT CAST(? AS VARCHAR), 0, CAST('' AS VARCHAR), CAST('' AS VARCHAR)
    UNION
    SELECT CAST(r.to_id AS VARCHAR), w.depth + 1,
           CAST(w.node_id AS VARCHAR), CAST(r.rel_type_id AS VARCHAR)
    FROM walk w JOIN (
        SELECT src_id AS from_id, dst_id AS to_id, rel_type_id, status FROM {rel}
        UNION ALL
        SELECT dst_id AS from_id, src_id AS to_id, rel_type_id, status FROM {rel}
    ) r ON r.from_id = w.node_id
    WHERE w.depth < ? AND r.status <> 'retired' AND r.to_id <> ?
)
SELECT node_id, depth, via_id, rel_type_id FROM (
    SELECT node_id, depth, via_id, rel_type_id,
           ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY depth, via_id, rel_type_id) AS pick
    FROM walk WHERE depth > 0
) AS picked WHERE pick = 1 ORDER BY depth, node_id
"""

# Indexes, created on start-up and never assumed to exist: a store that already holds a
# duplicate refuses the unique one, and the store logs it rather than failing to open.
#
# The unique ones are the logical keys of `3_logical-data-model.md`, which the store has always
# enforced in Python and nothing enforced in the database. `meta_attribute` has none: its key
# holds `type_id` or `rel_type_id` and never both, and the two engines do not agree on whether
# two NULLs are the same value.
#
# The rest are the read paths that grow with the model: the two ends of a walk, the rows that
# hang off an element, and the log of one element's changes.
INDEXES: list[tuple[str, str, bool, str]] = [
    ("meta_pack_key", "meta_pack", True, "(pack_id, version)"),
    ("meta_domain_key", "meta_domain", True, "(pack_id, pack_version, domain_id)"),
    ("meta_attribute_group_key", "meta_attribute_group", True, "(pack_id, pack_version, group_id)"),
    ("meta_element_type_key", "meta_element_type", True, "(pack_id, pack_version, type_id)"),
    ("meta_relationship_type_key", "meta_relationship_type", True, "(pack_id, pack_version, rel_type_id)"),
    ("meta_attribute_version", "meta_attribute", False, "(pack_id, pack_version)"),
    ("organisation_key", "organisation", True, "(org_id)"),
    ("element_key", "element", True, "(org_id, element_id)"),
    ("element_type", "element", False, "(org_id, type_id)"),
    ("relationship_key", "relationship", True, "(org_id, relationship_id)"),
    ("relationship_src", "relationship", False, "(org_id, src_id)"),
    ("relationship_dst", "relationship", False, "(org_id, dst_id)"),
    ("element_link_key", "element_link", True, "(org_id, link_id)"),
    ("element_link_element", "element_link", False, "(org_id, element_id)"),
    ("source_feed_key", "source_feed", True, "(org_id, feed_id)"),
    ("change_log_key", "change_log", True, "(org_id, change_id)"),
    ("change_log_entity", "change_log", False, "(org_id, entity_id)"),
    ("branch_key", "branch", True, "(org_id, branch_id)"),
    ("branch_element_key", "branch_element", True, "(org_id, branch_id, element_id)"),
    ("branch_relationship_key", "branch_relationship", True, "(org_id, branch_id, relationship_id)"),
    ("branch_relationship_src", "branch_relationship", False, "(org_id, branch_id, src_id)"),
    ("branch_relationship_dst", "branch_relationship", False, "(org_id, branch_id, dst_id)"),
    ("branch_link_key", "branch_link", True, "(org_id, branch_id, link_id)"),
    ("branch_link_element", "branch_link", False, "(org_id, branch_id, element_id)"),
    ("branch_review_key", "branch_review", True, "(org_id, review_id)"),
    ("reviewer_assignment_key", "reviewer_assignment", True, "(org_id, type_id, reviewer)"),
    ("proposal_key", "proposal", True, "(org_id, proposal_id)"),
    ("import_run_key", "import_run", True, "(org_id, run_id)"),
    # The history is read newest first, and a feed's own history is read the same way.
    ("import_run_recent", "import_run", False, "(org_id, started_at)"),
    ("import_run_feed", "import_run", False, "(org_id, feed_id, started_at)"),
]


def index_sql(name: str, table: str, unique: bool, columns: str, prefix: str) -> str:
    return (
        f"CREATE {'UNIQUE ' if unique else ''}INDEX IF NOT EXISTS {name} "
        f"ON {qualified(table, prefix)} {columns}"
    )


def create_table_sql(table: str, prefix: str) -> str:
    """The table's DDL, in the schema of its group."""
    head = f"CREATE TABLE IF NOT EXISTS {table}"
    return DDL[table].replace(head, f"CREATE TABLE IF NOT EXISTS {qualified(table, prefix)}", 1)


_COLUMN_RE = re.compile(r"^\s*(\w+)\s+(VARCHAR|INTEGER|BOOLEAN|TIMESTAMP)\b", re.MULTILINE)


def column_types(table: str) -> dict[str, str]:
    """The columns of a table and their portable types, in DDL order, read from the DDL itself."""
    return dict(_COLUMN_RE.findall(DDL[table]))


def table_columns(table: str) -> list[str]:
    return list(column_types(table))
