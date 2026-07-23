"""Discovery and lifecycle helpers for imported MediaWiki XML sources.

An XML import exists before any LLM-generated wiki cache does.  Keeping this
small registry derived from the source manifests makes imports durable across
browser reloads without introducing a second database that can drift out of
sync with the Markdown tree on disk.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from api.data_root import get_data_root
from api.web_crawler.site_store import read_site_meta, website_local_dir


def _source_id(start_url: str) -> str:
    digest = hashlib.sha256(start_url.encode("utf-8")).hexdigest()[:16]
    return f"fanwiki-source-{digest}"


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
    wiki_name = str(meta.get("wiki_name") or "").strip()
    return {
        "id": _source_id(start_url),
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


def _sources() -> List[Tuple[str, Dict]]:
    repos_dir = os.path.join(get_data_root(), "repos")
    if not os.path.isdir(repos_dir):
        return []

    sources: List[Tuple[str, Dict]] = []
    for name in os.listdir(repos_dir):
        local_dir = os.path.join(repos_dir, name)
        if not os.path.isdir(local_dir):
            continue
        meta = read_site_meta(local_dir)
        if not meta or not _is_fanwiki_manifest(meta) or not meta.get("start_url"):
            continue
        sources.append((local_dir, meta))
    return sources


def list_all() -> List[Dict]:
    entries = [_entry_from_manifest(local_dir, meta) for local_dir, meta in _sources()]
    entries.sort(key=lambda entry: entry["submittedAt"], reverse=True)
    return entries


def _find(entry_id: str) -> Optional[Tuple[str, Dict]]:
    for local_dir, meta in _sources():
        if _source_id(str(meta.get("start_url") or "").strip()) == entry_id:
            return local_dir, meta
    return None


def get(entry_id: str) -> Optional[Dict]:
    source = _find(entry_id)
    if source is None:
        return None
    local_dir, meta = source
    entry = _entry_from_manifest(local_dir, meta)
    pages = meta.get("pages") if isinstance(meta.get("pages"), list) else []
    main_page = next(
        (
            page for page in pages
            if isinstance(page, dict)
            and str(page.get("relpath") or "").casefold() == "wiki/main_page.md"
        ),
        next((page for page in pages if isinstance(page, dict)), None),
    )
    entry.update({
        "description": f"Imported MediaWiki XML source for {entry['name']}",
        "main_page_path": str(main_page.get("relpath") or "") if main_page else None,
    })
    return entry


def get_by_start_url(start_url: str) -> Optional[Dict]:
    normalized = start_url.strip()
    for local_dir, meta in _sources():
        if str(meta.get("start_url") or "").strip() == normalized:
            return _entry_from_manifest(local_dir, meta)
    return None


def page_index(entry_id: str, offset: int = 0, limit: int = 500) -> Dict:
    source = _find(entry_id)
    if source is None:
        raise KeyError(entry_id)
    _, meta = source
    pages = [
        {
            "path": str(page.get("relpath") or ""),
            "title": str(page.get("title") or page.get("relpath") or ""),
            "url": str(page.get("url") or ""),
            "categories": list(page.get("categories") or []),
        }
        for page in (meta.get("pages") or [])
        if isinstance(page, dict) and page.get("relpath")
    ]
    total = len(pages)
    return {
        "entries": pages[offset:offset + limit],
        "offset": offset,
        "truncated": offset + limit < total,
        "totalArticles": total,
    }


def search(entry_id: str, query: str, limit: int = 30) -> List[Dict]:
    source = _find(entry_id)
    if source is None:
        raise KeyError(entry_id)
    _, meta = source
    needle = query.strip().casefold()
    if not needle:
        return []
    matches = []
    for position, page in enumerate(meta.get("pages") or []):
        if not isinstance(page, dict) or not page.get("relpath"):
            continue
        title = str(page.get("title") or page.get("relpath") or "")
        categories = [str(value) for value in (page.get("categories") or [])]
        searchable = " ".join((title, str(page.get("url") or ""), *categories)).casefold()
        if needle not in searchable:
            continue
        folded_title = title.casefold()
        rank = 0 if folded_title == needle else 1 if folded_title.startswith(needle) else 2
        matches.append((
            rank,
            position,
            {
                "path": str(page["relpath"]),
                "title": title,
                "url": str(page.get("url") or ""),
                "categories": categories,
            },
        ))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in matches[:limit]]


def _reader_markdown(content: str) -> str:
    """Remove MediaWiki layout scaffolding that has no meaning in Markdown.

    XML dumps often contain homepage-only table/layout syntax and inputbox
    controls. The importer deliberately preserves their useful cell text, but
    showing raw ``{|``, ``|-`` and ``style=...`` tokens makes the direct
    reader look broken. This presentation pass is non-destructive (the source
    Markdown on disk remains untouched for RAG/export).
    """
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    content = re.sub(r"<inputbox\b[^>]*>.*?</inputbox>", "", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"</?mainpage[-\w]*\s*/?>", "", content, flags=re.IGNORECASE)
    content = re.sub(
        r"<h([1-6])\b[^>]*>(.*?)</h\1>",
        lambda match: f"\n{'#' * int(match.group(1))} {match.group(2).strip()}\n",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"</?(?:center|small|div)\b[^>]*>", "", content, flags=re.IGNORECASE)
    lines: List[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("{|") or stripped == "|}" or stripped.startswith("|-"):
            continue
        line = raw_line
        if stripped.startswith(("|", "!")):
            cell = stripped[1:].strip()
            if not cell:
                continue
            if "|" in cell:
                attributes, value = cell.split("|", 1)
                if "=" in attributes:
                    cell = value.strip()
            if not cell:
                continue
            line = cell
        # MediaWiki level-one headings are valid in article bodies but the
        # original converter handled only levels 2-6.
        heading = re.match(r"^=\s*(.+?)\s*=$", line.strip())
        if heading:
            line = f"# {heading.group(1)}"
        if line.strip() == "----":
            # Markdown horizontal rules need whitespace around them or the
            # following paragraph can be parsed as literal markup.
            lines.extend(("", "---", ""))
            continue
        if line.lstrip().startswith("*") and not (
            line.strip().endswith("*") and line.strip().count("*") == 2
        ):
            line = re.sub(r"^(\s*)\*(?=\S)", r"\1* ", line)
        line = line.replace("'''", "**")
        if line.strip().startswith("**") and line.count("**") == 1:
            line = line.rstrip() + "**"
        # External MediaWiki links use `[URL label]`, while Markdown expects
        # `[label](URL)`.
        line = re.sub(
            r"\[(https?://[^\s\]]+)\s+([^\]]+)\]",
            lambda match: f"[{match.group(2)}]({match.group(1)})",
            line,
        )
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def read_page(entry_id: str, relpath: str) -> Dict:
    source = _find(entry_id)
    if source is None:
        raise KeyError(entry_id)
    local_dir, meta = source
    page = next(
        (
            candidate for candidate in (meta.get("pages") or [])
            if isinstance(candidate, dict)
            and str(candidate.get("relpath") or "") == relpath
        ),
        None,
    )
    if page is None:
        raise FileNotFoundError(relpath)
    full_path = os.path.join(local_dir, relpath.replace("/", os.sep))
    with open(full_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    # The source files use the crawler's small YAML header. It is useful to
    # RAG/indexing, but it should not appear as a horizontal-rule block in the
    # reader itself.
    content = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n+", "", content, count=1, flags=re.DOTALL)
    content = _reader_markdown(content)
    return {
        "path": relpath,
        "title": str(page.get("title") or relpath),
        "url": str(page.get("url") or ""),
        "categories": list(page.get("categories") or []),
        "content": content,
    }


def resolve_asset(entry_id: str, relpath: str) -> str:
    source = _find(entry_id)
    if source is None:
        raise KeyError(entry_id)
    local_dir, _ = source
    base = os.path.realpath(local_dir)
    candidate = os.path.realpath(os.path.join(base, relpath.replace("/", os.sep)))
    if os.path.commonpath((base, candidate)) != base or not os.path.isfile(candidate):
        raise FileNotFoundError(relpath)
    if candidate.lower().endswith((".md", ".json")):
        raise FileNotFoundError(relpath)
    return candidate


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
