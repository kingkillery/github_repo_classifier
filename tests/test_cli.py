from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ghrepo_search.cli import app


def test_cli_fixture_pipeline_outputs_query_and_export(tmp_path: Path, fixtures_dir: Path) -> None:
    """Given fixture files; when CLI pipeline runs; then query and export work end to end."""
    runner = CliRunner()
    owned = tmp_path / "owned.json"
    manifest = tmp_path / "manifest.json"
    docs = tmp_path / "docs.json"
    chunks = tmp_path / "chunks.json"
    db = tmp_path / "search.sqlite"
    export = tmp_path / "classified_repos.json"
    owned.write_text(
        json.dumps([{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture"}]),
        encoding="utf-8",
    )

    inventory = runner.invoke(app, ["inventory", "--owned-json", str(owned), "--output", str(manifest)])
    fetch = runner.invoke(
        app,
        ["fetch", "--manifest", str(manifest), "--fixture-docs-dir", str(fixtures_dir), "--output", str(docs)],
    )
    corpus = runner.invoke(app, ["corpus", "--docs", str(docs), "--output", str(chunks)])
    index = runner.invoke(app, ["index", "--manifest", str(manifest), "--chunks", str(chunks), "--db", str(db)])
    query = runner.invoke(app, ["query", "--db", str(db), "acme-pdf-parser"])
    compat = runner.invoke(app, ["export", "--manifest", str(manifest), "--chunks", str(chunks), "--output", str(export)])

    assert inventory.exit_code == 0, inventory.output
    assert fetch.exit_code == 0, fetch.output
    assert corpus.exit_code == 0, corpus.output
    assert index.exit_code == 0, index.output
    assert query.exit_code == 0, query.output
    assert compat.exit_code == 0, compat.output
    assert json.loads(query.output)["results"][0]["repo_full_name"] == "owner/fixture"
    assert json.loads(export.read_text(encoding="utf-8"))[0]["github_url"] == "https://github.com/owner/fixture"

def test_cli_bucket_dry_run_outputs_planned_objects(tmp_path: Path) -> None:
    """Given artifact directory; when bucket sync dry-runs; then JSON plan is emitted."""
    artifact = tmp_path / "manifest.json"
    artifact.write_text("[]", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["sync-bucket", "--local-root", str(tmp_path), "--bucket-uri", "hf://private/github-repos"],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["applied"] is False
    assert payload["objects"] == [{"relative_path": "manifest.json", "size_bytes": 2}]


def test_cli_help_lists_full_pipeline() -> None:
    """Given CLI help; when displayed; then all user-facing commands are present."""
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("inventory", "fetch", "corpus", "index", "query", "deepen", "sync-bucket", "eval", "export"):
        assert command in result.output
