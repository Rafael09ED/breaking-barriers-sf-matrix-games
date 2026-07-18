from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from typing import Any, Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel

from takeoff.config import Settings


class ModelTransportError(RuntimeError):
    """The provider call failed before a usable model response was returned."""


class ModelOutputError(ValueError):
    """The provider returned no structured response to validate."""


class StructuredModelClient(Protocol):
    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[BaseModel],
        schema_name: str,
    ) -> str: ...


class OpenRouterClient:
    def __init__(
        self,
        settings: Settings,
        *,
        model: str,
        temperature: float,
        reasoning_effort: str,
    ) -> None:
        headers = {"X-Title": settings.app_name}
        if settings.app_url:
            headers["HTTP-Referer"] = settings.app_url
        self._model = model
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort
        self._debug_prompts_path = settings.debug_prompts_path
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=headers,
            max_retries=3,
            timeout=60.0,
        )

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[BaseModel],
        schema_name: str,
    ) -> str:
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        }
        self._audit_prompt(messages, schema_name)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=list(messages),  # type: ignore[arg-type]
                response_format=response_format,  # type: ignore[arg-type]
                temperature=self._temperature,
                extra_body={
                    "reasoning": (
                        {"enabled": False}
                        if self._reasoning_effort == "off"
                        else {"effort": self._reasoning_effort, "exclude": True}
                    ),
                    "provider": {"require_parameters": True},
                },
            )
        except (APIConnectionError, APITimeoutError, APIStatusError) as error:
            raise ModelTransportError(str(error)) from error

        content = response.choices[0].message.content
        if not content:
            raise ModelOutputError("model returned an empty response")
        return content

    def _audit_prompt(
        self,
        messages: Sequence[Mapping[str, str]],
        schema_name: str,
    ) -> None:
        if self._debug_prompts_path is None:
            return
        self._debug_prompts_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "created_at": datetime.now(UTC).isoformat(),
            "model": self._model,
            "schema_name": schema_name,
            "messages": [dict(message) for message in messages],
        }
        with self._debug_prompts_path.open("a", encoding="utf-8") as audit:
            audit.write(json.dumps(record, ensure_ascii=True))
            audit.write("\n")