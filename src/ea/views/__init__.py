"""Architecture views: a subgraph of the model rendered in an architecture notation.

One view model (:mod:`ea.views.model`), several renderers: Mermaid in the
notation of this repository's own architecture documents (:mod:`ea.views.mermaid`)
and a draw.io file a solution architect edits rather than redraws
(:mod:`ea.views.drawio`), laid out under a viewpoint the pack declares by
:mod:`ea.views.layout`. Nothing here draws by hand: every node is an element of
the model and carries its identifier.
"""

from ea.views.model import (
    DEFAULT_VIEWPOINT,
    View,
    ViewEdge,
    ViewNode,
    apply_viewpoint,
    has_state_markers,
    view_from_ids,
    view_from_impact,
    view_from_metamodel,
    view_from_neighbourhood,
)

__all__ = [
    "DEFAULT_VIEWPOINT",
    "apply_viewpoint",
    "View",
    "ViewEdge",
    "ViewNode",
    "has_state_markers",
    "view_from_ids",
    "view_from_impact",
    "view_from_metamodel",
    "view_from_neighbourhood",
]
