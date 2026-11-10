"""Buffered OpenAI-compatible Qwen HTTP adapter; never persists reasoning."""
import json
import math

import httpx

from app.providers.base import Completion, ProviderError


def validate_embedding(vector: object, dimensions: int = 1024) -> list[float]:
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise ProviderError("EMBEDDING_DIMENSION_INVALID")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
        raise ProviderError("EMBEDDING_VALUE_INVALID")
    if not any(vector):
        raise ProviderError("EMBEDDING_ZERO_VECTOR")
    return [float(v) for v in vector]


class QwenProvider:
    def __init__(self, settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.model = settings.llm_model
        self.embedding_model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        if not settings.dashscope_api_key or not settings.llm_base_url.startswith("https://"):
            raise ProviderError("PROVIDER_CONFIGURATION_INVALID")
        self.client = httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
            timeout=httpx.Timeout(settings.generation_timeout_seconds, connect=5),
            transport=transport,
        )

    async def complete(self, messages, *, purpose="generate", json_mode=False, max_tokens=256):
        body = {
            "model": self.model, "messages": messages,
            "temperature": 0.6 if purpose == "generate" else 0.0,
            "max_tokens": max_tokens, "stream": True,
            "stream_options": {"include_usage": True},
        }
        # Only this verified model family supports the configured non-thinking path.
        if self.model == "qwen-plus" or self.model.startswith("qwen-plus-"):
            body["enable_thinking"] = False
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        parts, usage, model, total_size = [], None, self.model, 0
        pending: list[str] = []
        finished = False

        def consume(data: str):
            nonlocal usage, model, total_size, finished
            if data == "[DONE]":
                finished = True
                return
            chunk = json.loads(data)
            if not isinstance(chunk, dict):
                raise ProviderError("PROVIDER_INVALID_RESPONSE")
            if "error" in chunk:
                raise ProviderError("PROVIDER_RESPONSE_ERROR")
            if chunk.get("model"):
                model = str(chunk["model"])
            if isinstance(chunk.get("usage"), dict) and chunk["usage"]:
                usage = chunk["usage"]  # Includes the choices=[] usage-only event.
            choices = chunk.get("choices") or []
            if not isinstance(choices, list):
                raise ProviderError("PROVIDER_INVALID_RESPONSE")
            if choices:
                choice = choices[0]
                if not isinstance(choice, dict):
                    raise ProviderError("PROVIDER_INVALID_RESPONSE")
                if choice.get("finish_reason") == "length":
                    raise ProviderError("PROVIDER_OUTPUT_TRUNCATED")
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    raise ProviderError("PROVIDER_INVALID_RESPONSE")
                value = delta.get("content")  # Deliberately ignore reasoning_content.
                if isinstance(value, str):
                    total_size += len(value)
                    if total_size > 16000:
                        raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                    parts.append(value)

        try:
            async with self.client.stream("POST", "chat/completions", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if len(line) > 131072:
                        raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                    if not line:
                        if pending:
                            consume("\n".join(pending))
                            pending.clear()
                        if finished:
                            break
                    elif line.startswith("data:"):
                        pending.append(line[5:].lstrip(" "))
                if pending and not finished:
                    consume("\n".join(pending))
            if not finished:
                raise ProviderError("PROVIDER_STREAM_INTERRUPTED")
            text = "".join(parts).strip()
            if not text:
                raise ProviderError("PROVIDER_EMPTY_RESPONSE")
            return Completion(text, model, usage)
        except httpx.HTTPStatusError as exc:
            raise ProviderError("PROVIDER_RATE_LIMIT" if exc.response.status_code == 429 else "PROVIDER_HTTP_ERROR") from None
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT") from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise ProviderError("PROVIDER_INVALID_RESPONSE") from None

    async def embed(self, text):
        try:
            response = await self.client.post("embeddings", json={
                "model": self.embedding_model, "input": [text],
                "dimensions": self.dimensions, "encoding_format": "float",
            })
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderError("PROVIDER_INVALID_RESPONSE")
            if payload.get("model", self.embedding_model) != self.embedding_model:
                raise ProviderError("EMBEDDING_MODEL_MISMATCH")
            return validate_embedding(payload["data"][0]["embedding"], self.dimensions)
        except httpx.HTTPStatusError as exc:
            raise ProviderError("PROVIDER_RATE_LIMIT" if exc.response.status_code == 429 else "PROVIDER_HTTP_ERROR") from None
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT") from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
            raise ProviderError("PROVIDER_INVALID_RESPONSE") from None

    async def close(self):
        await self.client.aclose()
