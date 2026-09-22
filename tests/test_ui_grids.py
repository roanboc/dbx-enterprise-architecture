"""What the two data grids promise the reader, asserted where a browser is not needed.

A grid is mostly a browser's business, but two of its properties are arithmetic over a
constant and belong here, where they run on every change rather than in the round that runs
on demand: whether a control the grid offers can keep the promise the page makes beside it,
and whether the columns fit the card they are drawn in.
"""

from __future__ import annotations

from ea.ui.pages import branches, browse

#: What the merge log has to fit inside. The round is taken at a 1600 px viewport: the
#: navigation takes 220, the page 24 of padding each side and the card 16, which leaves
#: about 1265 for the grid itself. A column past that edge is not unreachable — the grid
#: scrolls — but the reader does not know it is there.
MERGE_LOG_BUDGET = 1265


def _minimum_width(columns: list[dict]) -> int:
    """The narrowest the grid can draw itself: a fixed width, or a flex column's minimum."""
    return sum(int(c.get("width") or c.get("minWidth") or 0) for c in columns)


def test_browse_offers_no_column_filter_while_it_holds_one_page():
    """The grid holds one page of the result set, so a funnel would narrow the wrong thing.

    Sorting was turned off for exactly this reason — the store orders the whole result set
    and the grid shows a page of it. A column filter has the same problem and is worse for
    being silent: it would narrow the hundred rows on screen while the count beside it went
    on reporting the store's total, so the two would disagree from row 101 on.
    """
    assert browse.GRID_OPTIONS["pagination"] is False, "the store pages; the grid must not"
    defaults = browse._grid_defaults()
    assert defaults["sortable"] is False
    assert defaults["filter"] is False, (
        "a funnel narrows the page, not the result set, while the count reports the total"
    )


def test_the_merge_log_fits_the_card_it_is_drawn_in():
    """Every column of the merge log has to be visible, the decision column most of all.

    The 'take' cell is the one control that settles a conflict. A column added without
    checking the arithmetic pushed it to the card's edge and the two version columns past
    it, on a wide screen, while the accordion below went on telling the reader to read them.
    """
    width = _minimum_width(branches.GRID_COLUMNS)
    assert width <= MERGE_LOG_BUDGET, (
        f"the merge log needs {width}px and has about {MERGE_LOG_BUDGET}; "
        f"the take and version columns fall off the right edge"
    )


def test_every_merge_log_column_the_reader_decides_with_is_present():
    """Narrowing the columns must not become dropping the ones that carry the decision."""
    fields = [c.get("field") for c in branches.GRID_COLUMNS]
    for needed in ("include", "change", "entity_id", "label", "conflict", "resolution"):
        assert needed in fields, f"the merge log lost {needed}"
