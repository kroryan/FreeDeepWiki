"""
Unified content search across both source types: a .zim archive and a
git-repo wiki (backed by the RAG/FAISS retriever already prepared for a chat
connection). Both the "page + related pages" initial-context builder and the
agent's SEARCH_WIKI tool call this same function, so a .zim and a normal
repo behave identically from the chat's point of view.
"""
import logging
import os
from typing import Callable, Optional, TypedDict

from api import zim_reader

logger = logging.getLogger(__name__)


class SearchResult(TypedDict):
    title: str
    snippet: str
    ref: str  # zim entry path, or file_path for a repo


def search_zim(zim_path: str, query: str, limit: int = 5) -> list[SearchResult]:
    archive = zim_reader.open_archive(zim_path)
    hits = zim_reader.search_entries(archive, query, limit=limit)
    results: list[SearchResult] = []
    for hit in hits:
        try:
            content, mimetype = zim_reader.get_entry_content(archive, hit["path"])
            snippet = (
                zim_reader.extract_plain_text(content, max_chars=1000)
                if mimetype.startswith("text/html")
                else ""
            )
        except Exception as e:
            logger.warning(f"Could not read ZIM entry {hit['path']!r} for snippet: {e}")
            snippet = ""
        results.append({"title": hit["title"], "snippet": snippet, "ref": hit["path"]})
    return results


def search_repo(request_rag, query: str, language: str = "en", limit: int = 5) -> list[SearchResult]:
    """`request_rag` is the RAG instance already prepared (embedded/retriever
    built) for the current chat connection -- reused here rather than
    creating a second one, since preparing a retriever re-embeds the whole
    repo and is expensive."""
    try:
        retrieved = request_rag(query, language=language)
    except Exception as e:
        logger.warning(f"Repo search failed for query {query!r}: {e}")
        return []
    if not retrieved or not retrieved[0].documents:
        return []
    results: list[SearchResult] = []
    for doc in retrieved[0].documents[:limit]:
        file_path = doc.meta_data.get("file_path", "unknown")
        results.append({
            "title": file_path,
            "snippet": doc.text[:1000],
            "ref": file_path,
        })
    return results


def format_search_results(results: list[SearchResult]) -> str:
    """Render results as the `<tool_result>` block injected back into the
    conversation for both the initial-context builder and the agent loop."""
    if not results:
        return "No results found."
    parts = []
    for r in results:
        parts.append(f"## {r['title']} ({r['ref']})\n\n{r['snippet']}")
    return "\n\n---\n\n".join(parts)


def build_zim_context(zim_path: str, query: str, current_entry_path: Optional[str], limit: int = 5) -> str:
    """Context for a .zim chat: when the chat was opened from a specific
    entry, that entry (full plain text) plus up to `limit` related entries
    (found by searching the archive's own title, i.e. "what is this page
    about") -- never the whole archive, which can hold millions of entries.
    Without a current entry, falls back to searching the user's own query.
    """
    archive = zim_reader.open_archive(zim_path)

    if not current_entry_path:
        results = search_zim(zim_path, query, limit=limit)
        return format_search_results(results)

    try:
        content, mimetype = zim_reader.get_entry_content(archive, current_entry_path)
        current_title = zim_reader.get_entry_title(archive, current_entry_path)
    except Exception as e:
        logger.warning(f"Could not load current ZIM entry {current_entry_path!r}: {e}")
        results = search_zim(zim_path, query, limit=limit)
        return format_search_results(results)

    page_text = (
        zim_reader.extract_plain_text(content, max_chars=3000)
        if mimetype.startswith("text/html")
        else ""
    )
    related = [
        r for r in search_zim(zim_path, current_title, limit=limit + 1)
        if r["ref"] != current_entry_path
    ][:limit]

    parts = [f"## Current page: {current_title} ({current_entry_path})\n\n{page_text}"]
    if related:
        parts.append("# Related pages\n\n" + format_search_results(related))
    return "\n\n---\n\n".join(parts)


def build_repo_context(request_rag, query: str, current_page_title: Optional[str], language: str = "en", limit: int = 5) -> str:
    """Context for a normal repo-wiki chat. When opened from a specific wiki
    page, the retrieval query is anchored to that page's title instead of
    just the user's question, so FAISS returns documents relevant to the
    page being viewed rather than the whole repo."""
    effective_query = current_page_title or query
    results = search_repo(request_rag, effective_query, language=language, limit=limit)
    return format_search_results(results)


def resolve_tool_calling(
    *,
    enable_tool_calling: Optional[bool],
    is_deep_research: bool,
    is_zim: bool,
    zim_path: Optional[str],
    request_rag,
    language: str,
) -> tuple[bool, Optional[Callable[[str], str]]]:
    """Shared gate + search_fn resolution for the SEARCH_WIKI agent loop
    (api/agent_loop.py), used identically by the WebSocket and HTTP chat
    handlers so the two transports can't drift on what "tool calling
    enabled" means or what context source it searches. Never enabled for
    Deep Research (it has its own multi-iteration structure/prompts) or via
    the FREEDEEPWIKI_DISABLE_AGENT_LOOP=1 env killswitch.
    """
    enabled = (
        bool(enable_tool_calling)
        and not is_deep_research
        and os.environ.get("FREEDEEPWIKI_DISABLE_AGENT_LOOP") != "1"
    )
    if not enabled:
        return False, None

    if is_zim:
        search_fn: Optional[Callable[[str], str]] = lambda q, _path=zim_path: format_search_results(
            search_zim(_path, q, limit=5)
        )
    elif request_rag is not None:
        search_fn = lambda q, _rag=request_rag, _lang=language: format_search_results(
            search_repo(_rag, q, language=_lang, limit=5)
        )
    else:
        return False, None

    return True, search_fn
