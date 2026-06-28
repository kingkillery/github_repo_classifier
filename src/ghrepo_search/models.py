from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class Origin(StrEnum):
    OWNED = "owned"
    STARRED = "starred"


class SourceKind(StrEnum):
    METADATA = "metadata"
    README = "readme"
    AGENTS = "agents_md"
    CLAUDE = "claude_md"
    CONTRIBUTING = "contributing"
    DOCS_INDEX = "docs_index"
    PACKAGE = "package_metadata"
    RAW = "raw"


class FetchMissKind(StrEnum):
    NOT_FOUND = "not_found"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    FILE_TOO_LARGE = "file_too_large"
    API_ERROR = "api_error"


class RepoRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    full_name: str
    owner: str
    name: str
    url: str
    origins: frozenset[Origin]
    description: str = ""
    default_branch: str = "main"
    visibility: str = "public"
    language: str = ""
    stars: int = 0
    forks: int = 0
    topics: tuple[str, ...] = ()
    pushed_at: str = ""
    license: str = ""
    is_fork: bool = False


class DocumentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    path: str
    source_kind: SourceKind
    content: str
    trusted: bool = False
    content_hash: str
    fetched_at: str = "fixture"


class FetchMiss(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    path: str
    kind: FetchMissKind
    message: str = ""


class FetchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: RepoRecord
    documents: tuple[DocumentRecord, ...]
    misses: tuple[FetchMiss, ...]


class CorpusChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    repo_full_name: str
    path: str
    source_kind: SourceKind
    heading: str
    text: str
    trusted: bool
    content_hash: str
    ordinal: int


class ChunkMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    path: str
    source_kind: SourceKind
    heading: str
    snippet: str


class DeepeningEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    snippet: str


class QueryTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    filters: dict[str, str] = Field(default_factory=dict)
    lexical_enabled: bool = True
    vector_enabled: bool = True
    deepening_requested: bool = False
    deepening_paths: tuple[str, ...] = ()

class QueryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    title: str
    lexical_score: float
    vector_score: float
    fused_score: float
    source_kind: SourceKind
    matched_chunks: tuple[ChunkMatch, ...]
    deepening_used: bool = False
    deepening_evidence: tuple[DeepeningEvidence, ...] = ()


class QueryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    results: tuple[QueryResult, ...]
    trace: QueryTrace


DEFAULT_CLASSIFIER_SCORE: Final[int] = 5
