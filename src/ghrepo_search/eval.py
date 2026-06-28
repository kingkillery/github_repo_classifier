from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ghrepo_search.search import QueryEngine, QueryRequest


class MissKind(StrEnum):
    INVENTORY_MISS = "inventory_miss"
    FETCH_MISS = "fetch_miss"
    NORMALIZE_MISS = "normalize_miss"
    LEXICAL_MISS = "lexical_miss"
    VECTOR_MISS = "vector_miss"
    FUSION_MISS = "fusion_miss"
    DEEPENING_MISS = "deepening_miss"
    FRESHNESS_MISS = "freshness_miss"


class GoldenQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    expected_repo: str
    expected_miss: MissKind | None = None


class EvalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    expected_repo: str
    found_repo: str
    passed: bool
    miss_kind: MissKind | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    results: tuple[EvalResult, ...]


def _classify_miss(query: GoldenQuery, found_repo: str) -> MissKind:
    if query.expected_miss is not None:
        return query.expected_miss
    if found_repo == "":
        return MissKind.FETCH_MISS
    return MissKind.FUSION_MISS


def run_eval(engine: QueryEngine, queries: list[GoldenQuery]) -> EvalReport:
    results: list[EvalResult] = []
    for query in queries:
        response = engine.query(QueryRequest(text=query.text))
        found = response.results[0].repo_full_name if response.results else ""
        passed = found == query.expected_repo
        miss = None if passed else _classify_miss(query, found)
        results.append(EvalResult(text=query.text, expected_repo=query.expected_repo, found_repo=found, passed=passed, miss_kind=miss))
    return EvalReport(passed=all(result.passed for result in results), results=tuple(results))


def read_golden_queries(path: Path) -> list[GoldenQuery]:
    return [GoldenQuery.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def write_eval_report(path: Path, report: EvalReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
