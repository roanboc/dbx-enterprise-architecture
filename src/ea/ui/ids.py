"""Every Dash component id lives here so pages never collide."""

URL = "url"
PAGE = "page"
NOTIFY = "notify"
DOWNLOAD = "download"
NAV_VERSION = "nav-version"
APP_SHELL = "app-shell"
NAV_BURGER = "nav-burger"
NAV_BURGER_CLICK = "nav-burger-click"  # the wrapper that takes the click; Burger reports none
NAVBAR_OPEN = "navbar-open"
MD_TEXT = "md-text"
MD_PREVIEW = "md-preview"
MD_INSERT = "md-insert"
MD_MODE = "md-mode"
MD_WRAP = "md-wrap"

# browse
BROWSE_TYPE = "browse-type"
BROWSE_TEXT = "browse-text"
BROWSE_STATUS = "browse-status"
BROWSE_GRID = "browse-grid"
BROWSE_COUNT = "browse-count"
NEW_OPEN = "new-open"
NEW_MODAL = "new-modal"
NEW_TYPE = "new-type"
NEW_NAME = "new-name"
NEW_DESC = "new-desc"
NEW_SAVE = "new-save"
NEW_FEEDBACK = "new-feedback"

# element
EL_ID = "el-id"
EL_VERSION = "el-version"
EL_TABS = "el-tabs"
EL_NAME = "el-name"
EL_KEY = "el-key"
EL_STATUS = "el-status"
EL_LIFECYCLE = "el-lifecycle"
EL_DESC = "el-desc"
EL_LINKS = "el-links"
EL_SAVE = "el-save"
EL_SAVE_FEEDBACK = "el-save-feedback"
EL_SAVE_WHY = "el-save-why"  # why Save is off, said before anything is typed
EL_ATTR = "el-attr"  # pattern-matching: {"type": EL_ATTR, "name": <attr>}
EL_ATTR_VALUES = "el-attr-values"  # what the element's attributes say, in their groups
EL_REL_DIRECTION = "el-rel-direction"
EL_REL_OTHER = "el-rel-other"
EL_REL_TYPE = "el-rel-type"
EL_REL_QUALIFIER = "el-rel-qualifier"
EL_REL_ADD = "el-rel-add"
EL_REL_FEEDBACK = "el-rel-feedback"
EL_REL_TABLES = "el-rel-tables"
EL_REL_COUNT = "el-rel-count"  # the count in the tab label, kept true as relationships change
EL_REL_DELETE = "el-rel-delete"  # pattern-matching: {"type": EL_REL_DELETE, "id": <relationship_id>}
EL_REL_ATTRS = "el-rel-attrs"  # the inputs of the chosen relationship type's attributes
EL_REL_ATTR = "el-rel-attr"  # pattern-matching: {"type": EL_REL_ATTR, "name": <attr>}
EL_GRAPH = "el-graph"
EL_GRAPH_DEPTH = "el-graph-depth"
EL_GRAPH_TAP = "el-graph-tap"
EL_HISTORY = "el-history"

# organisations (initiative 15)
ORG_SELECT = "org-select"  # header: the organisation the reader is in
ORG_SWITCH = "org-switch"  # pattern-matching: {"type": ORG_SWITCH, "id": <org_id>}, a row's "Switch to"
PACK_BADGE = "pack-badge"  # header: the pack and the version the organisation applies
ORGS_LIST = "orgs-list"
ORGS_FEEDBACK = "orgs-feedback"
ORGS_START_PACK = "orgs-start-pack"  # which shipped metamodel a new organisation starts on
ORGS_START_NAME = "orgs-start-name"
ORGS_START_SAVE = "orgs-start-save"
ORGS_START_WHY = "orgs-start-why"  # why Start is off, beside it
ORGS_START_NOTE = "orgs-start-note"  # what the chosen starter is, under the selector
ORGS_NEW_NAME = "orgs-new-name"
ORGS_NEW_DESC = "orgs-new-desc"
ORGS_NEW_VERSION = "orgs-new-version"
ORGS_NEW_COPY = "orgs-new-copy"
ORGS_NEW_SAVE = "orgs-new-save"
ORGS_NEW_WHY = "orgs-new-why"  # why Create is off, beside it
ORGS_ACTION = "orgs-action"  # pattern-matching: {"type": ORGS_ACTION, "action": <what>, "org": <org_id>}
ORGS_APPLY_ORG = "orgs-apply-org"
ORGS_APPLY_VERSION = "orgs-apply-version"
ORGS_APPLY_FORCE = "orgs-apply-force"
ORGS_APPLY_CHECK = "orgs-apply-check"
ORGS_APPLY_RUN = "orgs-apply-run"
ORGS_APPLY_RESULT = "orgs-apply-result"
ORGS_CONFIRM_MODAL = "orgs-confirm-modal"
ORGS_CONFIRM_TEXT = "orgs-confirm-text"
ORGS_CONFIRM_YES = "orgs-confirm-yes"
ORGS_CONFIRM_STORE = "orgs-confirm-store"

# metamodel
MM_GRAPH = "mm-graph"
MM_BODY = "mm-body"  # everything under the page title, re-rendered when the version shown changes
MM_TABS = "mm-tabs"
MM_LISTS = "mm-lists"  # the inner tabs of Manage: one grid each
MM_VERSION = "mm-version"  # store: the version the page shows, as pack@version
MM_VERSION_SELECT = "mm-version-select"
MM_DOMAINS_GRID = "mm-domains-grid"
MM_GROUPS_GRID = "mm-groups-grid"
MM_ADD_DOMAIN = "mm-add-domain"
MM_ADD_GROUP = "mm-add-group"
MM_GRAPH_INACTIVE = "mm-graph-inactive"
MM_VIEW = "mm-view"  # the metamodel drawn as an architecture view
MM_VIEW_DOMAIN = "mm-view-domain"
MM_VIEW_INACTIVE = "mm-view-inactive"
MM_VIEW_MD = "mm-view-md"
MM_VIEW_DRAWIO = "mm-view-drawio"
MM_VIEW_NOTE = "mm-view-note"
MM_DRAFT_MODAL = "mm-draft-modal"
MM_DRAFT_VERSION = "mm-draft-version"
MM_DRAFT_NOTES = "mm-draft-notes"
MM_DRAFT_APPLY = "mm-draft-apply"
MM_DRAFT_SAVE = "mm-draft-save"
MM_DRAFT_FEEDBACK = "mm-draft-feedback"
MM_VER_ACTION = (
    "mm-ver-action"  # pattern-matching: {"type": MM_VER_ACTION, "action": <what>, "ref": <pack@version>}
)
MM_VER_FEEDBACK = "mm-ver-feedback"
MM_VERSIONS_TABLE = "mm-versions-table"  # every stored version, its state and who applies it
MM_CMP_A = "mm-cmp-a"
MM_CMP_B = "mm-cmp-b"
MM_CMP_RUN = "mm-cmp-run"
MM_CMP_RESULT = "mm-cmp-result"
MM_RENAME_MODAL = "mm-rename-modal"
MM_RENAME_NAME = "mm-rename-name"
MM_RENAME_SAVE = "mm-rename-save"
MM_RENAME_REF = "mm-rename-ref"  # store: the version the open dialog renames
MM_RENAME_FEEDBACK = "mm-rename-feedback"
MM_CONFIRM_MODAL = "mm-confirm-modal"
MM_CONFIRM_TEXT = "mm-confirm-text"
MM_CONFIRM_YES = "mm-confirm-yes"
MM_CONFIRM_STORE = "mm-confirm-store"
MM_DETAIL = "mm-detail"
MM_TYPES_GRID = "mm-types-grid"
MM_RELS_GRID = "mm-rels-grid"
MM_ATTRS_GRID = "mm-attrs-grid"
MM_DEL_TYPE = "mm-del-type"
MM_DEL_REL = "mm-del-rel"
MM_DEL_ATTR = "mm-del-attr"
MM_DEL_DOMAIN = "mm-del-domain"
MM_DEL_GROUP = "mm-del-group"
MM_ADD_TYPE = "mm-add-type"
MM_ADD_REL = "mm-add-rel"
MM_ADD_ATTR = "mm-add-attr"
MM_SAVE = "mm-save"
MM_SAVE_WHY = "mm-save-why"  # why Save changes is off, beside it
MM_EXPORT = "mm-export"
MM_RELOAD = "mm-reload"
MM_FEEDBACK = "mm-feedback"
MM_SUBTITLE = "mm-subtitle"  # the counts under the page title, which a save changes
MM_DOMAIN_FILTER = "mm-domain-filter"
MM_LAYOUT = "mm-layout"
MM_NOTATION_DOMAINS_GRID = "mm-notation-domains-grid"
MM_NOTATION_TYPES_GRID = "mm-notation-types-grid"
MM_NOTATION_SWATCHES = "mm-notation-swatches"  # a chip per domain, in the colour it declares
MM_NOTATION_PREVIEW = "mm-notation-preview"
MM_NOTATION_NOTE = "mm-notation-note"  # why the preview has stopped following the grids

# impact
IMP_ELEMENT = "imp-element"
IMP_DEPTH = "imp-depth"
IMP_RUN = "imp-run"
IMP_RESULT = "imp-result"
IMP_GRAPH = "imp-graph"

# import
IM_UPLOAD = "im-upload"
IM_FILES = "im-files"
IM_DROP = "im-drop"  # pattern-matching: {"type": IM_DROP, "name": <filename>}
IM_STORE = "im-store"
IM_SOURCE = "im-source"
IM_MAPPING = "im-mapping"
IM_TEMPLATE = "im-template"
IM_VALIDATE = "im-validate"
IM_LOAD = "im-load"
IM_REPORT = "im-report"
IM_MAP_UPLOAD = "im-map-upload"  # a mapping YAML of the reader's own
IM_MAP_STORE = "im-map-store"
IM_MAP_NAME = "im-map-name"
IM_EXPORT = "im-export"  # the current content, written back out in the same contract

# feeds
FEED_LIST = "feed-list"
FEED_FEEDBACK = "feed-feedback"
FEED_RUN = "feed-run"  # pattern-matching: {"type": FEED_RUN, "id": <feed_id>}
FEED_DELETE = "feed-delete"  # pattern-matching: {"type": FEED_DELETE, "id": <feed_id>}
FEED_EDIT = "feed-edit"  # pattern-matching: {"type": FEED_EDIT, "id": <feed_id>}
FEED_MODAL = "feed-modal"
FEED_ID = "feed-id"  # store: the feed the modal is editing, empty for a new one
FEED_NAME = "feed-name"
FEED_SOURCE = "feed-source"
FEED_EL_TABLE = "feed-el-table"
FEED_REL_TABLE = "feed-rel-table"
FEED_LINK_TABLE = "feed-link-table"
FEED_BRANCH = "feed-branch"
FEED_EVERY = "feed-every"  # the recurrence: hour, day, week, month
FEED_HOUR = "feed-hour"
FEED_MINUTE = "feed-minute"
FEED_WEEKDAY = "feed-weekday"  # shown for a weekly schedule
FEED_MONTHDAY = "feed-monthday"  # shown for a monthly one
FEED_SHOW_CRON = "feed-show-cron"
FEED_SCHEDULE = "feed-schedule"  # the expression itself, revealed by the checkbox
FEED_SCHEDULE_SAID = "feed-schedule-said"  # the sentence the choices add up to
FEED_TZ = "feed-tz"
FEED_CLEAR = "feed-clear"
FEED_ENABLED = "feed-enabled"
FEED_MAPPING = "feed-mapping"
FEED_EXAMPLE = "feed-example"  # the contract's example files, from the feed form
FEED_MAPPING_SAID = "feed-mapping-said"  # what the mapping typed there would do
FEED_SAVE = "feed-save"
FEED_NEW = "feed-new"
FEED_MODAL_FEEDBACK = "feed-modal-feedback"
RUNS_LIST = "runs-list"
RUNS_OFFSET = "runs-offset"  # store: how far into the history the page is
RUNS_OLDER = "runs-older"
RUNS_NEWER = "runs-newer"

# ask
ASK_INPUT = "ask-input"
ASK_BUTTON = "ask-button"
ASK_HINT = "ask-hint"  # why Ask cannot be pressed, beside it
ASK_RESET = "ask-reset"
ASK_ANSWER = "ask-answer"
ASK_TRACE = "ask-trace"
ASK_PROVIDER = "ask-provider"
ASK_HISTORY = "ask-history"

# Generated architecture views (initiative 2)
MERMAID_SRC = "mermaid-src"  # pattern type: {"type": MERMAID_SRC, "id": <block>}
MERMAID_SVG = "mermaid-svg"
MERMAID_LEGEND = "mermaid-legend"  # pattern type: the colour legend above a diagram
MERMAID_POS = "mermaid-pos"  # shape positions reported by the browser, never saved
MERMAID_RESET = "mermaid-reset"
MERMAID_ZOOM_IN = "mermaid-zoom-in"
MERMAID_ZOOM_OUT = "mermaid-zoom-out"
MERMAID_FIT = "mermaid-fit"
MERMAID_FULL = "mermaid-full"
MERMAID_VIEW = "mermaid-view"  # zoom and pan of the viewport, never saved
EL_VIEW_MD = "el-view-md"
EL_VIEW_DRAWIO = "el-view-drawio"
IMP_VIEW_MD = "imp-view-md"
IMP_VIEW_DRAWIO = "imp-view-drawio"
IMP_VIEW_NOTE = "imp-view-note"  # why the downloads are disabled, beside them
IMP_GRAPH_NOTE = "imp-graph-note"  # how many hops the picture draws, against what the tables answer
ASK_DOC_MD = "ask-doc-md"
ASK_DOC_DRAWIO = "ask-doc-drawio"
ASK_DOC_STORE = "ask-doc-store"

# Branches (initiative 4)
BRANCH_SELECT = "branch-select"  # header: the branch the reader is on
BRANCH_BADGE = "branch-badge"
BRANCH_NEW_WHY = "branch-new-why"  # the same reason, named by aria-describedby
BRANCH_NEW_TIP = "branch-new-tip"  # the label beside the New branch button, kept with the role
BRANCH_NEW_OPEN = "branch-new-open"
BRANCH_NEW_MODAL = "branch-new-modal"
BRANCH_NEW_NAME = "branch-new-name"
BRANCH_NEW_DESC = "branch-new-desc"
BRANCH_NEW_WP = "branch-new-wp"
BRANCH_NEW_SAVE = "branch-new-save"
BRANCH_NEW_FEEDBACK = "branch-new-feedback"
# One disputed field of one change item: which side's value main keeps. Pattern-matched,
# because how many there are depends on the branch.
BR_FIELD_TAKE = "br-field-take"
BR_STATUS = "br-status"
BR_WHERE = "br-where"  # the line saying which branch the reader is on, above the list
BR_LIST = "br-list"
BR_SELECTED = "br-selected"  # store: the branch whose change set is shown
BR_DETAIL = "br-detail"
BR_GRID = "br-grid"
BR_MERGE = "br-merge"
BR_ABANDON = "br-abandon"
BR_SWITCH = "br-switch"
BR_FEEDBACK = "br-feedback"
BR_OPEN = "br-open"  # pattern-matching: {"type": BR_OPEN, "id": <branch_id>}
BR_DIFF_DETAIL = "br-diff-detail"

# Element state (initiative 4)
EL_CURRENT_STATE = "el-current-state"
EL_TARGET_STATE = "el-target-state"
EL_TARGET_WP = "el-target-wp"
EL_TARGET_NOTE = "el-target-note"

# Target state page (initiative 4)
TG_WP = "tg-wp"
TG_ONLY_CHANGES = "tg-only-changes"
TG_BODY = "tg-body"
TG_ADDRESS_NOTE = "tg-address-note"  # what the address asked for that the model does not hold
TG_VIEW_MD = "tg-view-md"
TG_VIEW_DRAWIO = "tg-view-drawio"

# Propose (initiative 5)
PR_TEXT = "pr-text"
PR_UPLOAD = "pr-upload"
PR_FILES = "pr-files"
PR_STORE = "pr-store"
PR_LINKS = "pr-links"
PR_BRANCH = "pr-branch"
PR_BRANCH_NEW = "pr-branch-new"
PR_WP = "pr-wp"
PR_WP_NEW = "pr-wp-new"
PR_TEMPLATE = "pr-template"
PR_EXAMPLE = "pr-example"
PR_ANALYSE = "pr-analyse"
PR_RESULT = "pr-result"
PR_EL_GRID = "pr-el-grid"
PR_REL_GRID = "pr-rel-grid"
PR_ADD_EL = "pr-add-el"
PR_ADD_REL = "pr-add-rel"
PR_APPLY = "pr-apply"
PR_APPLY_WHY = "pr-apply-why"  # why Apply to branch is off, beside it
PR_APPLY_FEEDBACK = "pr-apply-feedback"
PR_PUSHBACK = "pr-pushback"
PR_PROVIDER = "pr-provider"
PR_RESULT_STORE = "pr-result-store"
PR_TPL_PICK = "pr-tpl-pick"  # the template a page is read with, when it names none itself
PR_TPL_UPLOAD = "pr-tpl-upload"  # an admin keeps a template for the organisation
PR_TPL_KEEP = "pr-tpl-keep"  # an admin keeps the picked starter as the organisation's own
PR_TPL_DELETE = "pr-tpl-delete"  # pattern-matching: {"type": PR_TPL_DELETE, "id": template_id}
PR_TPL_LIST = "pr-tpl-list"
PR_TPL_FEEDBACK = "pr-tpl-feedback"
PR_IMPACT = "pr-impact"
PR_VIEW = "pr-view"
PR_TABS = "pr-tabs"  # the preview: rows, what the change touches, the change drawn
# the conversation that settles a draft (initiative 24)
PR_CONV = "pr-conv"  # the conversation panel beside the draft
PR_CONV_STORE = "pr-conv-store"  # the turns so far
PR_DRAFT_STORE = "pr-draft-store"  # the draft's identifier once kept
PR_Q_DATA = "pr-q-data"  # pattern-matching: {"type": PR_Q_DATA, "qid": qid} — a question's options
PR_Q_OPT = "pr-q-opt"  # pattern-matching: the choice picked
PR_Q_CHOICE = "pr-q-choice"  # pattern-matching: the second pick a choice needs (a relationship, a type)
PR_Q_TEXT = "pr-q-text"  # pattern-matching: the words, name or page a choice needs
PR_Q_SEND = "pr-q-send"  # pattern-matching: answer this question
PR_MESSAGE = "pr-message"  # the architect's own words to the assistant
PR_SEND = "pr-send"
PR_TURN_FEEDBACK = "pr-turn-feedback"
PR_DRAFTS = "pr-drafts"  # the architect's drafts, to pick up
PR_DRAFT_RESUME = "pr-draft-resume"  # pattern-matching: {"type": PR_DRAFT_RESUME, "id": proposal_id}
PR_DRAFT_DISCARD = "pr-draft-discard"  # pattern-matching: {"type": PR_DRAFT_DISCARD, "id": proposal_id}
BR_PROPOSALS = "br-proposals"  # the proposals a branch came from, for the reviewer
BR_IMPACT = "br-impact"
BR_TABS = "br-tabs"  # a branch: its changes, the proposals it came from, what it touches, drawn

# Search, bulk edit (initiative 6)
BROWSE_EMPTY = "browse-empty"  # what the screen says when the grid has nothing in it
BROWSE_SELECTED = "browse-selected"
# The filters beyond the three the page started with. Each narrows with the others, and
# every one of them round-trips through the address bar so a search can be shared.
BROWSE_CURRENT = "browse-current"
BROWSE_TARGET = "browse-target"
BROWSE_WP = "browse-wp"
BROWSE_SOURCE = "browse-source"
BROWSE_LIFECYCLE = "browse-lifecycle"
BROWSE_ATTR_NAME = "browse-attr-name"
BROWSE_ATTR_VALUE = "browse-attr-value"
BROWSE_UPDATED_SINCE = "browse-updated-since"
BROWSE_SORT = "browse-sort"
BROWSE_DESC = "browse-desc"
BROWSE_MORE = "browse-more"  # the drawer holding the filters that are not the common three
BROWSE_MORE_OPEN = "browse-more-open"
BROWSE_CLEAR = "browse-clear"
BROWSE_CHIPS = "browse-chips"  # what is narrowing the list, as removable chips
BROWSE_PAGE = "browse-page"  # which page of the result set is on screen
BROWSE_PAGER = "browse-pager"
BROWSE_EXPORT = "browse-export"  # the result set as CSV
BROWSE_COLUMNS = "browse-columns"  # which columns the grid shows
BULK_OPEN = "bulk-open"
BULK_MODAL = "bulk-modal"
BULK_STATUS = "bulk-status"
BULK_CURRENT = "bulk-current"
BULK_TARGET = "bulk-target"
BULK_WP = "bulk-wp"
BULK_NOTE = "bulk-note"
BULK_LIFECYCLE = "bulk-lifecycle"
BULK_ATTR_NAME = "bulk-attr-name"
BULK_ATTR_VALUE = "bulk-attr-value"
BULK_ATTR_CLEAR = "bulk-attr-clear"  # empty the attribute rather than write a blank into it
BULK_SAVE = "bulk-save"
BULK_FEEDBACK = "bulk-feedback"
BROWSE_FILTER_NOTE = "browse-filter-note"

# Health (initiative 6)
HEALTH_BODY = "health-body"
HEALTH_REFRESH = "health-refresh"

# Roles and review (initiative 7)
PERSONA_SELECT = "persona-select"
ROLE_BADGE = "role-badge"
RV_PANEL = "rv-panel"
RV_REQUEST = "rv-request"
RV_APPROVE = "rv-approve"
RV_SEND_BACK = "rv-send-back"
RV_TYPES = "rv-types"
RV_COMMENT = "rv-comment"
RV_FEEDBACK = "rv-feedback"
MM_REVIEWERS_GRID = "mm-reviewers-grid"
MM_REVIEWERS_SAVE = "mm-reviewers-save"
MM_REVIEWERS_FEEDBACK = "mm-reviewers-feedback"
