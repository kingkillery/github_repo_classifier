from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ghrepo_search.models import Origin, RepoRecord

_REPO_RE: Final[re.Pattern[str]] = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$")
type RepoJsonValue = str | int | bool | None | dict[str, str | int | bool | None] | list[str] | list[dict[str, str]]
type RawRepoPayload = dict[str, RepoJsonValue]


@dataclass(frozen=True, slots=True)
class InventoryWriteError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class _BranchRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = "main"


class _Language(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = ""


class _Topic(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str


class _LicenseInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    spdx_id: str = Field(default="", alias="spdxId")
    name: str = ""


class OwnedRepoPayload(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name_with_owner: str | None = Field(default="", alias="nameWithOwner")
    url: str
    description: str | None = ""
    default_branch_ref: _BranchRef | None = Field(default=None, alias="defaultBranchRef")
    is_private: bool | None = Field(default=False, alias="isPrivate")
    primary_language: _Language | None = Field(default=None, alias="primaryLanguage")
    stargazer_count: int | None = Field(default=0, alias="stargazerCount")
    fork_count: int | None = Field(default=0, alias="forkCount")
    repository_topics: tuple[_Topic, ...] | None = Field(default=None, alias="repositoryTopics")
    pushed_at: str | None = Field(default="", alias="pushedAt")
    license_info: _LicenseInfo | None = Field(default=None, alias="licenseInfo")


class StarredRepoPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    full_name: str | None = ""
    html_url: str
    description: str | None = ""
    default_branch: str | None = "main"
    private: bool | None = False
    language: str | None = ""
    stargazers_count: int | None = 0
    forks_count: int | None = 0
    topics: tuple[str, ...] | None = None
    pushed_at: str | None = ""
    license: _LicenseInfo | None = None

def _name_from_url(url: str) -> tuple[str, str]:
    match = _REPO_RE.match(url)
    if match is None:
        raise InventoryWriteError(message=f"invalid GitHub repository URL: {url}")
    return match.group("owner").lower(), match.group("name").lower()


def _repo_from_owned(payload: RawRepoPayload) -> RepoRecord:
    try:
        parsed = OwnedRepoPayload.model_validate(payload)
    except ValidationError as exc:
        raise InventoryWriteError(message=f"invalid GitHub repository payload: {exc}") from exc
    owner, name = _name_from_url(parsed.url)
    full_name = parsed.name_with_owner.lower() if parsed.name_with_owner else f"{owner}/{name}"
    branch = parsed.default_branch_ref.name if parsed.default_branch_ref is not None else "main"
    language = parsed.primary_language.name if parsed.primary_language is not None else ""
    license_name = ""
    if parsed.license_info is not None:
        license_name = parsed.license_info.spdx_id or parsed.license_info.name
    return RepoRecord(
        full_name=full_name,
        owner=owner,
        name=name,
        url=parsed.url,
        origins=frozenset({Origin.OWNED}),
        description=parsed.description or "",
        default_branch=branch,
        visibility="private" if parsed.is_private else "public",
        language=language,
        stars=parsed.stargazer_count or 0,
        forks=parsed.fork_count or 0,
        topics=tuple(topic.name for topic in parsed.repository_topics) if parsed.repository_topics is not None else (),
        pushed_at=parsed.pushed_at or "",
    )


def _repo_from_starred(payload: RawRepoPayload) -> RepoRecord:
    try:
        parsed = StarredRepoPayload.model_validate(payload)
    except ValidationError as exc:
        raise InventoryWriteError(message=f"invalid GitHub starred payload: {exc}") from exc
    owner, name = _name_from_url(parsed.html_url)
    full_name = parsed.full_name.lower() if parsed.full_name else f"{owner}/{name}"
    license_name = ""
    if parsed.license is not None:
        license_name = parsed.license.spdx_id or parsed.license.name
    return RepoRecord(
        full_name=full_name,
        owner=owner,
        name=name,
        url=parsed.html_url,
        origins=frozenset({Origin.STARRED}),
        description=parsed.description or "",
        default_branch=parsed.default_branch or "main",
        visibility="private" if parsed.private else "public",
        language=parsed.language or "",
        stars=parsed.stargazers_count or 0,
        forks=parsed.forks_count or 0,
        topics=parsed.topics or (),
        pushed_at=parsed.pushed_at or "",
        license=license_name,
    )


def _merge(left: RepoRecord, right: RepoRecord) -> RepoRecord:
    return left.model_copy(
        update={
            "origins": left.origins | right.origins,
            "description": left.description or right.description,
            "language": left.language or right.language,
            "stars": max(left.stars, right.stars),
            "forks": max(left.forks, right.forks),
            "topics": tuple(sorted(set(left.topics) | set(right.topics))),
            "pushed_at": max(left.pushed_at, right.pushed_at),
            "license": left.license or right.license,
        }
    )


def build_inventory(*, owned: list[RawRepoPayload], starred: list[RawRepoPayload]) -> list[RepoRecord]:
    records: dict[str, RepoRecord] = {}
    for repo in [_repo_from_owned(item) for item in owned] + [_repo_from_starred(item) for item in starred]:
        existing = records.get(repo.full_name)
        records[repo.full_name] = repo if existing is None else _merge(existing, repo)
    return [records[key] for key in sorted(records)]


def write_manifest(path: Path, records: list[RepoRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [json.loads(record.model_dump_json()) for record in records]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(data, tmp, indent=2)
        temp_path = Path(tmp.name)
    temp_path.replace(path)


def read_manifest(path: Path) -> list[RepoRecord]:
    return [RepoRecord.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
