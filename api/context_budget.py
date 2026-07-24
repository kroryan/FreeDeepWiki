"""Keeps the `<file_tree>` block of a wiki-structure-planning prompt within
the selected model's actual context window, proactively -- instead of only
reacting after the provider already rejected an oversized prompt (see
CONTEXT_LIMIT_ERROR_PHRASES in websocket_wiki.py/simple_chat.py, which stays
in place as a defense-in-depth fallback for whatever this estimate misses).

Why this exists: the frontend (src/app/[owner]/[repo]/page.tsx) embeds the
COMPLETE, unfiltered file tree of the repository into the structure-planning
prompt with no size cap -- fine for a small/medium repo and a large-context
cloud model, but a large monorepo (thousands of files) against a
small-context local model (Ollama models often default to a few thousand
tokens unless configured otherwise) reliably blows the context window,
producing a hard 500 error with no usable wiki at all.

Shared by both chat transports (websocket_wiki.py, simple_chat.py) so they
can't drift on this -- mirrors how MAX_FALLBACK_QUERY_CHARS/
CONTEXT_LIMIT_ERROR_PHRASES are already independently duplicated between the
two with a cross-referencing comment, the established pattern in this
codebase for HTTP/WebSocket transport parity.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)

_FILE_TREE_RE = re.compile(r"(<file_tree>\n)(.*?)(\n</file_tree>)", re.DOTALL)

# Ollama models default to a modest context window unless the caller (or the
# model's own Modelfile) configures num_ctx explicitly -- generator.json
# specifies num_ctx per listed model, but a custom/unlisted Ollama model (or
# any provider with no num_ctx in its resolved model_kwargs) has no reliable
# value here, so this is a conservative assumption for "provider says nothing
# concrete about its window", NOT applied when num_ctx IS present.
_DEFAULT_CONTEXT_TOKENS: Dict[str, int] = {
    "ollama": 8192,
    # Per-provider conservative floors for when num_ctx isn't set. These are
    # real observed context windows per family, not guesses -- using the
    # actual window (instead of a flat 100k for every cloud provider) stops
    # the file-tree budget from over-trimming a 50k-token tree that a
    # Gemini-1M or Claude-200k model could fully absorb, while still capping
    # a 200k-token tree that would blow an older 128k model.
    "claude": 200_000,
    "google": 1_000_000,
    "openai": 128_000,
    "openai_custom": 128_000,
    "openrouter": 128_000,
    "litellm": 128_000,
    "bedrock": 200_000,
    "azure": 128_000,
    "dashscope": 128_000,
}
# Conservative floor for any provider not listed above.
_FALLBACK_CLOUD_CONTEXT_TOKENS = 128_000

# Per-MODEL context windows, keyed by provider then model name (substring
# match against the resolved model string -- so "claude-3-5-sonnet" hits the
# "claude-3-5" entry). Families differ a lot within a provider -- Claude
# 3.5/3.7 Sonnet/Haiku are 200k but Claude 3 Opus is 200k too, while Claude 2
# was 100k; GPT-4o is 128k but gpt-4 (vision) 128k, gpt-4-turbo 128k, gpt-3.5
# 16k/4k; Gemini 1.5 is 1M/2M, Gemini 2.0 is 1M, Gemini 2.5 Pro is 1M/2M.
# Without a per-model table the file-tree budget assumed the provider's
# single floor for every model in that family, over-trimming trees a big
# 2M-context model could fully absorb (or under-trimming for a tiny one).
# Resolved in resolve_context_window AFTER num_ctx, BEFORE the provider floor.
# Values are real published context windows, conservative (input-side).
_MODEL_CONTEXT_TOKENS: Dict[str, Dict[str, int]] = {
    "claude": {
        "claude-3-5": 200_000,
        "claude-3-7": 200_000,
        "claude-3-opus": 200_000,
        "claude-3-haiku": 200_000,
        "claude-3-sonnet": 200_000,
        "claude-2": 100_000,
        "claude-opus-4": 200_000,
        "claude-sonnet-4": 200_000,
        "claude-haiku-4": 200_000,
    },
    "openai": {
        "gpt-4o": 128_000,
        "gpt-4-turbo": 128_000,
        "gpt-4.1": 1_000_000,
        "o1": 200_000,
        "o3": 200_000,
        "o4-mini": 200_000,
        "gpt-4": 128_000,
        "gpt-3.5-turbo-16k": 16_000,
        "gpt-3.5": 16_000,
    },
    "openai_custom": {
        # Caller-defined endpoint; assume modern 128k unless the model name
        # signals otherwise. Kept permissive (substring) since custom models
        # are arbitrary strings.
        "gpt-4.1": 1_000_000,
        "gpt-4o": 128_000,
        "o1": 200_000,
        "o3": 200_000,
    },
    "google": {
        "gemini-2.5-pro": 2_000_000,
        "gemini-2.5-flash": 1_000_000,
        "gemini-2.0": 1_000_000,
        "gemini-1.5-pro": 2_000_000,
        "gemini-1.5-flash": 1_000_000,
        "gemini-1.5": 1_000_000,
    },
    "openrouter": {
        # OpenRouter proxies many models; default to the provider floor
        # (128k) unless the routed model name carries a known family.
        "gpt-4o": 128_000,
        "claude-3.5": 200_000,
        "claude-3.7": 200_000,
        "gemini-2.5": 2_000_000,
        "gemini-1.5": 1_000_000,
        "deepseek": 128_000,
        "llama-3": 128_000,
    },
    "litellm": {
        "gpt-4o": 128_000,
        "claude-3.5": 200_000,
        "claude-3.7": 200_000,
        "gemini-2.5": 2_000_000,
        "gemini-1.5": 1_000_000,
        "deepseek": 128_000,
    },
    "bedrock": {
        "claude-3-5": 200_000,
        "claude-3-7": 200_000,
        "claude-3-opus": 200_000,
        "claude-3-haiku": 200_000,
        "anthropic.claude": 200_000,
        "amazon.nova": 300_000,
        "meta.llama3": 128_000,
    },
    "azure": {
        "gpt-4o": 128_000,
        "gpt-4-turbo": 128_000,
        "gpt-4.1": 1_000_000,
        "gpt-35-turbo": 16_000,
        "gpt-3.5": 16_000,
        "o3": 200_000,
        "o4-mini": 200_000,
    },
    "dashscope": {
        "qwen-max": 32_000,
        "qwen-plus": 131_000,
        "qwen-turbo": 1_000_000,
        "qwen2.5": 131_000,
        "qwen3": 131_000,
    },
}

# Fraction of the model's context window reserved for the file tree
# specifically -- leaves room for the README, task instructions, output XML
# schema, conversation history, and the model's own generated output.
_FILE_TREE_BUDGET_FRACTION = 0.35

# Per-directory entry caps tried in order (most generous first) until the
# summarized tree fits the token budget.
_PER_DIR_CAPS = (50, 30, 20, 12, 8, 5, 3, 2, 1)


def resolve_context_window(provider: str, model_config_kwargs: dict) -> int:
    """The effective context window (tokens) to budget the file tree
    against: the model's own configured num_ctx if we have one (Ollama),
    else a per-MODEL lookup (many models in a family have different windows),
    else a provider-appropriate default."""
    num_ctx = model_config_kwargs.get("num_ctx") if model_config_kwargs else None
    if isinstance(num_ctx, (int, float)) and num_ctx > 0:
        return int(num_ctx)
    model = (model_config_kwargs.get("model") if model_config_kwargs else None) or ""
    per_model = _MODEL_CONTEXT_TOKENS.get(provider, {})
    if model and per_model:
        for name, win in per_model.items():
            if model == name or name in model:
                return win
    return _DEFAULT_CONTEXT_TOKENS.get(provider, _FALLBACK_CLOUD_CONTEXT_TOKENS)


def _summarize_tree_text(tree_text: str, budget_tokens: int, count_tokens_fn, is_ollama: bool) -> str:
    """Group file paths by directory and progressively cap how many entries
    of each directory are shown, so a directory with hundreds/thousands of
    near-identical files (or a monorepo with thousands of directories) never
    silently loses whole sections -- every directory keeps at least a
    representative sample, with an explicit count of what's hidden, instead
    of a naive head/tail character truncation losing entire directories
    outright depending on where they land alphabetically."""
    lines = [line for line in tree_text.split("\n") if line.strip()]
    groups: Dict[str, list] = defaultdict(list)
    for line in lines:
        directory = "/".join(line.split("/")[:-1]) or "."
        groups[directory].append(line)

    candidate = tree_text
    for per_dir_cap in _PER_DIR_CAPS:
        out_lines = []
        for directory in sorted(groups):
            entries = sorted(groups[directory])
            shown = entries[:per_dir_cap]
            out_lines.extend(shown)
            hidden = len(entries) - len(shown)
            if hidden > 0:
                out_lines.append(f"... and {hidden} more file(s) in {directory}/ (not shown individually)")
        candidate = "\n".join(out_lines)
        if count_tokens_fn(candidate, is_ollama_embedder=is_ollama) <= budget_tokens:
            return candidate

    # Every directory already capped at 1 entry and still too big (an
    # extreme case: tens of thousands of distinct directories) -- fall back
    # to a hard character truncate as an absolute last resort.
    approx_chars = max(budget_tokens * 4, 1000)
    return candidate[:approx_chars] + "\n... [tree truncated further -- too large even summarized]"


def summarize_file_tree_in_query(
    query: str,
    *,
    provider: str,
    model_config_kwargs: dict,
    count_tokens_fn,
) -> str:
    """If `query` contains a `<file_tree>...</file_tree>` block (the
    wiki-structure-planning prompt built by determineWikiStructure in
    page.tsx) and it doesn't fit the resolved model's context budget,
    replace it in place with a directory-aware summary. Returns `query`
    unchanged if there's no file_tree block or it already fits."""
    match = _FILE_TREE_RE.search(query)
    if not match:
        return query

    tree_text = match.group(2)
    is_ollama = provider == "ollama"
    context_window = resolve_context_window(provider, model_config_kwargs)
    budget_tokens = int(context_window * _FILE_TREE_BUDGET_FRACTION)

    if count_tokens_fn(tree_text, is_ollama_embedder=is_ollama) <= budget_tokens:
        return query

    logger.warning(
        "File tree in prompt exceeds ~%d token budget for provider=%s (context_window=%d); summarizing per-directory",
        budget_tokens, provider, context_window,
    )
    summarized = _summarize_tree_text(tree_text, budget_tokens, count_tokens_fn, is_ollama)
    return query[: match.start(2)] + summarized + query[match.end(2):]
