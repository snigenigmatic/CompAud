"""OpenAI client singleton for CompAud agents."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_enabled or not settings.openai_api_key:
            raise RuntimeError(
                "OpenAI is not configured. Set OPENAI_ENABLED=true and OPENAI_API_KEY in .env"
            )
        _client = OpenAI(api_key=settings.openai_api_key)
        logger.info("OpenAI client initialised (model=%s)", settings.openai_model)
    return _client


def llm_complete(
    system_prompt: str,
    user_prompt: str,
    response_format: dict[str, Any] | None = None,
    temperature: float = 0.2,
) -> str:
    """Send a completion request and return the text response."""
    settings = get_settings()
    client = get_openai_client()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """Send a completion request and parse the JSON response."""
    raw = llm_complete(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    return json.loads(raw)
