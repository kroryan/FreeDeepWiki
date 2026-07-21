"""Data shapes for the website crawler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional


@dataclass
class CrawlScope:
    """How much of the site to crawl. Exactly one of ``mode``'s meanings
    applies; the others are ignored. Mirrors the three choices offered in the
    UI: a page-count cap, an explicit subdomain/path list, or "the whole site"."""

    mode: str = "count"  # "count" | "subdomains" | "all"
    max_pages: int = 60
    # For mode == "subdomains": explicit list of subdomains/paths to crawl,
    # one per line in the UI (e.g. "blog.example.com" or
    # "example.com/docs") -- each seeds its own crawl, still same-site-only.
    subdomains: List[str] = field(default_factory=list)
    respect_robots: bool = True
    max_depth: int = 12  # safety cap even in "all" mode (avoids infinite paginated traps)
    # Hard ceiling regardless of user input, so a mistyped huge number (or
    # "all" on a massive site) can't run for hours / blow through the LLM
    # token budget. The UI surfaces this as the practical max.
    hard_cap: int = 2000


@dataclass
class CrawlPage:
    url: str
    path: str  # URL path, used to derive the local file path
    title: str
    markdown: str
    depth: int
    links: List[str] = field(default_factory=list)  # same-site links found on this page
    # Heuristic-only guess (URL pattern based) that this page is user-generated
    # content (profile/comments/forum post/etc.) rather than site content. The
    # wiki-structure LLM makes the final call using this as a hint -- see the
    # module docstring in api/web_crawler/__init__.py.
    likely_user_content: bool = False
    status_code: int = 200
    content_type: str = "text/html"


@dataclass
class CrawlProgress:
    message: str
    pages_done: int
    pages_total_estimate: int
    percent: Optional[int] = None


ProgressCb = Callable[[CrawlProgress], Awaitable[None]]
