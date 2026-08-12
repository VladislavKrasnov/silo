from __future__ import annotations

from app.pagination import paginate


class TestPaginate:
    def test_splits_items_by_page_size(self) -> None:
        page = paginate(list(range(10)), 0, 4)
        assert page.items == (0, 1, 2, 3)
        assert page.total_pages == 3

    def test_returns_middle_page(self) -> None:
        page = paginate(list(range(10)), 1, 4)
        assert page.items == (4, 5, 6, 7)

    def test_returns_final_partial_page(self) -> None:
        page = paginate(list(range(10)), 2, 4)
        assert page.items == (8, 9)

    def test_clamps_negative_index_to_zero(self) -> None:
        page = paginate(list(range(10)), -5, 4)
        assert page.page_index == 0

    def test_clamps_out_of_range_index_to_last_page(self) -> None:
        page = paginate(list(range(10)), 999, 4)
        assert page.page_index == 2

    def test_empty_sequence_yields_single_empty_page(self) -> None:
        page = paginate([], 0, 4)
        assert page.items == ()
        assert page.total_pages == 1
        assert page.page_index == 0

    def test_has_previous_and_next_flags(self) -> None:
        page = paginate(list(range(10)), 1, 4)
        assert page.has_previous is True
        assert page.has_next is True

        first_page = paginate(list(range(10)), 0, 4)
        assert first_page.has_previous is False

        last_page = paginate(list(range(10)), 2, 4)
        assert last_page.has_next is False
