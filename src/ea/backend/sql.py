"""Portable DDL. One schema, two engines: DuckDB locally, Delta on Databricks.

Types are kept to the intersection both understand (a backend spells them in
its own dialect: `VARCHAR` is `STRING` on Databricks). JSON is stored as text
and parsed in Python, which keeps the DDL identical and the rows readable from
any SQL client.
"""

import re

META_TABLES = ["meta_pack", "meta_domain", "meta_element_type", "meta_attribute", "meta_relationship_type"]
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

# Columns added after a table first shipped. A backend applies them to an existing
# store on start-up (ADD COLUMN IF NOT EXISTS on DuckDB, DESCRIBE then ADD COLUMNS
# on Databricks), so an older store keeps working. New columns go at the end
# because the inserts are positional.
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
]

STATE_COLUMNS_DDL = """,
            current_state VARCHAR,
            target_state VARCHAR,
            target_work_package VARCHAR,
            target_note VARCHAR"""
BRANCH_EXTRA_DDL = """,
            branch_id VARCHAR NOT NULL,
            base_version INTEGER NOT NULL,
            op VARCHAR NOT NULL"""

DDL: dict[str, str] = {
    "meta_pack": """
        CREATE TABLE IF NOT EXISTS meta_pack (
            pack_id VARCHAR NOT NULL,
            name VARCHAR,
            version VARCHAR,
            description VARCHAR,
            source VARCHAR,
            provenance_values VARCHAR,
            loaded_at TIMESTAMP
        )""",
    "meta_domain": """
        CREATE TABLE IF NOT EXISTS meta_domain (
            pack_id VARCHAR NOT NULL,
            domain_id VARCHAR NOT NULL,
            name VARCHAR,
            description VARCHAR,
            sort_order INTEGER,
            notation VARCHAR
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
            notation VARCHAR
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
            sort_order INTEGER
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
            sort_order INTEGER
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
    + """
        )""",
    "element_link": """
        CREATE TABLE IF NOT EXISTS element_link (
            link_id VARCHAR NOT NULL,
            element_id VARCHAR NOT NULL,
            url VARCHAR NOT NULL,
            label VARCHAR,
            sort_order INTEGER
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
            branch_id VARCHAR
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
            closed_at TIMESTAMP
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
    + """
        )""",
    "branch_link": """
        CREATE TABLE IF NOT EXISTS branch_link (
            link_id VARCHAR NOT NULL,
            element_id VARCHAR NOT NULL,
            url VARCHAR NOT NULL,
            label VARCHAR,
            sort_order INTEGER,
            branch_id VARCHAR NOT NULL
        )""",
    "branch_review": """
        CREATE TABLE IF NOT EXISTS branch_review (
            review_id VARCHAR NOT NULL,
            branch_id VARCHAR NOT NULL,
            reviewer VARCHAR NOT NULL,
            decision VARCHAR NOT NULL,
            type_ids VARCHAR,
            comment VARCHAR,
            decided_at TIMESTAMP
        )""",
    "reviewer_assignment": """
        CREATE TABLE IF NOT EXISTS reviewer_assignment (
            type_id VARCHAR NOT NULL,
            reviewer VARCHAR NOT NULL,
            added_by VARCHAR,
            added_at TIMESTAMP
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
            created_at TIMESTAMP
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

# Recursive traversal over the relationship table. Parameters: start id, max depth.
# `{rel}` is the relationship source of the current branch and `{string}` the
# engine's string type; both are substituted by the backend. out = follow
# src->dst, in = dst->src. INSTR, MIN_BY and || read the same on both engines.
TRACE_OUT_SQL = """
WITH RECURSIVE walk(start_id, node_id, depth, path, rel_path) AS (
    SELECT ?, ?, 0, CAST(? AS {string}), CAST('' AS {string})
    UNION ALL
    SELECT w.start_id, r.dst_id, w.depth + 1,
           w.path || '>' || r.dst_id,
           CASE WHEN w.rel_path = '' THEN r.rel_type_id ELSE w.rel_path || '>' || r.rel_type_id END
    FROM walk w JOIN {rel} r ON r.src_id = w.node_id
    WHERE w.depth < ? AND r.status <> 'retired' AND INSTR('>' || w.path || '>', '>' || r.dst_id || '>') = 0
)
SELECT node_id, MIN(depth) AS depth, MIN_BY(path, depth) AS path, MIN_BY(rel_path, depth) AS rel_path
FROM walk WHERE depth > 0 GROUP BY node_id ORDER BY depth, node_id
"""

TRACE_IN_SQL = """
WITH RECURSIVE walk(start_id, node_id, depth, path, rel_path) AS (
    SELECT ?, ?, 0, CAST(? AS {string}), CAST('' AS {string})
    UNION ALL
    SELECT w.start_id, r.src_id, w.depth + 1,
           w.path || '<' || r.src_id,
           CASE WHEN w.rel_path = '' THEN r.rel_type_id ELSE w.rel_path || '<' || r.rel_type_id END
    FROM walk w JOIN {rel} r ON r.dst_id = w.node_id
    WHERE w.depth < ? AND r.status <> 'retired' AND INSTR('<' || w.path || '<', '<' || r.src_id || '<') = 0
)
SELECT node_id, MIN(depth) AS depth, MIN_BY(path, depth) AS path, MIN_BY(rel_path, depth) AS rel_path
FROM walk WHERE depth > 0 GROUP BY node_id ORDER BY depth, node_id
"""

_COLUMN_RE = re.compile(r"^\s*(\w+)\s+(VARCHAR|INTEGER|BOOLEAN|TIMESTAMP)\b", re.MULTILINE)


def column_types(table: str) -> dict[str, str]:
    """The columns of a table and their portable types, in DDL order, read from the DDL itself."""
    return dict(_COLUMN_RE.findall(DDL[table]))


def table_columns(table: str) -> list[str]:
    return list(column_types(table))
