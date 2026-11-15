import json

import httpx
import pytest

from app.ai.provider import (
    FakeProvider,
    LLMProvider,
    OpenAICompatibleProvider,
    get_llm_provider,
)
from app.config import Settings


def test_fake_provider_returns_canned_json_and_records_calls():
    canned = json.dumps({"sector": ["banking"], "event_type": "policy"})
    provider = FakeProvider(canned_response=canned)

    assert isinstance(provider, LLMProvider)
    assert len(provider.calls) == 0

    res = provider.complete("system prompt", "user query")
    assert res == canned
    assert len(provider.calls) == 1
    assert provider.calls[0] == ("system prompt", "user query")


def test_real_provider_requires_api_key():
    with pytest.raises(ValueError, match="LLM API key is required"):
        OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            api_key=None,
        )

    with pytest.raises(ValueError, match="LLM API key is required"):
        OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            api_key="   ",
        )


def test_real_provider_successful_completion():
    expected_content = '{"event_type": "policy"}'

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key-123"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "gpt-4o-mini"
        assert payload["messages"] == [
            {"role": "system", "content": "You are a finance assistant."},
            {"role": "user", "content": "Tag this news."},
        ]

        return httpx.Response(
            status_code=200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": expected_content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="test-key-123",
        client=client,
    )

    out = provider.complete("You are a finance assistant.", "Tag this news.")
    assert out == expected_content


def test_real_provider_handles_api_error():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, text="Invalid API key")

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="bad-key",
        client=client,
    )

    with pytest.raises(RuntimeError, match="status 401"):
        provider.complete("sys", "user")


def test_real_provider_handles_malformed_response():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"error": "no choices returned"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="key",
        client=client,
    )

    with pytest.raises(RuntimeError, match="Malformed LLM response format"):
        provider.complete("sys", "user")


def test_factory_returns_fake_provider():
    cfg = Settings(llm_provider="fake")
    provider = get_llm_provider(cfg)
    assert isinstance(provider, FakeProvider)


def test_factory_returns_real_provider():
    cfg = Settings(
        llm_provider="openai",
        llm_base_url="https://custom.llm/v1",
        llm_model="custom-model",
        llm_api_key="sk-test-secret",
    )
    provider = get_llm_provider(cfg)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://custom.llm/v1"
    assert provider.model == "custom-model"
    assert provider.api_key == "sk-test-secret"


def test_factory_raises_when_real_key_missing():
    cfg = Settings(llm_provider="real", llm_api_key=None)
    with pytest.raises(ValueError, match="LLM API key is required"):
        get_llm_provider(cfg)


def test_factory_raises_on_unknown_provider():
    cfg = Settings(llm_provider="anthropic-bedrock")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider(cfg)
