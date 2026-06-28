"""ghrepo_search: README/AGENTS-first hybrid search over GitHub repositories.

The public API grows incrementally as later lanes land inventory, fetch,
corpus, indexing, query, deepening, eval, and CLI modules. For now this module
only establishes the package root and version.

TRUST BOUNDARY (load-bearing):
    Every remote README, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, source file, or
    other fetched document is treated as UNTRUSTED CORPUS TEXT. Nothing fetched
    from a remote repository is ever executed, imported, or obeyed as a runtime
    instruction. Injection probes inside corpus text are stored verbatim as
    inert data and surfaced only through retrieval results.
"""

from __future__ import annotations

__all__: list[str] = ["__version__"]
__version__: str = "0.0.1"
