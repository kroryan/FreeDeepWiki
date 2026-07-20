"""
Thin wrapper over libzim (openzim.org's Python bindings) for reading .zim
archives: offline wiki dumps (Wikipedia, DevDocs, StackExchange, etc.).

A .zim file can hold anywhere from dozens to millions of entries, so this
module never loads "everything" -- it opens the archive lazily, resolves
individual entries by path, and relies on libzim's built-in full-text search
index (Xapian under the hood) rather than building our own index.
"""
import logging
import mimetypes
import re
import string
import threading
from typing import Optional, TypedDict

from libzim.reader import Archive
from libzim.search import Query, Searcher
from libzim.suggestion import SuggestionSearcher

logger = logging.getLogger(__name__)

# Archive objects are cheap to keep open (lazy reads), so cache them by path
# for the lifetime of the process instead of reopening on every request.
_archive_cache: dict[str, Archive] = {}
_archive_cache_lock = threading.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class SearchHit(TypedDict):
    path: str
    title: str


def open_archive(path: str) -> Archive:
    """Open (or reuse a cached handle for) the .zim file at `path`.

    Raises whatever libzim raises (RuntimeError) if `path` is not a valid
    .zim file -- callers should catch that and turn it into an HTTP 400.
    """
    with _archive_cache_lock:
        cached = _archive_cache.get(path)
        if cached is not None:
            return cached
        archive = Archive(path)
        _archive_cache[path] = archive
        return archive


def close_archive(path: str) -> None:
    """Drop a cached Archive handle (called when a .zim is unregistered)."""
    with _archive_cache_lock:
        _archive_cache.pop(path, None)


def _resolve_main_entry_path(archive: Archive) -> Optional[str]:
    """archive.main_entry is itself a redirect pseudo-entry: its own `.path`
    (e.g. "mainPage") is NOT a real, independently-resolvable path in the
    archive namespace -- calling get_entry_by_path() on it raises "Cannot
    find entry". The real, browsable path is only reachable by following the
    redirect once via get_redirect_entry()."""
    if not archive.has_main_entry:
        return None
    main_entry = archive.main_entry
    if main_entry.is_redirect:
        return main_entry.get_redirect_entry().path
    return main_entry.path


def get_metadata(archive: Archive) -> dict:
    def _meta(key: str) -> Optional[str]:
        if key not in archive.metadata_keys:
            return None
        try:
            return archive.get_metadata(key).decode("utf-8", errors="replace")
        except Exception:
            return None

    return {
        "title": _meta("Title") or "Untitled ZIM",
        "description": _meta("Description") or "",
        "language": _meta("Language") or "",
        "creator": _meta("Creator") or "",
        "articleCount": archive.article_count,
        "hasFulltextIndex": archive.has_fulltext_index,
        "mainEntryPath": _resolve_main_entry_path(archive),
    }


def get_entry_content(archive: Archive, path: str) -> tuple[bytes, str]:
    """Return (content_bytes, mimetype) for the entry at `path`.

    Raises KeyError (via libzim) if the path does not exist in the archive.

    Some archives (seen in the wild with DevDocs-sourced .zim files) store a
    generic "application/octet-stream" mimetype for their own CSS/JS assets.
    Browsers enforce strict MIME sniffing for stylesheets and scripts, so a
    wrong type here means the page silently loses its styling/interactivity
    with only a console warning to explain why. When libzim's own mimetype
    is that generic fallback, prefer a type guessed from the path's
    extension -- it only ever makes the type MORE specific, never less.
    """
    entry = archive.get_entry_by_path(path)
    if entry.is_redirect:
        entry = entry.get_redirect_entry()
    item = entry.get_item()
    mimetype = item.mimetype
    if not mimetype or mimetype == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(path)
        if guessed:
            mimetype = guessed
    return bytes(item.content), mimetype


def get_entry_title(archive: Archive, path: str) -> str:
    entry = archive.get_entry_by_path(path)
    return entry.title


def search_entries(archive: Archive, query: str, limit: int = 5) -> list[SearchHit]:
    """Full-text search using libzim's built-in Xapian index.

    Falls back to an empty list (never raises) if the archive has no
    full-text index or the query fails -- callers treat "no results" the
    same as "search unavailable" for a single .zim.
    """
    if not query or not query.strip():
        return []
    try:
        searcher = Searcher(archive)
        search = searcher.search(Query().set_query(query))
        hits: list[SearchHit] = []
        for path in search.getResults(0, limit):
            try:
                title = archive.get_entry_by_path(path).title
            except Exception:
                title = path
            hits.append({"path": path, "title": title})
        return hits
    except Exception as e:
        logger.warning(f"ZIM search failed for query {query!r}: {e}")
        return []


class IndexEntry(TypedDict):
    path: str
    title: str


def build_title_index(archive: Archive, limit: int = 500) -> dict:
    """Browsable index of the archive's article pages, sorted by title.

    libzim's Python bindings expose no direct "enumerate every entry" call
    (no __iter__, no get_entry_by_id) -- the only way to reach entries in
    bulk is through the search/suggestion indexes.

    Primary strategy: sweep the title-suggestion index by every
    alphanumeric prefix and dedupe by path. In practice this reaches every
    article in any archive that titles its pages with normal alphanumeric
    text (verified: exactly matched article_count on a real DevDocs .zim).
    It finds nothing for archives with no title-suggestion index built, or
    ones titled purely in other scripts/symbols that never start with a-z0-9.

    Fallback: if that sweep comes up empty (or clearly incomplete relative
    to article_count) but the archive does have articles, fill in with
    get_random_entry() calls instead -- not a real index (no ordering, no
    guarantee of covering everything), but a working, always-available
    "here are some pages" list beats an empty one.
    """
    seen: dict[str, str] = {}
    try:
        searcher = SuggestionSearcher(archive)
        for prefix in string.ascii_lowercase + string.digits:
            if len(seen) >= limit:
                break
            try:
                suggestion = searcher.suggest(prefix)
                paths = suggestion.getResults(0, limit)
            except Exception as e:
                logger.warning(f"ZIM index sweep failed for prefix {prefix!r}: {e}")
                continue
            for path in paths:
                if path in seen or len(seen) >= limit:
                    continue
                try:
                    entry = archive.get_entry_by_path(path)
                    if entry.is_redirect:
                        entry = entry.get_redirect_entry()
                    if not entry.get_item().mimetype.startswith("text/html"):
                        continue
                    seen[path] = entry.title
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"ZIM title-suggestion sweep unavailable: {e}")

    if not seen and archive.article_count > 0:
        target = min(limit, archive.article_count)
        # get_random_entry() can repeat, especially once we've already
        # collected most of a small archive -- cap attempts instead of
        # looping until we hit `target`, which could spin forever on a
        # small archive once every article's already been seen.
        for _ in range(target * 4):
            if len(seen) >= target:
                break
            try:
                entry = archive.get_random_entry()
                if entry.is_redirect:
                    entry = entry.get_redirect_entry()
                if not entry.get_item().mimetype.startswith("text/html"):
                    continue
                seen[entry.path] = entry.title
            except Exception:
                continue

    entries: list[IndexEntry] = sorted(
        ({"path": p, "title": t} for p, t in seen.items()),
        key=lambda e: e["title"].lower(),
    )
    return {
        "entries": entries,
        "truncated": len(seen) >= limit and archive.article_count > limit,
        "totalArticles": archive.article_count,
    }


def extract_plain_text(html: bytes, max_chars: int = 4000) -> str:
    """Strip HTML tags for a cheap plain-text snippet to feed an LLM as
    context. Not a real HTML parser -- good enough for prose extraction,
    not for anything security-sensitive (never rendered as HTML)."""
    text = html.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:max_chars]
