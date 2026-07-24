"""Shared wiki-cache path resolution (anti-duplication).

``api.api`` defines the wikicache directory + filename-prefix conventions and
uses them across ~15 read/write/version helpers. ``api.mcp_tools`` and
``api.storage.wiki_search`` ALSO need to locate caches (to search/read them),
and were re-declaring the same prefix strings independently -- which is
exactly the drift that once made mcp_tools look in the wrong layout
(nested vs flat) and find no wikis. This module is the single source of truth
for the on-disk layout, imported by all three.

Layout: caches live in ONE flat directory ``<data_root>/wikicache/`` as
``<prefix>_<repo_type>_<owner>_<repo>_<language>_<...>.json``. The current
prefix is ``hackdeepwiki_cache_``; the legacy ``freedeepwiki_cache_`` prefix
(pre-rename) is matched too so caches saved before the rename stay findable.

Lightweight: stdlib + api.data_root only, so mcp_tools (which must stay
importable without starting FastAPI) can import it freely.
"""

from __future__ import annotations

import os
from typing import List

from api.data_root import get_data_root

# Directory (flat -- NOT nested per owner/repo). Created on first use.
WIKI_CACHE_DIR = os.path.join(get_data_root(), "wikicache")
os.makedirs(WIKI_CACHE_DIR, exist_ok=True)

# Filename prefixes. ``hackdeepwiki_cache_`` for new writes; the legacy
# ``freedeepwiki_cache_`` is matched on read so pre-rename caches survive.
WIKI_CACHE_FILE_PREFIX = "hackdeepwiki_cache_"
LEGACY_WIKI_CACHE_FILE_PREFIX = "freedeepwiki_cache_"


def repo_cache_prefix(repo_type: str, owner: str, repo: str, language: str) -> str:
    """Filename prefix used for *new* cache writes for one repo/language/type."""
    return f"{WIKI_CACHE_FILE_PREFIX}{repo_type}_{owner}_{repo}_{language}"


def repo_cache_prefixes(repo_type: str, owner: str, repo: str, language: str) -> List[str]:
    """Every filename prefix that could hold a release of one
    repo/language/type -- current prefix first, then the pre-rename (legacy)
    prefix, so caches saved before the rename are still found/managed rather
    than silently orphaned."""
    return [
        repo_cache_prefix(repo_type, owner, repo, language),
        f"{LEGACY_WIKI_CACHE_FILE_PREFIX}{repo_type}_{owner}_{repo}_{language}",
    ]


def list_cache_files(repo_type: str, owner: str, repo: str, language: str) -> List[str]:
    """All cache .json files for one repo/language/type, newest-first. Matches
    both current and legacy prefixes. Centralizes the listdir+filter so
    api.api, mcp_tools, and wiki_search all agree on what's a cache file."""
    if not os.path.isdir(WIKI_CACHE_DIR):
        return []
    prefixes = tuple(repo_cache_prefixes(repo_type, owner, repo, language))
    files = [
        os.path.join(WIKI_CACHE_DIR, fn)
        for fn in os.listdir(WIKI_CACHE_DIR)
        if fn.endswith(".json") and fn.startswith(prefixes)
    ]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def load_latest_cache_json(owner: str, repo: str, repo_type: str, language: str):
    """Load the newest cache release as a plain dict, or None. Kept here (not
    in api.api) so mcp_tools/wiki_search can read a cache without importing
    the full FastAPI app + the WikiCacheData pydantic model."""
    import json
    for path in list_cache_files(repo_type, owner, repo, language):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001 - one unreadable file shouldn't block the next
            continue
    return None
