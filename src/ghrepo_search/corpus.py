from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ghrepo_search.models import CorpusChunk, DocumentRecord


def _heading_for(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    title = stripped.lstrip("#").strip()
    return title or None


def _split_text(text: str, target_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if current == "" else f"{current}\n\n{paragraph}"
        if len(candidate) <= target_chars or current == "":
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _chunk_id(document: DocumentRecord, ordinal: int, text: str) -> str:
    raw = f"{document.repo_full_name}\0{document.path}\0{ordinal}\0{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _document_heading(document: DocumentRecord) -> str:
    for line in document.content.splitlines():
        heading = _heading_for(line)
        if heading is not None:
            return heading
    return document.path


def chunk_documents(documents: tuple[DocumentRecord, ...], target_chars: int = 900) -> tuple[CorpusChunk, ...]:
    chunks: list[CorpusChunk] = []
    for document in documents:
        heading = _document_heading(document)
        for ordinal, text in enumerate(_split_text(document.content, target_chars)):
            chunks.append(
                CorpusChunk(
                    chunk_id=_chunk_id(document, ordinal, text),
                    repo_full_name=document.repo_full_name,
                    path=document.path,
                    source_kind=document.source_kind,
                    heading=heading,
                    text=text,
                    trusted=document.trusted,
                    content_hash=document.content_hash,
                    ordinal=ordinal,
                )
            )
    return tuple(chunks)


def write_chunks(path: Path, chunks: tuple[CorpusChunk, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([json.loads(chunk.model_dump_json()) for chunk in chunks], indent=2), encoding="utf-8")


def read_chunks(path: Path) -> tuple[CorpusChunk, ...]:
    return tuple(CorpusChunk.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8")))


def write_documents(path: Path, documents: tuple[DocumentRecord, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([json.loads(doc.model_dump_json()) for doc in documents], indent=2), encoding="utf-8")


def read_documents(path: Path) -> tuple[DocumentRecord, ...]:
    return tuple(DocumentRecord.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8")))
