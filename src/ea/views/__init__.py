"""Architecture views: a subgraph of the model rendered in an architecture notation.

One view model (:mod:`ea.views.model`), several renderers: Mermaid in the
notation of this repository's own architecture documents (:mod:`ea.views.mermaid`)
and a draft draw.io file (:mod:`ea.views.drawio`). Nothing here draws by hand:
every node is an element of the model and carries its identifier.
"""

from ea.views.model import (
    View,
    ViewEdge,
    ViewNode,
    has_state_markers,
    view_from_ids,
    view_from_impact,
    view_from_metamodel,
    view_from_neighbourhood,
)

__all__ = [
    "View",
    "ViewEdge",
    "ViewNode",
    "has_state_markers",
    "view_from_ids",
    "view_from_impact",
    "view_from_metamodel",
    "view_from_neighbourhood",
]
