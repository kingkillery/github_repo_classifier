from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ghrepo_search.index import SearchHit, SearchIndex
from ghrepo_search.models import ChunkMatch, Origin, QueryResponse, QueryResult, QueryTrace, SourceKind

_RRF_K: Final[int] = 60


@dataclass(frozen=True, slots=True)
class QueryRequest:
    text: str
    limit: int = 10
    enable_lexical: bool = True
    enable_vector: bool = True
    language: str = ""
    origin: Origin | None = None
    source_kind: SourceKind | None = None
    deepen: bool = False
    deepening_paths: tuple[str, ...] = ()


def _snippet(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:240]


def _passes_filters(hit: SearchHit, request: QueryRequest) -> bool:
    if request.language and hit.repo.language.lower() != request.language.lower():
        return False
    if request.origin is not None and request.origin not in hit.repo.origins:
        return False
    if request.source_kind is not None and hit.chunk.source_kind is not request.source_kind:
        return False
    return True


def _filter_trace(request: QueryRequest) -> dict[str, str]:
    filters: dict[str, str] = {}
    if request.language:
        filters["language"] = request.language
    if request.origin is not None:
        filters["origin"] = request.origin.value
    if request.source_kind is not None:
        filters["source_kind"] = request.source_kind.value
    return filters


def _chunk_match(hit: SearchHit) -> ChunkMatch:
    return ChunkMatch(
        chunk_id=hit.chunk.chunk_id,
        path=hit.chunk.path,
        source_kind=hit.chunk.source_kind,
        heading=hit.chunk.heading,
        snippet=_snippet(hit.chunk.text),
    )


@dataclass(frozen=True, slots=True)
class _Accumulated:
    repo_full_name: str
    title: str
    lexical_score: float
    vector_score: float
    fused_score: float
    chunks: tuple[ChunkMatch, ...]


class QueryEngine:
    def __init__(self, index: SearchIndex) -> None:
        self.index = index

    def query(self, request: QueryRequest) -> QueryResponse:
        lexical = self.index.lexical(request.text, request.limit * 3) if request.enable_lexical else []
        vector = self.index.vector(request.text, request.limit * 3) if request.enable_vector else []
        lexical = [hit for hit in lexical if _passes_filters(hit, request)]
        vector = [hit for hit in vector if _passes_filters(hit, request)]
        accumulated = self._accumulate(lexical, vector)
        results = tuple(self._to_result(item, request) for item in sorted(accumulated.values(), key=lambda value: value.fused_score, reverse=True)[: request.limit])
        return QueryResponse(
            query=request.text,
            results=results,
            trace=QueryTrace(
                filters=_filter_trace(request),
                lexical_enabled=request.enable_lexical,
                vector_enabled=request.enable_vector,
                deepening_requested=request.deepen,
                deepening_paths=request.deepening_paths,
            ),
        )

    def _accumulate(self, lexical: list[SearchHit], vector: list[SearchHit]) -> dict[str, _Accumulated]:
        values: dict[str, _Accumulated] = {}
        for hit in lexical:
            values[hit.repo.full_name] = self._with_hit(values.get(hit.repo.full_name), hit, lexical_score=hit.score, vector_score=0.0, fused_score=1 / (_RRF_K + hit.rank))
        for hit in vector:
            values[hit.repo.full_name] = self._with_hit(values.get(hit.repo.full_name), hit, lexical_score=0.0, vector_score=hit.score, fused_score=1 / (_RRF_K + hit.rank))
        return values

    def _with_hit(self, existing: _Accumulated | None, hit: SearchHit, *, lexical_score: float, vector_score: float, fused_score: float) -> _Accumulated:
        match = _chunk_match(hit)
        if existing is None:
            return _Accumulated(hit.repo.full_name, hit.repo.name, lexical_score, vector_score, fused_score, (match,))
        chunks = existing.chunks if match in existing.chunks else (*existing.chunks, match)
        return _Accumulated(
            existing.repo_full_name,
            existing.title,
            max(existing.lexical_score, lexical_score),
            max(existing.vector_score, vector_score),
            existing.fused_score + fused_score,
            chunks,
        )

    def _to_result(self, value: _Accumulated, request: QueryRequest) -> QueryResult:
        source_kind = value.chunks[0].source_kind if value.chunks else SourceKind.METADATA
        return QueryResult(
            repo_full_name=value.repo_full_name,
            title=value.title,
            lexical_score=value.lexical_score,
            vector_score=value.vector_score,
            fused_score=value.fused_score,
            source_kind=source_kind,
            matched_chunks=value.chunks,
        )
