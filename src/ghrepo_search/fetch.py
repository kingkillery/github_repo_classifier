from __future__ import annotations

import base64
import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, assert_never

from ghrepo_search.models import DocumentRecord, FetchMiss, FetchMissKind, FetchResult, RepoRecord, SourceKind

DOC_CANDIDATES: tuple[str, ...] = (
    "README.md",
    "README.rst",
    "README.txt",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "docs/index.md",
    "docs/index.rst",
    "docs/index.txt",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def source_kind_for_path(path: str) -> SourceKind:
    normalized = path.lower()
    if normalized.startswith("readme"):
        return SourceKind.README
    if normalized == "agents.md":
        return SourceKind.AGENTS
    if normalized == "claude.md":
        return SourceKind.CLAUDE
    if normalized == "contributing.md":
        return SourceKind.CONTRIBUTING
    if normalized.startswith("docs/index"):
        return SourceKind.DOCS_INDEX
    if normalized in {"package.json", "pyproject.toml", "cargo.toml", "go.mod"}:
        return SourceKind.PACKAGE
    return SourceKind.RAW


@dataclass(frozen=True, slots=True)
class FetchedFile:
    path: str
    content: str


class ContentProvider(Protocol):
    def fetch_file(self, repo: str, path: str) -> FetchedFile | FetchMiss: ...


@dataclass(slots=True)  # noqa: MUTABLE_OK
class FixtureContentProvider:
    files: dict[tuple[str, str], str]
    fetch_log: list[str] = field(default_factory=list)

    @classmethod
    def from_directory(cls, repo: str, root: Path, extra_paths: set[str]) -> FixtureContentProvider:
        files: dict[tuple[str, str], str] = {}
        for path in extra_paths:
            file_path = root / path
            if file_path.exists():
                files[(repo, path)] = file_path.read_text(encoding="utf-8")
        return cls(files=files)

    def fetch_file(self, repo: str, path: str) -> FetchedFile | FetchMiss:
        self.fetch_log.append(path)
        content = self.files.get((repo, path))
        if content is None:
            return FetchMiss(repo_full_name=repo, path=path, kind=FetchMissKind.NOT_FOUND)
        return FetchedFile(path=path, content=content)


@dataclass(frozen=True, slots=True)
class GhContentProvider:
    def fetch_file(self, repo: str, path: str) -> FetchedFile | FetchMiss:
        endpoint = f"repos/{repo}/contents/{path}"
        try:
            completed = subprocess.run(
                ["gh", "api", endpoint, "--jq", ".content"],
                check=True,
                capture_output=True,
                encoding="utf-8",
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.lower()
            kind = _classify_gh_error(stderr)
            return FetchMiss(repo_full_name=repo, path=path, kind=kind, message=exc.stderr.strip())
        encoded = completed.stdout.strip().replace("\n", "")
        content = base64.b64decode(encoded).decode("utf-8")
        return FetchedFile(path=path, content=content)


def _classify_gh_error(stderr: str) -> FetchMissKind:
    if "not found" in stderr or "404" in stderr:
        return FetchMissKind.NOT_FOUND
    if "rate limit" in stderr or "403" in stderr:
        return FetchMissKind.RATE_LIMIT
    if "too large" in stderr or "100 mb" in stderr:
        return FetchMissKind.FILE_TOO_LARGE
    if "auth" in stderr or "401" in stderr:
        return FetchMissKind.AUTH
    return FetchMissKind.API_ERROR


def _doc_from_file(repo: RepoRecord, fetched: FetchedFile) -> DocumentRecord:
    return DocumentRecord(
        repo_full_name=repo.full_name,
        path=fetched.path,
        source_kind=source_kind_for_path(fetched.path),
        content=fetched.content,
        trusted=False,
        content_hash=content_hash(fetched.content),
    )


def fetch_first_stage_docs(repo: RepoRecord, provider: ContentProvider) -> FetchResult:
    documents: list[DocumentRecord] = []
    misses: list[FetchMiss] = []
    metadata = repo.model_dump_json()
    documents.append(
        DocumentRecord(
            repo_full_name=repo.full_name,
            path="__metadata__.json",
            source_kind=SourceKind.METADATA,
            content=metadata,
            trusted=False,
            content_hash=content_hash(metadata),
        )
    )
    for path in DOC_CANDIDATES:
        match provider.fetch_file(repo.full_name, path):
            case FetchedFile() as fetched:
                documents.append(_doc_from_file(repo, fetched))
            case FetchMiss() as miss:
                misses.append(miss)
            case unreachable:
                assert_never(unreachable)
    return FetchResult(repo=repo, documents=tuple(documents), misses=tuple(misses))
