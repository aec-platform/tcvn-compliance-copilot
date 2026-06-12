"""Thin async wrapper around an OpenAI-compatible OSS LLM endpoint.

Works with Ollama (http://localhost:11434/v1), vLLM, SGLang, llama.cpp server,
LiteLLM, or LM Studio — anything that speaks `/chat/completions`. Centralises
retries and JSON parsing so call sites in the compliance engine stay declarative.

The LLM must stay on infrastructure under the operator's control: TCVN/QCVN
review touches client design files that are commercially sensitive, and the
project mandates self-hosted OSS models (Qwen / Llama / DeepSeek) rather than
cross-border managed APIs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tcvn_copilot.config import get_settings
from tcvn_copilot.core.errors import ExternalServiceError
from tcvn_copilot.core.logging import get_logger

log = get_logger(__name__)

ModelRole = Literal["reasoning", "extraction"]


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client  # noqa: PLW0603
    if _client is None:
        settings = get_settings()
        headers: dict[str, str] = {}
        if settings.llm_api_key is not None:
            secret = settings.llm_api_key.get_secret_value()
            if secret:
                headers["authorization"] = f"Bearer {secret}"
        _client = httpx.AsyncClient(
            base_url=str(settings.llm_base_url).rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(settings.llm_request_timeout_seconds),
        )
    return _client


def _model_for(role: ModelRole) -> str:
    s = get_settings()
    return s.llm_reasoning_model if role == "reasoning" else s.llm_extraction_model


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(
        (TimeoutError, ConnectionError, httpx.TransportError, httpx.HTTPStatusError)
    ),
)
async def complete(
    *,
    system: str,
    messages: list[Message],
    role: ModelRole = "reasoning",
    max_tokens: int | None = None,
    temperature: float = 0.0,
    json_response: bool = False,
) -> LLMResponse:
    """Run a single OSS LLM completion via OpenAI-compatible /chat/completions.

    The system prompt is repeated verbatim across calls so the inference server
    (vLLM/SGLang with prefix caching, Ollama with KV-cache reuse) can serve
    the standards corpus prefix from cache — same effect as Anthropic's
    `cache_control: ephemeral`, no client-side wiring needed.
    """
    settings = get_settings()
    model = _model_for(role)

    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "max_tokens": max_tokens or settings.llm_max_output_tokens,
        "temperature": temperature,
    }
    if json_response:
        body["response_format"] = {"type": "json_object"}

    client = _get_client()
    try:
        resp = await client.post("/chat/completions", json=body)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.warning(
            "llm_call_failed",
            status=exc.response.status_code,
            body=exc.response.text[:500],
            model=model,
        )
        raise ExternalServiceError(
            f"LLM endpoint returned {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc
    except Exception as exc:
        log.warning("llm_call_failed", error=str(exc), model=model)
        raise ExternalServiceError(f"LLM call failed: {exc}") from exc

    data = cast(dict[str, Any], resp.json())
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    usage = data.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}

    return LLMResponse(
        text=text,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        # vLLM / SGLang report prefix-cache hits here; Ollama leaves it zero
        # because its KV-cache reuse is implicit.
        cache_read_tokens=int(prompt_details.get("cached_tokens") or 0),
        cache_creation_tokens=0,
        model=model,
    )


async def complete_json(
    *,
    system: str,
    messages: list[Message],
    role: ModelRole = "reasoning",
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Convenience wrapper that asks for and parses a JSON-only response."""
    resp = await complete(
        system=system,
        messages=messages,
        role=role,
        max_tokens=max_tokens,
        temperature=0.0,
        json_response=True,
    )
    body = resp.text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body.split("\n", 1)[1] if "\n" in body else body
        body = body.rstrip("`").strip()
    try:
        parsed: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        log.warning("llm_returned_invalid_json", body_preview=body[:500])
        raise ExternalServiceError(f"LLM returned non-JSON: {exc}") from exc
    return parsed
