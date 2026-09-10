"""Shared fixtures. Everything here is offline -- no network, no API keys needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def haaland_html() -> str:
    """A real FBref player page (Erling Haaland), captured 2026-09-11."""
    return (FIXTURES / "haaland_page.html").read_text()


@pytest.fixture(scope="session")
def danny_ward_search_html() -> str:
    """A real FBref multi-match search results page for 'Danny Ward'."""
    return (FIXTURES / "danny_ward_search.html").read_text()
