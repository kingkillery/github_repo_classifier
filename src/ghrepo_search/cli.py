from __future__ import annotations

import json
from pathlib import Path

import typer

from ghrepo_search.bucket import BucketConfig, HfCliSyncRunner, plan_bucket_sync, sync_bucket
from ghrepo_search.corpus import chunk_documents, read_chunks, read_documents, write_chunks, write_documents
from ghrepo_search.deepening import deepen_results
from ghrepo_search.eval import read_golden_queries, run_eval, write_eval_report
from ghrepo_search.export import export_classified_repos
from ghrepo_search.fetch import FixtureContentProvider, GhContentProvider, fetch_first_stage_docs
from ghrepo_search.index import SearchIndex
from ghrepo_search.inventory import RawRepoPayload, build_inventory, read_manifest, write_manifest
from ghrepo_search.search import QueryEngine, QueryRequest

app = typer.Typer(help="README/AGENTS-first hybrid search over owned and starred GitHub repositories.")


def _read_payloads(path: Path | None) -> list[RawRepoPayload]:
    if path is None:
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@app.command()
def inventory(
    owned_json: Path | None = typer.Option(None, help="JSON array from gh repo list."),
    starred_json: Path | None = typer.Option(None, help="JSON array from gh api user/starred."),
    output: Path = typer.Option(..., help="Manifest output path."),
) -> None:
    """Build canonical owned/starred repo manifest."""
    records = build_inventory(owned=_read_payloads(owned_json), starred=_read_payloads(starred_json))
    write_manifest(output, records)
    typer.echo(json.dumps({"repos": len(records), "output": str(output)}))


@app.command()
def fetch(
    manifest: Path = typer.Option(...),
    output: Path = typer.Option(...),
    fixture_docs_dir: Path | None = typer.Option(None),
) -> None:
    """Fetch metadata and high-signal docs without cloning."""
    repos = read_manifest(manifest)
    documents = []
    for repo in repos:
        provider = GhContentProvider() if fixture_docs_dir is None else FixtureContentProvider.from_directory(repo.full_name, fixture_docs_dir, {"README.md", "AGENTS.md"})
        fetched = fetch_first_stage_docs(repo, provider)
        documents.extend(fetched.documents)
    write_documents(output, tuple(documents))
    typer.echo(json.dumps({"documents": len(documents), "output": str(output)}))


@app.command()
def corpus(docs: Path = typer.Option(...), output: Path = typer.Option(...)) -> None:
    """Normalize fetched docs into searchable chunks."""
    chunks = chunk_documents(read_documents(docs))
    write_chunks(output, chunks)
    typer.echo(json.dumps({"chunks": len(chunks), "output": str(output)}))


@app.command("index")
def index_command(manifest: Path = typer.Option(...), chunks: Path = typer.Option(...), db: Path = typer.Option(...)) -> None:
    """Build lexical and local vector indexes."""
    parsed_chunks = read_chunks(chunks)
    SearchIndex.open(db).rebuild(read_manifest(manifest), parsed_chunks)
    typer.echo(json.dumps({"chunks": len(parsed_chunks), "db": str(db)}))


@app.command()
def query(db: Path = typer.Option(...), text: str = typer.Argument(...)) -> None:
    """Run traceable hybrid search."""
    response = QueryEngine(SearchIndex.open(db)).query(QueryRequest(text=text))
    typer.echo(response.model_dump_json())


@app.command()
def deepen(db: Path = typer.Option(...), text: str = typer.Argument(...), fixture_docs_dir: Path = typer.Option(...), path: list[str] | None = typer.Option(None)) -> None:
    """Run query with explicit raw-file deepening."""
    engine = QueryEngine(SearchIndex.open(db))
    request = QueryRequest(text=text, deepen=True, deepening_paths=tuple(path or ()))
    response = engine.query(request)
    repo_name = response.results[0].repo_full_name if response.results else ""
    provider = FixtureContentProvider.from_directory(repo_name, fixture_docs_dir, set(path or ()))
    typer.echo(deepen_results(response, provider).model_dump_json())


@app.command("sync-bucket")
def sync_bucket_command(
    local_root: Path = typer.Option(...),
    bucket_uri: str = typer.Option(...),
    apply: bool = typer.Option(False, "--apply", help="Actually call hf buckets sync."),
) -> None:
    """Plan or apply optional private Hugging Face bucket sync."""
    config = BucketConfig(bucket_uri=bucket_uri, local_root=local_root)
    if apply:
        result = sync_bucket(config, apply=True, runner=HfCliSyncRunner())
        payload = {
            "bucket_uri": result.plan.bucket_uri,
            "applied": result.applied,
            "objects": [{"relative_path": item.relative_path, "size_bytes": item.size_bytes} for item in result.plan.objects],
        }
    else:
        plan = plan_bucket_sync(config)
        payload = {
            "bucket_uri": plan.bucket_uri,
            "applied": False,
            "objects": [{"relative_path": item.relative_path, "size_bytes": item.size_bytes} for item in plan.objects],
        }
    typer.echo(json.dumps(payload))


@app.command("eval")
def eval_command(db: Path = typer.Option(...), golden: Path = typer.Option(...), output: Path = typer.Option(...)) -> None:
    """Run golden-query evaluation and write miss taxonomy report."""
    report = run_eval(QueryEngine(SearchIndex.open(db)), read_golden_queries(golden))
    write_eval_report(output, report)
    typer.echo(report.model_dump_json())
    if not report.passed:
        raise typer.Exit(1)


@app.command("export")
def export_command(manifest: Path = typer.Option(...), chunks: Path = typer.Option(...), output: Path = typer.Option(...)) -> None:
    """Export compatibility JSON for visualize.py."""
    export_classified_repos(read_manifest(manifest), read_chunks(chunks), output)
    typer.echo(json.dumps({"output": str(output)}))
