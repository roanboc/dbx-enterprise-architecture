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
EL_REL_DIRECTION = "el-rel-direction"
EL_REL_OTHER = "el-rel-other"
EL_REL_TYPE = "el-rel-type"
EL_REL_QUALIFIER = "el-rel-qualifier"
EL_REL_ADD = "el-rel-add"
EL_REL_FEEDBACK = "el-rel-feedback"
EL_REL_TABLES = "el-rel-tables"
EL_REL_COUNT = "el-rel-count"  # the count in the tab label, kept true as relationships change
EL_REL_DELETE = "el-rel-delete"  # pattern-matching: {"type": EL_REL_DELETE, "id": <relationship_id>}
EL_GRAPH = "el-graph"
EL_GRAPH_DEPTH = "el-graph-depth"
EL_GRAPH_TAP = "el-graph-tap"
EL_HISTORY = "el-history"

# metamodel
MM_GRAPH = "mm-graph"
MM_DETAIL = "mm-detail"
MM_TYPES_GRID = "mm-types-grid"
MM_RELS_GRID = "mm-rels-grid"
MM_ATTRS_GRID = "mm-attrs-grid"
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

# Search, bulk edit (initiative 6)
BROWSE_EMPTY = "browse-empty"  # what the screen says when the grid has nothing in it
BROWSE_SELECTED = "browse-selected"
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
