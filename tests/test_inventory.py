from __future__ import annotations

import json
from pathlib import Path

import pytest

from ghrepo_search.inventory import InventoryWriteError, build_inventory, write_manifest
from ghrepo_search.models import Origin


def test_inventory_dedupes_owned_and_starred_origins() -> None:
    """Given duplicate owned/starred repos; when inventory builds; then origins merge."""
    owned = [
        {
            "nameWithOwner": "KingKillery/Alpha",
            "url": "https://github.com/KingKillery/Alpha",
            "description": "Owned repo",
            "defaultBranchRef": {"name": "main"},
            "isPrivate": False,
            "primaryLanguage": {"name": "Python"},
            "stargazerCount": 7,
            "repositoryTopics": [{"name": "agents"}],
            "pushedAt": "2026-01-01T00:00:00Z",
            "licenseInfo": {"spdxId": "MIT"},
        }
    ]
    starred = [
        {
            "full_name": "kingkillery/alpha",
            "html_url": "https://github.com/kingkillery/alpha",
            "description": "Starred copy",
            "default_branch": "main",
            "private": False,
            "language": "Python",
            "stargazers_count": 9,
            "topics": ["search"],
            "pushed_at": "2026-01-02T00:00:00Z",
            "license": {"spdx_id": "Apache-2.0"},
        }
    ]

    records = build_inventory(owned=owned, starred=starred)

    assert len(records) == 1
    repo = records[0]
    assert repo.full_name == "kingkillery/alpha"
    assert repo.origins == frozenset({Origin.OWNED, Origin.STARRED})
    assert repo.owner == "kingkillery"
    assert repo.name == "alpha"
    assert repo.url == "https://github.com/KingKillery/Alpha"

def test_inventory_automatically_tags_categories() -> None:
    """Given owned non-fork repo with <100 stars; when inventory builds; then categories are tagged."""
    owned = [
        {
            "nameWithOwner": "kingkillery/speak-extension",
            "url": "https://github.com/kingkillery/speak-extension",
            "description": "An mcp server for speech",
            "isFork": False,
            "stargazerCount": 5,
        }
    ]

    records = build_inventory(owned=owned, starred=[])

    assert len(records) == 1
    repo = records[0]
    assert "kingkillery-original" in repo.topics
    assert "hidden-gem" in repo.topics
    assert "mcp-server" in repo.topics
    assert "plugin-extension" in repo.topics


def test_manifest_write_rejects_malformed_repo_without_partial_file(tmp_path: Path) -> None:
    """Given malformed repo payload; when writing manifest; then no partial file remains."""
    output = tmp_path / "manifest.json"

    with pytest.raises(InventoryWriteError) as error:
        write_manifest(output, build_inventory(owned=[{"url": "https://example.com/nope"}], starred=[]))

    assert "invalid GitHub repository" in str(error.value)
    assert not output.exists()


def test_manifest_round_trips_origin_flags(tmp_path: Path) -> None:
    """Given inventory records; when manifest writes; then JSON preserves origins."""
    output = tmp_path / "manifest.json"
    records = build_inventory(
        owned=[{"nameWithOwner": "owner/tool", "url": "https://github.com/owner/tool"}],
        starred=[{"full_name": "friend/lib", "html_url": "https://github.com/friend/lib"}],
    )

    write_manifest(output, records)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert {item["full_name"] for item in data} == {"owner/tool", "friend/lib"}
    origins_by_repo = {item["full_name"]: set(item["origins"]) for item in data}
    assert origins_by_repo == {"owner/tool": {"owned"}, "friend/lib": {"starred"}}
