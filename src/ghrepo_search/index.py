from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ghrepo_search.models import CorpusChunk, Origin, RepoRecord, SourceKind

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_SYNONYMS: Final[dict[str, tuple[str, ...]]] = {
    "docs": ("document", "documentation"),
    "doc": ("document", "documentation"),
    "extract": ("extraction", "parser", "parse"),
    "extracting": ("extraction", "parser", "parse"),
    "tool": ("package", "library"),
    "tools": ("package", "library"),
}


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: CorpusChunk
    repo: RepoRecord
    score: float
    rank: int


def tokenize(text: str) -> frozenset[str]:
    terms = set(_TOKEN_RE.findall(text.lower()))
    expanded = set(terms)
    for term in terms:
        expanded.update(_SYNONYMS.get(term, ()))
    return frozenset(expanded)


def _fts_query(text: str) -> str:
    terms = sorted(tokenize(text))
    return " OR ".join(terms)


def _origin_csv(origins: frozenset[Origin]) -> str:
    return ",".join(sorted(origin.value for origin in origins))


def _repo_from_row(row: tuple[str, str, str, str, str, str, int, int, str, str, str]) -> RepoRecord:
    topics = tuple(item for item in row[8].split(",") if item)
    origins = frozenset(Origin(item) for item in row[4].split(",") if item)
    return RepoRecord(
        full_name=row[0],
        owner=row[1],
        name=row[2],
        url=row[3],
        origins=origins,
        description=row[5],
        language=row[6],
        stars=row[7],
        topics=topics,
        pushed_at=row[9],
        license=row[10],
    )


class SearchIndex:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @classmethod
    def open(cls, db_path: Path) -> SearchIndex:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        index = cls(db_path)
        index._init_schema()
        return index

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS repos(full_name TEXT PRIMARY KEY, owner TEXT, name TEXT, url TEXT, origins TEXT, description TEXT, language TEXT, stars INTEGER, topics TEXT, pushed_at TEXT, license TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY, repo_full_name TEXT, path TEXT, source_kind TEXT, heading TEXT, text TEXT, trusted INTEGER, content_hash TEXT, ordinal INTEGER)")
            conn.execute("CREATE TABLE IF NOT EXISTS vectors(chunk_id TEXT PRIMARY KEY, terms_json TEXT, corpus_hash TEXT)")
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, repo_full_name UNINDEXED, path, heading, text)")

    def rebuild(self, repos: list[RepoRecord], chunks: tuple[CorpusChunk, ...]) -> None:
        corpus_hash = self.corpus_hash(chunks)
        with self._connect() as conn:
            conn.execute("DELETE FROM repos")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM vectors")
            conn.execute("DELETE FROM chunks_fts")
            for repo in repos:
                conn.execute(
                    "INSERT INTO repos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (repo.full_name, repo.owner, repo.name, repo.url, _origin_csv(repo.origins), repo.description, repo.language, repo.stars, ",".join(repo.topics), repo.pushed_at, repo.license),
                )
            for chunk in chunks:
                conn.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (chunk.chunk_id, chunk.repo_full_name, chunk.path, chunk.source_kind.value, chunk.heading, chunk.text, int(chunk.trusted), chunk.content_hash, chunk.ordinal),
                )
                conn.execute("INSERT INTO chunks_fts VALUES (?, ?, ?, ?, ?)", (chunk.chunk_id, chunk.repo_full_name, chunk.path, chunk.heading, chunk.text))
                conn.execute("INSERT INTO vectors VALUES (?, ?, ?)", (chunk.chunk_id, json.dumps(sorted(tokenize(chunk.text))), corpus_hash))

    @staticmethod
    def corpus_hash(chunks: tuple[CorpusChunk, ...]) -> str:
        return str(abs(hash(tuple((chunk.chunk_id, chunk.content_hash) for chunk in chunks))))

    def repos(self) -> dict[str, RepoRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT full_name, owner, name, url, origins, description, language, stars, topics, pushed_at, license FROM repos").fetchall()
        return {row[0]: _repo_from_row(row) for row in rows}

    def chunks_by_id(self) -> dict[str, CorpusChunk]:
        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_id, repo_full_name, path, source_kind, heading, text, trusted, content_hash, ordinal FROM chunks").fetchall()
        return {
            row[0]: CorpusChunk(
                chunk_id=row[0],
                repo_full_name=row[1],
                path=row[2],
                source_kind=SourceKind(row[3]),
                heading=row[4],
                text=row[5],
                trusted=bool(row[6]),
                content_hash=row[7],
                ordinal=row[8],
            )
            for row in rows
        }

    def lexical(self, text: str, limit: int) -> list[SearchHit]:
        query = _fts_query(text)
        if query == "":
            return []
        repos = self.repos()
        chunks = self.chunks_by_id()
        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_id, bm25(chunks_fts) AS score FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?", (query, limit)).fetchall()
        hits: list[SearchHit] = []
        for rank, row in enumerate(rows, start=1):
            chunk = chunks[row[0]]
            hits.append(SearchHit(chunk=chunk, repo=repos[chunk.repo_full_name], score=1 / (1 + abs(float(row[1]))), rank=rank))
        return hits

    def vector(self, text: str, limit: int) -> list[SearchHit]:
        query_terms = tokenize(text)
        if not query_terms:
            return []
        repos = self.repos()
        chunks = self.chunks_by_id()
        scored: list[SearchHit] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_id, terms_json FROM vectors").fetchall()
        for row in rows:
            terms = frozenset(json.loads(row[1]))
            overlap = len(query_terms & terms)
            if overlap == 0:
                continue
            score = overlap / math.sqrt(len(query_terms) * len(terms))
            chunk = chunks[row[0]]
            scored.append(SearchHit(chunk=chunk, repo=repos[chunk.repo_full_name], score=score, rank=0))
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return [SearchHit(chunk=hit.chunk, repo=hit.repo, score=hit.score, rank=rank) for rank, hit in enumerate(scored[:limit], start=1)]
