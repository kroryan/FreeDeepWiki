"""
Textual tool-calling agent loop layered on top of api.provider_streaming.

Both `.zim` chats and normal repo-wiki chats are single-shot prompt
completions today (see api/provider_streaming.py) -- no client here
normalizes native function-calling across all 8 supported providers. So
this reuses the same textual protocol Deep Research already uses (headings
like "## Research Plan" detected by substring): the system prompt instructs
the model that if it needs more context than it was given, its ENTIRE
response should be exactly one line, `SEARCH_WIKI: <query>`. This module
detects that line as it streams in, resolves it via a caller-supplied
search function, and re-prompts the model with the result appended --
transparently to the caller, which only ever sees the final answer text
(plus a small "(Buscando: ...)" marker the backend itself emits, never text
the model wrote).
"""
import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from api.provider_streaming import stream_provider_response

logger = logging.getLogger(__name__)

SEARCH_PREFIX = "SEARCH_WIKI:"
# Generous enough for a multi-hop chase (search -> follow a related result's
# title -> follow one of ITS related results -> ... -> answer) since a
# single search often isn't enough to answer a question that requires
# "clicking through" a couple of linked pages, not just bounded to one flat
# lookup. Still capped -- see the forced-final-round handling below, which
# guarantees an answer is always produced instead of looping forever.
MAX_TOOL_ROUNDS = 5
# Cap on how much of the "query" line we'll buffer before giving up on ever
# seeing a newline -- guards against a model that emits the prefix and then
# just keeps generating without ever closing the line.
MAX_QUERY_BUFFER = 500

SendChunk = Callable[[str], Awaitable[None]]


async def sniff_and_relay(stream: AsyncIterator[str], send_chunk: SendChunk) -> Optional[str]:
    """Relay `stream` to `send_chunk` verbatim UNLESS it turns out to be a
    `SEARCH_WIKI: <query>` tool call, in which case nothing is relayed and
    the query is returned instead (None if this was ordinary text).

    Only the first few characters need buffering: as soon as the
    accumulated text (leading whitespace ignored) stops being a valid
    case-insensitive prefix of "SEARCH_WIKI:", it's flushed in one shot and
    every later chunk is forwarded immediately -- the buffer never grows
    past ~len("SEARCH_WIKI:"), so this adds no perceptible latency to
    ordinary answers.
    """
    buffer = ""
    relaying = False
    async for chunk in stream:
        if relaying:
            await send_chunk(chunk)
            continue

        buffer += chunk
        stripped = buffer.lstrip()
        if not stripped:
            if len(buffer) > MAX_QUERY_BUFFER:
                await send_chunk(buffer)
                relaying = True
            continue

        upper = stripped.upper()
        if upper.startswith(SEARCH_PREFIX):
            if "\n" in stripped or len(stripped) - len(SEARCH_PREFIX) > MAX_QUERY_BUFFER:
                break
            continue  # confirmed tool-call line, keep collecting the query
        if len(upper) < len(SEARCH_PREFIX) and SEARCH_PREFIX.startswith(upper):
            continue  # still an ambiguous prefix, need more characters

        # Definitely not a tool call: flush what we buffered and relay
        # everything else directly from here on.
        await send_chunk(buffer)
        relaying = True
    else:
        # Stream ended without ever diverging from (or completing) the
        # prefix check above.
        if not relaying and buffer:
            stripped = buffer.lstrip()
            if stripped.upper().startswith(SEARCH_PREFIX):
                query = stripped[len(SEARCH_PREFIX):].strip()
                if query:
                    return query
            await send_chunk(buffer)
        return None

    # Reached via `break`: buffer is a confirmed "SEARCH_WIKI: ..." line.
    stripped = buffer.lstrip()
    line, _, _ = stripped.partition("\n")
    query = line[len(SEARCH_PREFIX):].strip()
    if query:
        return query
    # Full prefix but an empty query is ambiguous -- treat as ordinary text
    # rather than looping on a request we can't act on.
    await send_chunk(buffer)
    return None


async def _run_agent_rounds(
    *,
    provider: str,
    requested_model: Optional[str],
    prompt: str,
    model_config_kwargs: dict,
    api_key: Optional[str],
    api_endpoint: Optional[str],
    search_fn: Callable[[str], str],
    send_chunk: SendChunk,
) -> None:
    # Some models (seen with a reasoning-heavy cloud model under a longer,
    # tool-instructions-laden prompt) can legitimately end their stream
    # having produced zero content chunks -- no error, just nothing. Track
    # whether anything at all has reached the caller so that if the whole
    # loop ends without ever relaying a single character, we say SOMETHING
    # instead of leaving the user looking at a blank response with no
    # indication of what happened.
    sent_anything = False

    async def tracked_send_chunk(text: str) -> None:
        nonlocal sent_anything
        if text:
            sent_anything = True
        await send_chunk(text)

    current_prompt = prompt
    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        is_last_round = round_num == MAX_TOOL_ROUNDS
        if is_last_round:
            current_prompt += (
                "\n<note>You have used all available searches for this answer. "
                "Answer now using the information already gathered -- do not "
                "request another search.</note>\n"
            )

        stream = stream_provider_response(
            provider=provider,
            requested_model=requested_model,
            prompt=current_prompt,
            model_config_kwargs=model_config_kwargs,
            api_key=api_key,
            api_endpoint=api_endpoint,
        )

        if is_last_round:
            # No round left to act on a tool call even if the model ignores
            # the note above -- relay raw so the user never sees a blank
            # response because we swallowed a stray "SEARCH_WIKI:" line.
            async for chunk in stream:
                await tracked_send_chunk(chunk)
            break

        query = await sniff_and_relay(stream, tracked_send_chunk)
        if not query:
            break

        logger.info(f"Agent tool call SEARCH_WIKI: {query!r} (round {round_num})")
        await tracked_send_chunk(f"\n\n_(Buscando: {query})_\n\n")
        try:
            tool_result = search_fn(query)
        except Exception as e:
            logger.warning(f"search_fn failed for query {query!r}: {e}")
            tool_result = "Search failed."

        current_prompt += (
            f"{SEARCH_PREFIX} {query}\n\n"
            f"<tool_result>\n{tool_result}\n</tool_result>\n\nAssistant: "
        )
    if not sent_anything:
        logger.warning("Agent loop produced no output at all; sending fallback message")
        await send_chunk(
            "I wasn't able to generate a response for that. Please try rephrasing your question."
        )


async def run_agent_chat(
    *,
    provider: str,
    requested_model: Optional[str],
    prompt: str,
    model_config_kwargs: dict,
    api_key: Optional[str] = None,
    api_endpoint: Optional[str] = None,
    search_fn: Callable[[str], str],
) -> AsyncIterator[str]:
    """Async-generator facade over `_run_agent_rounds`'s callback-based loop,
    so both call sites (the WebSocket handler's `await websocket.send_text`
    and the HTTP handler's `yield`) can consume this the same way they
    already consume `stream_provider_response`: `async for text in ...`.

    A background task drives the round loop and feeds an internal queue via
    the `send_chunk` callback; this generator just relays the queue in
    order. If the consumer stops iterating early (e.g. the client
    disconnects mid-round), the task is cancelled instead of left running.
    """
    queue: "asyncio.Queue[Any]" = asyncio.Queue()
    _DONE = object()

    async def send_chunk(text: str) -> None:
        await queue.put(text)

    async def runner() -> None:
        try:
            await _run_agent_rounds(
                provider=provider,
                requested_model=requested_model,
                prompt=prompt,
                model_config_kwargs=model_config_kwargs,
                api_key=api_key,
                api_endpoint=api_endpoint,
                search_fn=search_fn,
                send_chunk=send_chunk,
            )
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(runner())
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            yield item
    finally:
        # Only reached normally once the loop above breaks, or via
        # GeneratorExit if the consumer stops iterating early (client
        # disconnect mid-round) -- either way, don't leave the round loop
        # running in the background.
        if not task.done():
            task.cancel()

    # Only reached on normal completion (GeneratorExit propagates past this
    # point without running it). Surfaces any exception the round loop hit
    # (e.g. a provider error), matching stream_provider_response's behavior
    # of propagating to the caller's own try/except.
    try:
        await task
    except asyncio.CancelledError:
        pass
