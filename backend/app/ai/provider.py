from abc import ABC, abstractmethod
from collections.abc import Callable

import httpx

from ..config import Settings, settings


class LLMProvider(ABC):
    """Abstract interface for LLM completion providers."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Generate a completion for the given system and user prompts."""
        pass


class OpenAICompatibleProvider(LLMProvider):
    """Calls any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "LLM API key is required for OpenAICompatibleProvider (set MI_LLM_API_KEY)"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key.strip()
        self.timeout = timeout
        self._client = client

    def complete(self, system: str, user: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }

        if self._client is not None:
            response = self._client.post(url, headers=headers, json=payload)
        else:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            raise RuntimeError(
                f"LLM API request failed with status {response.status_code}: {response.text}"
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
            if content is None:
                return ""
            return content.strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Malformed LLM response format: {data}") from exc


class FakeProvider(LLMProvider):
    """Returns canned responses for offline unit tests without network calls."""

    def __init__(self, canned_response: str | Callable[[str, str], str] = "{}") -> None:
        self.canned_response = canned_response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if callable(self.canned_response):
            return self.canned_response(system, user)
        return self.canned_response


def get_llm_provider(settings_obj: Settings | None = None) -> LLMProvider:
    """Factory that instantiates an LLMProvider based on application settings."""
    cfg = settings_obj or settings
    provider_type = cfg.llm_provider.strip().lower()

    if provider_type in ("fake", "mock", "test"):
        return FakeProvider()

    if provider_type in ("real", "openai", "openai-compatible"):
        return OpenAICompatibleProvider(
            base_url=cfg.llm_base_url,
            model=cfg.llm_model,
            api_key=cfg.llm_api_key,
            timeout=cfg.llm_timeout_seconds,
        )

    raise ValueError(f"Unknown LLM provider configured: '{cfg.llm_provider}'")
