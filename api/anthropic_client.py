"""Anthropic (Claude) ModelClient integration.

Talks directly to api.anthropic.com instead of routing through a LiteLLM
proxy, which requires a locally-running gateway that the portable AppImage
never starts. Accepts either:

- A standard Anthropic API key (starts with "sk-ant-api"), sent via the
  `x-api-key` header.
- A Claude Pro/Max subscription OAuth access token (obtained via `claude
  login` in Claude Code, or any Anthropic OAuth login flow), sent via
  `Authorization: Bearer` with the `anthropic-beta: oauth-2025-04-20` header
  Anthropic requires for OAuth-authenticated requests.
"""

from typing import Any, Dict
import logging
import os

import aiohttp
import requests

from adalflow.core.model_client import ModelClient
from adalflow.core.types import ModelType

log = logging.getLogger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
DEFAULT_MAX_TOKENS = 8192


class AnthropicClient(ModelClient):
    """A component wrapper for the native Anthropic Messages API."""

    def __init__(self, api_key: str = None, base_url: str = None, **kwargs) -> None:
        super().__init__()
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL") or ANTHROPIC_API_BASE).rstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "anthropic-version": ANTHROPIC_VERSION}
        if not self._api_key:
            return headers
        if self._api_key.startswith("sk-ant-api"):
            headers["x-api-key"] = self._api_key
        else:
            # Subscription OAuth token (e.g. from `claude login`)
            headers["Authorization"] = f"Bearer {self._api_key}"
            headers["anthropic-beta"] = OAUTH_BETA_HEADER
        return headers

    def convert_inputs_to_api_kwargs(
        self, input: Any, model_kwargs: Dict = None, model_type: ModelType = None
    ) -> Dict:
        model_kwargs = model_kwargs or {}
        if model_type != ModelType.LLM:
            raise ValueError(f"Unsupported model type for Anthropic client: {model_type}")

        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        elif isinstance(input, list) and all(isinstance(m, dict) for m in input):
            messages = input
        else:
            raise ValueError(f"Unsupported input format for Anthropic: {type(input)}")

        api_kwargs = {**model_kwargs, "messages": messages}
        api_kwargs.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
        # Streamed via a single buffered response, matching the OpenRouter client's pattern.
        api_kwargs.pop("stream", None)
        return api_kwargs

    @staticmethod
    def _extract_text(data: Dict) -> str:
        return "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )

    async def acall(self, api_kwargs: Dict = None, model_type: ModelType = None) -> Any:
        api_kwargs = api_kwargs or {}

        if not self._api_key:
            error_msg = (
                "Anthropic API key not configured. Set an API key or paste a Claude "
                "Pro/Max subscription token (from `claude login`) for the Claude provider."
            )
            log.error(error_msg)

            async def error_generator():
                yield error_msg
            return error_generator()

        headers = self._headers()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=api_kwargs,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        log.error(f"Anthropic API error ({response.status}): {error_text}")

                        async def error_response_generator():
                            yield f"Anthropic API error ({response.status}): {error_text}"
                        return error_response_generator()

                    data = await response.json()
        except Exception as e:
            log.error(f"Error calling Anthropic API: {str(e)}")

            async def exception_generator():
                yield f"Error calling Anthropic API: {str(e)}"
            return exception_generator()

        text = self._extract_text(data)

        async def content_generator():
            yield text
        return content_generator()

    def call(self, api_kwargs: Dict = None, model_type: ModelType = None) -> Any:
        api_kwargs = api_kwargs or {}
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY (or a subscription token) must be set")

        response = requests.post(
            f"{self.base_url}/messages",
            headers=self._headers(),
            json=api_kwargs,
            timeout=300,
        )
        response.raise_for_status()
        return self._extract_text(response.json())
