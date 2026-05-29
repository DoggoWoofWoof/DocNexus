import json
import time
from dataclasses import dataclass
from typing import Any

from backend.app.core.config import Settings


class MistralConfigurationError(RuntimeError):
    """Raised when Mistral cannot be called because configuration is missing."""


class MistralClientError(RuntimeError):
    """Raised when Mistral returns an unexpected response or client error."""


@dataclass
class MistralToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class MistralMessage:
    content: str | None
    tool_calls: list[MistralToolCall]


class MistralToolClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        parallel_tool_calls: bool = True,
        temperature: float = 0.0,
    ) -> MistralMessage:
        if not self.settings.mistral_api_key:
            raise MistralConfigurationError("MISTRAL_API_KEY is not configured.")

        try:
            try:
                from mistralai import Mistral
            except ImportError:
                from mistralai.client import Mistral
        except ImportError as exc:
            raise MistralConfigurationError(
                "The mistralai package is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        client = Mistral(api_key=self.settings.mistral_api_key)

        for attempt, delay in enumerate([0.0, 1.5, 3.0], start=1):
            if delay:
                time.sleep(delay)
            try:
                response = client.chat.complete(
                    model=self.settings.mistral_model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    parallel_tool_calls=parallel_tool_calls,
                    temperature=temperature,
                )
                break
            except Exception as exc:
                if attempt == 3 or not _is_rate_limit_error(exc):
                    raise MistralClientError(f"Mistral chat completion failed: {exc}") from exc

        return self._parse_response(response)

    def complete_text(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
    ) -> str:
        if not self.settings.mistral_api_key:
            raise MistralConfigurationError("MISTRAL_API_KEY is not configured.")

        try:
            try:
                from mistralai import Mistral
            except ImportError:
                from mistralai.client import Mistral
        except ImportError as exc:
            raise MistralConfigurationError(
                "The mistralai package is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        client = Mistral(api_key=self.settings.mistral_api_key)
        for attempt, delay in enumerate([0.0, 1.5, 3.0], start=1):
            if delay:
                time.sleep(delay)
            try:
                response = client.chat.complete(
                    model=self.settings.mistral_model,
                    messages=messages,
                    temperature=temperature,
                )
                break
            except Exception as exc:
                if attempt == 3 or not _is_rate_limit_error(exc):
                    raise MistralClientError(f"Mistral text completion failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise MistralClientError("Mistral response did not include choices[0].message.content.") from exc

        if not content:
            raise MistralClientError("Mistral returned an empty response.")
        return content

    def _parse_response(self, response: Any) -> MistralMessage:
        try:
            message = response.choices[0].message
        except Exception as exc:
            raise MistralClientError("Mistral response did not include choices[0].message.") from exc

        content = self._get_value(message, "content")
        raw_tool_calls = self._get_value(message, "tool_calls") or []

        tool_calls: list[MistralToolCall] = []
        for raw_tool_call in raw_tool_calls:
            function = self._get_value(raw_tool_call, "function") or {}
            name = self._get_value(function, "name")
            raw_arguments = self._get_value(function, "arguments") or "{}"
            tool_call_id = self._get_value(raw_tool_call, "id") or name or "tool_call"

            if not name:
                raise MistralClientError("Tool call is missing a function name.")

            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError as exc:
                raise MistralClientError(f"Tool call arguments were not valid JSON: {raw_arguments}") from exc

            tool_calls.append(
                MistralToolCall(
                    id=tool_call_id,
                    name=name,
                    arguments=arguments,
                )
            )

        return MistralMessage(content=content, tool_calls=tool_calls)

    @staticmethod
    def _get_value(value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "rate_limited" in message
