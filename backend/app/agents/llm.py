"""LLM access layer.

Agents ask for structured output through a forced tool call, so every answer is
JSON that matches a schema. If no API key is set, a deterministic offline
"mock" provider is used so the platform can be demoed and tested without AI.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from ..config import get_settings

log = logging.getLogger("controllens.llm")
settings = get_settings()


@dataclass
class LLMResult:
    data: dict
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    pass


def provider_name() -> str:
    if settings.llm_provider == "mock":
        return "mock"
    if settings.llm_provider == "anthropic" or settings.anthropic_api_key:
        return "anthropic"
    return "mock"


def model_for(role: str) -> str:
    """Model for a kind of step: plan | evaluate | test | review."""
    return getattr(settings, f"llm_model_{role}", "") or settings.llm_model


def call_structured(*, tool_name: str, tool_description: str, schema: dict, system: str,
                    user: str, mock: Callable[[], dict], retries: int = 2, role: str = "evaluate",
                    attachments: list[dict] | None = None) -> LLMResult:
    """attachments: extra content blocks (images / PDFs) placed before the text."""
    if provider_name() == "mock":
        return LLMResult(data=mock(), provider="mock", model="offline-mock")

    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None, max_retries=3,
                                 timeout=180)
    tool = {"name": tool_name, "description": tool_description, "input_schema": schema}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = client.messages.create(
                model=model_for(role),
                max_tokens=settings.llm_max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": (attachments or []) + [{"type": "text", "text": user}]}],
            )
            block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
            if block is None:
                raise LLMError("Model did not return structured output")
            data = block.input if isinstance(block.input, dict) else json.loads(block.input)
            _check_required(schema, data)
            return LLMResult(data=data, provider="anthropic", model=resp.model,
                             input_tokens=resp.usage.input_tokens,
                             output_tokens=resp.usage.output_tokens)
        except (LLMError, KeyError, ValueError) as e:
            last_err = e
            log.warning("structured output problem (attempt %s): %s", attempt + 1, e)
        except anthropic.APIError as e:
            last_err = e
            log.warning("API error (attempt %s): %s", attempt + 1, e)
            time.sleep(2 * (attempt + 1))
    raise LLMError(f"AI call failed after {retries + 1} attempts: {last_err}")


def _check_required(schema: dict, data: dict):
    for key in schema.get("required", []):
        if key not in data:
            raise LLMError(f"Missing field '{key}' in AI output")
