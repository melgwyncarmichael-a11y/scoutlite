"""dedupe_players() is pure -- no network, no LLM. The rest of scoutlite_compare.py's main()
orchestrates the live pipeline (research_player + build_comparison_docx), same as
scoutlite_combined.run() -- covered by live smoke-testing, not the unit suite."""
from scoutlite_compare import dedupe_players


def test_no_duplicates_returns_unchanged():
    assert dedupe_players(["Erling Haaland", "Ollie Watkins"]) == ["Erling Haaland", "Ollie Watkins"]


def test_exact_duplicate_is_dropped():
    assert dedupe_players(["Erling Haaland", "Erling Haaland"]) == ["Erling Haaland"]


def test_case_and_whitespace_insensitive():
    assert dedupe_players(["Erling Haaland", "  ERLING HAALAND  "]) == ["Erling Haaland"]


def test_first_occurrence_casing_is_kept():
    result = dedupe_players(["erling haaland", "Erling Haaland"])
    assert result == ["erling haaland"]


def test_preserves_order_of_first_occurrence():
    result = dedupe_players(["B", "A", "B", "C", "A"])
    assert result == ["B", "A", "C"]
