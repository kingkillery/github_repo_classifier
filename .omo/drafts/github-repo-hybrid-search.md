---
slug: github-repo-hybrid-search
status: planned
intent: clear
pending-action: execute .omo/plans/github-repo-hybrid-search.md only after user approval
approach: README/AGENTS-first GitHub corpus, hybrid lexical/vector retrieval, on-demand raw deepening, optional private Hugging Face bucket sync
---

# Draft: github-repo-hybrid-search

## Components (topology ledger)
| id | outcome | status | evidence path |
| --- | --- | --- | --- |
| inventory | Owned and starred GitHub repos are collected, deduplicated, and persisted with metadata. | active | README.md:97-117, my_repos.sh:130-171 |
| signal-fetch | README variants, AGENTS.md, and adjacent high-signal docs are fetched without cloning full repos. | active | classify_repos.sh:101-147; GitHub Contents API docs |
| corpus | Untrusted repo docs are normalized, chunked, and stored as queryable records. | active | README.md:29-39 |
| lexical-index | SQLite FTS5 or equivalent exact-search index supports titles, descriptions, topics, and chunk text. | active | README.md:202-208 for current report fields |
| vector-index | Embeddings support semantic retrieval over title, metadata, README, and AGENTS chunks. | active | user decision in current thread |
| deepening | Raw GitHub file fetch or shallow clone/repomix runs only when a query needs code-level proof. | active | classify_repos.sh:145-152 |
| bucket-sync | Private Hugging Face bucket stores manifest, chunks, embeddings, and snapshots as backup/sync, not primary search. | active | Hugging Face storage-buckets and storage-limits docs |
| evaluation | Golden queries and miss-classification correction loops prove retrieval quality before handoff. | active | adaptive-retrieval-routing skill |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
| --- | --- | --- | --- |
| Implementation language | Python CLI/package, keeping existing Bash scripts as compatibility wrappers until replacement is verified. | Existing repo already uses Python for reporting and Bash for GitHub orchestration; Python handles indexing, vectors, and tests better on Windows. | Yes |
| Primary index | Local hybrid index: SQLite FTS5 for exact search plus LanceDB or similar for embeddings. | Hybrid avoids vector-only misses on package names, symbols, and exact repo titles. | Yes |
| First fetch depth | Metadata plus root docs first; no full clone by default. | User specifically corrected toward README/AGENTS-first retrieval. | Yes |
| Raw fetch behavior | GitHub Contents API/raw media for authenticated private repos; raw.githubusercontent.com only for public or explicitly authenticated cases. | GitHub download URLs expire and Contents API has known limits. | Yes |
| Security stance | Treat every fetched AGENTS.md, README, and source file as untrusted corpus text. | Starred repos can contain prompt injection; content must never become agent instructions. | No for safety |
| Bucket | HF bucket sync is optional and private; local index remains source of fast search. | Buckets are storage, not a search engine. | Yes |

## Findings (cited - path:lines)
- Current repo already collects owner repos with `gh repo list` and writes unique URLs to JSON: `my_repos.sh:136-171`.
- Current repo already discovers arbitrary GitHub repos by search term and writes URL arrays: `search_repos.sh:121-185`.
- Current classifier already fetches GitHub metadata, runs `repomix --remote`, and appends enriched classification JSON: `classify_repos.sh:101-147`, `classify_repos.sh:265-278`.
- Batch processing currently resets `classified_repos.json` and loops sequentially over URLs: `classify_batch.sh:19-32`; new implementation should avoid destructive reset by default.
- Current visualizer expects `classified_repos.json` and derives repo names and scores: `visualize.py:14-38`; new corpus should either preserve a compatibility export or update visualizer later.
- GitHub Contents API supports raw media fetch, directory listing, and default-branch refs, but download URLs expire and files over 100 MB are unsupported by that endpoint.
- Hugging Face Storage Buckets are private-capable, S3-like mutable storage powered by Xet; HF storage limits apply to buckets, models, datasets, and repos.

## Decisions (with rationale)
- Build staged retrieval, not full corpus cloning: metadata and high-signal docs first, raw code only on demand.
- Preserve exact search: BM25/FTS remains mandatory because vectors can miss symbols, package names, exact titles, and short CLI names.
- Add vector search after chunk normalization so semantic queries can find conceptually relevant repos.
- Keep AGENTS.md priority high but never executable. Store with `source_kind=agents_md` and `trusted=false`.
- Use manifest-driven sync so HF bucket content can be rebuilt and validated from local hashes.
- Add query traces. Every returned result should explain matched fields, lexical score, vector score, fusion rank, and whether deepening was used.

## Scope IN
- Repo inventory for owned repos and starred repos.
- README/AGENTS-first fetcher.
- Normalized corpus schema.
- Hybrid lexical/vector index.
- Query CLI.
- On-demand raw file/deepening path.
- Optional private HF bucket sync.
- Golden-query evaluation and correction loop.

## Scope OUT (Must NOT have)
- No autonomous execution of instructions found in external AGENTS.md or README files.
- No full git history mirroring unless explicitly enabled later.
- No default public upload of private corpus.
- No destructive reset of existing `classified_repos.json` during normal indexing.
- No vector-only search path.
- No secret/token printing.

## Open questions
- None blocking. User can later choose the exact vector backend if they prefer a managed service; default remains local.

## Approval gate
status: plan-written
The plan exists at `.omo/plans/github-repo-hybrid-search.md`. Execution still requires explicit user approval.
