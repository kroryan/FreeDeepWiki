"""Discovery and lifecycle helpers for imported MediaWiki XML sources.

An XML import exists before any LLM-generated wiki cache does.  Keeping this
small registry derived from the source manifests makes imports durable across
browser reloads without introducing a second database that can drift out of
sync with the Markdown tree on disk.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse

from api.data_root import get_data_root
from api.web_crawler.site_store import read_site_meta, website_local_dir


def _is_fanwiki_manifest(meta: Dict) -> bool:
    if meta.get("source_type") == "fanwiki":
        return True
    # Compatibility with imports produced by the first fanwiki release,
    # before source_type was persisted. Imported pages always carried a
    # categories field; live crawler manifests do not.
    pages = meta.get("pages")
    return bool(
        isinstance(pages, list)
        and any(isinstance(page, dict) and "categories" in page for page in pages[:50])
    )


def _timestamp_ms(value: object, fallback_path: str) -> int:
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            pass
    try:
        return int(os.path.getmtime(fallback_path) * 1000)
    except OSError:
        return 0


def _entry_from_manifest(local_dir: str, meta: Dict) -> Dict:
    start_url = str(meta.get("start_url") or "").strip()
    host = urlparse(start_url).hostname or "import"
    digest = hashlib.sha256(start_url.encode("utf-8")).hexdigest()[:16]
    wiki_name = str(meta.get("wiki_name") or "").strip()
    return {
        "id": f"fanwiki-source-{digest}",
        "owner": "fanwiki",
        "repo": host,
        "name": wiki_name or f"Imported fanwiki: {host}",
        "repo_type": "fanwiki",
        "submittedAt": _timestamp_ms(meta.get("crawled_at"), local_dir),
        "language": "",
        "status": "imported",
        "start_url": start_url,
        "page_count": int(meta.get("page_count") or 0),
    }


def list_all() -> List[Dict]:
    repos_dir = os.path.join(get_data_root(), "repos")
    if not os.path.isdir(repos_dir):
        return []

    entries: List[Dict] = []
    for name in os.listdir(repos_dir):
        local_dir = os.path.join(repos_dir, name)
        if not os.path.isdir(local_dir):
            continue
        meta = read_site_meta(local_dir)
        if not meta or not _is_fanwiki_manifest(meta) or not meta.get("start_url"):
            continue
        entries.append(_entry_from_manifest(local_dir, meta))
    entries.sort(key=lambda entry: entry["submittedAt"], reverse=True)
    return entries


def delete(start_url: str) -> bool:
    """Delete only a verified fanwiki source tree and its embeddings cache."""
    local_dir = website_local_dir(start_url)
    meta = read_site_meta(local_dir)
    if not meta or not _is_fanwiki_manifest(meta):
        return False
    if str(meta.get("start_url") or "").strip() != start_url.strip():
        return False

    shutil.rmtree(local_dir)
    repo_name = os.path.basename(local_dir)
    database_path = os.path.join(get_data_root(), "databases", f"{repo_name}.pkl")
    try:
        os.remove(database_path)
    except FileNotFoundError:
        pass
    return True
