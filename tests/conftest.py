"""Shared pytest fixtures for the ghrepo_search test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"
"""Absolute path to the corpus fixtures used by the test harness."""


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Resolve the shared fixtures directory as a typed ``Path``."""
    return FIXTURES_DIR
