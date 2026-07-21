"""Persists crawled pages as a local Markdown tree that mirrors the site's
URL structure, and resolves that tree's location using the same
``<data_root>/repos/<name>`` convention the git-repo pipeline uses (see
``api.data_pipeline._local_clone_dir``) -- so a crawled site can be handed to
the exact same wiki-generation code path (file tree walk, RAG indexing, page
citation) as a cloned git repo, just under ``repo_type == "website"``.

Layout for ``https://example.com``:

    <data_root>/repos/website_example.com/
        index.md                  <- https://example.com/
        blog/post-1.md            <- https://example.com/blog/post-1
        blog/post-1/comments.md   <- disambiguated when both a page and a
                                      "directory" of it exist (see _safe_path)
        _site_meta.json           <- crawl manifest (url list, timestamps,
                                      user-content flags) read back by the
                                      category-split step in wiki generation

Each page file carries a YAML front-matter header:

    ---
    url: https://example.com/blog/post-1
    title: Post title
    likely_user_content: false
    ---
    <markdown body>
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urlparse

from api.data_root import get_data_root
from api.web_crawler.models import CrawlPage

_SITE_META_FILENAME = "_site_meta.json"
_INVALID_SEGMENT_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def website_repo_name(start_url: str) -> str:
    netloc = urlparse(start_url).netloc or start_url
    netloc = netloc.split(":")[0]  # drop a port if present
    safe = _INVALID_SEGMENT_CHARS.sub("_", netloc)
    return f"website_{safe}"


def website_local_dir(start_url: str) -> str:
    root_path = get_data_root()
    return os.path.join(root_path, "repos", website_repo_name(start_url))


def _safe_segment(segment: str) -> str:
    segment = _INVALID_SEGMENT_CHARS.sub("_", segment)
    return segment or "_"


def page_to_relpath(page: CrawlPage) -> str:
    """URL path -> relative .md file path, mirroring the site's structure.

    "/" and "/blog/" become "index.md" and "blog/index.md" (a directory's
    own page). Query strings that meaningfully change content (?page=2) are
    folded into the filename so paginated listings don't collide into one
    file; a bare "?" with no query is ignored.
    """
    path = page.path.strip("/")
    query_suffix = ""
    if "?" in page.url:
        q = page.url.split("?", 1)[1]
        if q:
            safe_q = _INVALID_SEGMENT_CHARS.sub("_", q)[:60]
            query_suffix = f"__q_{safe_q}"

    if not path:
        return f"index{query_suffix}.md" if query_suffix else "index.md"

    segments = [_safe_segment(s) for s in path.split("/") if s]
    base = segments[-1]
    dir_segments = segments[:-1]
    filename = f"{base}{query_suffix}.md"
    return os.path.join(*dir_segments, filename) if dir_segments else filename


def _front_matter(page: CrawlPage) -> str:
    # Minimal hand-rolled YAML -- values are escaped enough for URLs/titles
    # (no embedded newlines expected from either), avoiding a yaml dependency
    # for three scalar fields.
    title = page.title.replace('"', "'").replace("\n", " ").strip()
    return (
        "---\n"
        f'url: "{page.url}"\n'
        f'title: "{title}"\n'
        f"likely_user_content: {str(page.likely_user_content).lower()}\n"
        f"depth: {page.depth}\n"
        "---\n\n"
    )


def write_page(local_dir: str, page: CrawlPage) -> str:
    """Write one crawled page to disk and return the relative path written."""
    relpath = page_to_relpath(page)
    full_path = os.path.join(local_dir, relpath)
    os.makedirs(os.path.dirname(full_path) or local_dir, exist_ok=True)
    # A path collision (e.g. both /blog and /blog/ resolved to the same
    # "blog/index.md") is possible on adversarial sites; last write wins,
    # which is an acceptable degradation (still get *a* valid wiki source).
    with open(full_path, "w", encoding="utf-8") as fh:
        fh.write(_front_matter(page))
        fh.write(page.markdown)
    return relpath.replace(os.sep, "/")


def write_site_meta(local_dir: str, start_url: str, pages: List[Dict]) -> None:
    """Write the crawl manifest used by wiki generation to know, per file,
    whether it was flagged as likely user content -- without re-parsing every
    Markdown file's front matter for that one boolean."""
    meta = {
        "start_url": start_url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "pages": pages,  # [{relpath, url, title, likely_user_content}, ...]
    }
    with open(os.path.join(local_dir, _SITE_META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)


def read_site_meta(local_dir: str) -> Dict:
    path = os.path.join(local_dir, _SITE_META_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
