"""Placeholder tests proving the package skeleton imports cleanly.

These tests intentionally exercise only the harness (Todo 1): package
importability, version sanity, the approved pydantic dependency, and the
presence of corpus seed fixtures. Lane behaviour is tested by later todos.
"""

from __future__ import annotations

import pathlib

import pytest


def test_package_importable() -> None:
    """The package must import under its canonical name."""
    import ghrepo_search

    assert ghrepo_search.__name__ == "ghrepo_search"


def test_version_is_nonempty_string() -> None:
    """``__version__`` is a non-empty string consumable by tooling."""
    import ghrepo_search

    assert isinstance(ghrepo_search.__version__, str)
    assert ghrepo_search.__version__.strip()


def test_pydantic_is_usable() -> None:
    """Pydantic is an approved core dependency for the corpus schema lane."""
    import pydantic

    class _Probe(pydantic.BaseModel):
        model_config = pydantic.ConfigDict(strict=True)
        value: int

    probe = _Probe(value=3)
    assert probe.value == 3


def test_fixtures_dir_exists(fixtures_dir: pathlib.Path) -> None:
    """Corpus seed fixtures must exist for downstream lanes."""
    assert fixtures_dir.is_dir(), f"fixtures dir missing: {fixtures_dir}"
    assert (fixtures_dir / "README.md").is_file()
    assert (fixtures_dir / "AGENTS.md").is_file()


def test_untrusted_agents_fixture_is_inert_text(
    fixtures_dir: pathlib.Path,
) -> None:
    """The fixture AGENTS.md is plain corpus text, not executed at import.

    Later lanes assert that an injection probe like the one shipped in this
    fixture is stored verbatim and never routed as an instruction. Here we only
    confirm the probe string is present on disk so the guardrail is testable.
    """
    agents = (fixtures_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "UNTRUSTED CORPUS TEXT" in agents
    assert "injection probe" in agents
