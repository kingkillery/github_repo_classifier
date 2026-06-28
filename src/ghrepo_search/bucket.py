from __future__ import annotations

from dataclasses import dataclass, field
import subprocess
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BucketConfig:
    bucket_uri: str
    local_root: Path


@dataclass(frozen=True, slots=True)
class BucketObject:
    relative_path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BucketSyncPlan:
    bucket_uri: str
    objects: tuple[BucketObject, ...]


@dataclass(frozen=True, slots=True)
class BucketSyncResult:
    plan: BucketSyncPlan
    applied: bool


@dataclass(frozen=True, slots=True)
class BucketConfigError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class HfCliSyncRunner:
    def sync(self, local_root: Path, bucket_uri: str) -> None:
        subprocess.run(["hf", "buckets", "sync", str(local_root), bucket_uri], check=True)

class SyncRunner(Protocol):
    def sync(self, local_root: Path, bucket_uri: str) -> None: ...


@dataclass(slots=True)  # noqa: MUTABLE_OK
class RecordingSyncRunner:
    calls: list[tuple[Path, str]] = field(default_factory=list)

    def sync(self, local_root: Path, bucket_uri: str) -> None:
        self.calls.append((local_root, bucket_uri))


def plan_bucket_sync(config: BucketConfig) -> BucketSyncPlan:
    if config.bucket_uri == "":
        raise BucketConfigError(message="missing private Hugging Face bucket URI")
    if not config.local_root.exists():
        raise BucketConfigError(message=f"missing local artifact root: {config.local_root}")
    objects = tuple(
        BucketObject(relative_path=str(path.relative_to(config.local_root)).replace("\\", "/"), size_bytes=path.stat().st_size)
        for path in sorted(config.local_root.rglob("*"))
        if path.is_file()
    )
    return BucketSyncPlan(bucket_uri=config.bucket_uri, objects=objects)


def sync_bucket(config: BucketConfig, *, apply: bool, runner: SyncRunner) -> BucketSyncResult:
    plan = plan_bucket_sync(config)
    if apply:
        runner.sync(config.local_root, config.bucket_uri)
    return BucketSyncResult(plan=plan, applied=apply)
