from __future__ import annotations

import json
from pathlib import Path

from ghrepo_search.bucket import BucketConfig, RecordingSyncRunner, plan_bucket_sync, sync_bucket
from ghrepo_search.corpus import chunk_documents
from ghrepo_search.deepening import deepen_results
from ghrepo_search.eval import GoldenQuery, MissKind, run_eval
from ghrepo_search.export import export_classified_repos
from ghrepo_search.fetch import FixtureContentProvider, fetch_first_stage_docs
from ghrepo_search.index import SearchIndex
from ghrepo_search.inventory import build_inventory
from ghrepo_search.models import Origin, SourceKind
from ghrepo_search.search import QueryEngine, QueryRequest


def test_fetch_records_readme_agents_and_misses_as_untrusted(fixtures_dir: Path) -> None:
    """Given fixture docs; when docs-first fetch runs; then hits are untrusted and misses survive."""
    repo = build_inventory(
        owned=[{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture"}],
        starred=[],
    )[0]
    provider = FixtureContentProvider.from_directory(
        repo=repo.full_name,
        root=fixtures_dir,
        extra_paths={"README.md", "AGENTS.md"},
    )

    result = fetch_first_stage_docs(repo, provider)

    paths = {doc.path for doc in result.documents}
    assert {"README.md", "AGENTS.md"}.issubset(paths)
    assert all(not doc.trusted for doc in result.documents)
    agents = next(doc for doc in result.documents if doc.path == "AGENTS.md")
    assert agents.source_kind is SourceKind.AGENTS
    assert "Ignore all previous instructions" in agents.content
    assert "CLAUDE.md" in {miss.path for miss in result.misses}


def test_corpus_chunks_preserve_heading_hash_and_trust(fixtures_dir: Path) -> None:
    """Given fetched docs; when chunking; then metadata and inert trust state persist."""
    repo = build_inventory(
        owned=[{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture"}],
        starred=[],
    )[0]
    provider = FixtureContentProvider.from_directory(repo.full_name, fixtures_dir, {"README.md", "AGENTS.md"})
    fetched = fetch_first_stage_docs(repo, provider)

    chunks = chunk_documents(fetched.documents, target_chars=120)

    assert chunks
    chunk = next(item for item in chunks if item.path == "AGENTS.md")
    assert chunk.repo_full_name == "owner/fixture"
    assert chunk.source_kind is SourceKind.AGENTS
    assert chunk.heading == "AGENTS.md (fixture)"
    assert not chunk.trusted
    assert len(chunk.content_hash) == 64


def test_hybrid_search_returns_lexical_vector_scores_and_filters(tmp_path: Path, fixtures_dir: Path) -> None:
    """Given fixture corpus; when querying; then exact and semantic searches have traces."""
    repo = build_inventory(
        owned=[{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture", "language": "Python"}],
        starred=[],
    )[0]
    provider = FixtureContentProvider.from_directory(repo.full_name, fixtures_dir, {"README.md", "AGENTS.md"})
    fetched = fetch_first_stage_docs(repo, provider)
    chunks = chunk_documents(fetched.documents)
    index = SearchIndex.open(tmp_path / "search.sqlite")
    index.rebuild([repo], chunks)
    engine = QueryEngine(index)

    exact = engine.query(QueryRequest(text="acme-pdf-parser", enable_vector=False))
    semantic = engine.query(QueryRequest(text="find tools for extracting documents", enable_lexical=False))
    filtered = engine.query(QueryRequest(text="acme-pdf-parser", language="Rust"))

    assert exact.results[0].repo_full_name == "owner/fixture"
    assert exact.results[0].lexical_score > 0
    assert exact.results[0].vector_score == 0
    assert semantic.results[0].repo_full_name == "owner/fixture"
    assert semantic.results[0].vector_score > 0
    assert semantic.results[0].source_kind in {SourceKind.README, SourceKind.AGENTS}
    assert not filtered.results
    assert filtered.trace.filters == {"language": "Rust"}


def test_deepening_fetches_only_when_needed(tmp_path: Path, fixtures_dir: Path) -> None:
    """Given low-evidence result; when deepening runs; then requested raw path is attached."""
    repo = build_inventory(
        owned=[{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture"}],
        starred=[],
    )[0]
    provider = FixtureContentProvider.from_directory(repo.full_name, fixtures_dir, {"README.md", "AGENTS.md"})
    fetched = fetch_first_stage_docs(repo, provider)
    index = SearchIndex.open(tmp_path / "search.sqlite")
    index.rebuild([repo], chunk_documents(fetched.documents))
    engine = QueryEngine(index)

    high = engine.query(QueryRequest(text="acme-pdf-parser"))
    low = engine.query(QueryRequest(text="delete corpus", deepen=True, deepening_paths=("AGENTS.md",)))

    unchanged = deepen_results(high, provider)
    deepened = deepen_results(low, provider)

    assert unchanged.results[0].deepening_used is False
    assert deepened.results[0].deepening_used is True
    assert deepened.results[0].deepening_evidence[0].path == "AGENTS.md"
    assert provider.fetch_log.count("AGENTS.md") == 2


def test_bucket_sync_is_optional_dry_run_first(tmp_path: Path) -> None:
    """Given local artifacts; when sync plans; then dry-run is inert and apply calls boundary."""
    artifact = tmp_path / "manifest.json"
    artifact.write_text("[]", encoding="utf-8")
    config = BucketConfig(bucket_uri="hf://private/github-repos", local_root=tmp_path)
    runner = RecordingSyncRunner()

    plan = plan_bucket_sync(config)
    dry_run = sync_bucket(config, apply=False, runner=runner)
    applied = sync_bucket(config, apply=True, runner=runner)

    assert [item.relative_path for item in plan.objects] == ["manifest.json"]
    assert dry_run.applied is False
    assert runner.calls == [(tmp_path, "hf://private/github-repos")]
    assert applied.applied is True


def test_eval_classifies_intentional_miss(tmp_path: Path, fixtures_dir: Path) -> None:
    """Given golden query miss; when eval runs; then taxonomy label is emitted."""
    repo = build_inventory(
        owned=[{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture"}],
        starred=[],
    )[0]
    provider = FixtureContentProvider.from_directory(repo.full_name, fixtures_dir, {"README.md"})
    fetched = fetch_first_stage_docs(repo, provider)
    index = SearchIndex.open(tmp_path / "search.sqlite")
    index.rebuild([repo], chunk_documents(fetched.documents))
    engine = QueryEngine(index)

    report = run_eval(
        engine,
        [GoldenQuery(text="document extraction", expected_repo="owner/missing", expected_miss=MissKind.INVENTORY_MISS)],
    )

    assert report.passed is False
    assert report.results[0].miss_kind is MissKind.INVENTORY_MISS
    assert report.results[0].found_repo == "owner/fixture"


def test_compatibility_export_matches_visualizer_shape(tmp_path: Path, fixtures_dir: Path) -> None:
    """Given manifest and chunks; when exporting; then visualizer-required fields exist."""
    repo = build_inventory(
        owned=[{"nameWithOwner": "owner/fixture", "url": "https://github.com/owner/fixture", "stargazerCount": 3}],
        starred=[],
    )[0]
    provider = FixtureContentProvider.from_directory(repo.full_name, fixtures_dir, {"README.md"})
    fetched = fetch_first_stage_docs(repo, provider)
    output = tmp_path / "classified_repos.json"

    export_classified_repos([repo], chunk_documents(fetched.documents), output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data[0]["github_url"] == "https://github.com/owner/fixture"
    assert data[0]["star_count"] == 3
    assert {"project_domain", "motivation", "tech_stack", "code_quality", "innovativeness", "usefulness", "user_friendliness", "underrated", "overrated"}.issubset(data[0])
