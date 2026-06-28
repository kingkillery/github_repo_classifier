from __future__ import annotations

from typing import assert_never

from ghrepo_search.fetch import ContentProvider, FetchedFile
from ghrepo_search.models import DeepeningEvidence, FetchMiss, QueryResponse, QueryResult


def _evidence_from_file(fetched: FetchedFile) -> DeepeningEvidence:
    snippet = " ".join(fetched.content.split())[:500]
    return DeepeningEvidence(path=fetched.path, snippet=snippet)


def _deepen_result(result: QueryResult, provider: ContentProvider, paths: tuple[str, ...]) -> QueryResult:
    evidence: list[DeepeningEvidence] = []
    for path in paths:
        match provider.fetch_file(result.repo_full_name, path):
            case FetchedFile() as fetched:
                evidence.append(_evidence_from_file(fetched))
            case FetchMiss():
                continue
            case unreachable:
                assert_never(unreachable)
    return result.model_copy(update={"deepening_used": bool(evidence), "deepening_evidence": tuple(evidence)})


def deepen_results(response: QueryResponse, provider: ContentProvider) -> QueryResponse:
    if not response.trace.deepening_requested or not response.results:
        return response
    paths = response.trace.deepening_paths or tuple(match.path for match in response.results[0].matched_chunks[:1])
    results = (_deepen_result(response.results[0], provider, paths), *response.results[1:])
    return response.model_copy(update={"results": results})
