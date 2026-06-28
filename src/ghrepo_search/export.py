from __future__ import annotations

import json
from pathlib import Path

from ghrepo_search.models import DEFAULT_CLASSIFIER_SCORE, CorpusChunk, RepoRecord, SourceKind


def _motivation_for(repo: RepoRecord, chunks: tuple[CorpusChunk, ...]) -> str:
    for chunk in chunks:
        if chunk.repo_full_name == repo.full_name and chunk.source_kind is SourceKind.README:
            return " ".join(chunk.text.split())[:500]
    return repo.description


def _domain_for(repo: RepoRecord) -> str:
    if repo.topics:
        return ", ".join(repo.topics)
    return repo.language or "repository"


def export_classified_repos(repos: list[RepoRecord], chunks: tuple[CorpusChunk, ...], output: Path) -> None:
    rows = []
    for repo in repos:
        rows.append(
            {
                "project_domain": _domain_for(repo),
                "motivation": _motivation_for(repo, chunks),
                "tech_stack": repo.language,
                "code_quality": DEFAULT_CLASSIFIER_SCORE,
                "innovativeness": DEFAULT_CLASSIFIER_SCORE,
                "usefulness": DEFAULT_CLASSIFIER_SCORE,
                "user_friendliness": DEFAULT_CLASSIFIER_SCORE,
                "underrated": 0,
                "overrated": 0,
                "github_url": repo.url,
                "star_count": repo.stars,
                "commit_count": 0,
                "last_commit_date": repo.pushed_at or "N/A",
                "open_issues_count": 0,
                "license": repo.license or "N/A",
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
