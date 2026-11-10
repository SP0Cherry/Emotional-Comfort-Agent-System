import json
from types import SimpleNamespace

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.mock import MockProvider
from app.providers.qwen import QwenProvider, validate_embedding


def configuration(**changes):
    values = {"llm_model": "qwen-plus", "embedding_model": "text-embedding-v4", "embedding_dimensions": 1024,
              "dashscope_api_key": "test-key", "llm_base_url": "https://test.invalid/v1", "generation_timeout_seconds": 45}
    return SimpleNamespace(**(values | changes))


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data.encode("utf-8")

    async def __aiter__(self):
        # Every Chinese character and SSE boundary can split at transport bytes.
        for offset in range(0, len(self.data), 2):
            yield self.data[offset:offset+2]


async def test_qwen_buffers_utf8_ignores_reasoning_and_reads_usage_only_chunk():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        chunks = [
            {"model": "qwen-plus-actual", "choices": [{"delta": {"reasoning_content": "PRIVATE THOUGHT", "content": "您"}}]},
            {"choices": [{"delta": {"content": "好。"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
        ]
        body = ": heartbeat\n\n" + "".join("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, stream=FragmentedStream(body))

    provider = QwenProvider(configuration(), transport=httpx.MockTransport(handler))
    result = await provider.complete([{"role": "user", "content": "您好"}])
    assert result.text == "您好。"
    assert result.model == "qwen-plus-actual"
    assert result.usage == {"prompt_tokens": 12, "completion_tokens": 3}
    assert requests[0]["enable_thinking"] is False
    assert requests[0]["stream_options"]["include_usage"] is True
    await provider.close()


async def test_unknown_model_does_not_receive_unsupported_thinking_flag():
    def handler(request):
        assert "enable_thinking" not in json.loads(request.content)
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"}}],"usage":{}}\n\ndata: [DONE]\n\n')
    provider = QwenProvider(configuration(llm_model="another-model"), transport=httpx.MockTransport(handler))
    result = await provider.complete([{"role": "user", "content": "hello"}])
    assert result.usage is None
    await provider.close()


@pytest.mark.parametrize("status,code", [(429, "PROVIDER_RATE_LIMIT"), (503, "PROVIDER_HTTP_ERROR")])
async def test_provider_http_failures_are_sanitized(status, code):
    provider = QwenProvider(configuration(), transport=httpx.MockTransport(lambda request: httpx.Response(status, text="sensitive upstream body")))
    with pytest.raises(ProviderError) as error:
        await provider.complete([{"role": "user", "content": "hello"}])
    assert error.value.code == code
    assert "sensitive" not in str(error.value)
    await provider.close()


async def test_incomplete_stream_is_never_success():
    provider = QwenProvider(configuration(), transport=httpx.MockTransport(lambda request: httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')))
    with pytest.raises(ProviderError, match="PROVIDER_STREAM_INTERRUPTED"):
        await provider.complete([{"role": "user", "content": "hello"}])
    await provider.close()


@pytest.mark.parametrize("vector", [[0.1], [float("nan")] * 1024, [float("inf")] * 1024, [True] * 1024, [0.0] * 1024])
def test_embedding_shape_and_finite_values_are_validated(vector):
    with pytest.raises(ProviderError):
        validate_embedding(vector)


async def test_embedding_request_dimensions_and_model_are_explicit():
    def handler(request):
        data = json.loads(request.content)
        assert data == {"model": "text-embedding-v4", "input": ["喜欢京剧"], "dimensions": 1024, "encoding_format": "float"}
        return httpx.Response(200, json={"model": "text-embedding-v4", "data": [{"embedding": [0.25] * 1024}]})
    provider = QwenProvider(configuration(), transport=httpx.MockTransport(handler))
    assert len(await provider.embed("喜欢京剧")) == 1024
    await provider.close()


async def test_mock_is_deterministic_and_has_a_distinct_embedding_namespace():
    provider = MockProvider()
    first = await provider.embed("我喜欢京剧")
    assert first == await provider.embed("我喜欢京剧")
    assert len(first) == 1024
    assert provider.embedding_model != "text-embedding-v4"
    identity = await provider.complete([{"role": "user", "content": "你是谁？"}])
    assert "AI" in identity.text
    assert identity.usage is None
