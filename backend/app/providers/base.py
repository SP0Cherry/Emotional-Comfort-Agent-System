"""Provider contracts contain no database or application policy."""
from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: dict | None = None


class ModelProvider(Protocol):
    embedding_model: str

    async def complete(
        self, messages: list[dict[str, str]], *, purpose: str = "generate",
        json_mode: bool = False, max_tokens: int = 256,
    ) -> Completion: ...

    async def embed(self, text: str) -> list[float]: ...

    async def close(self) -> None: ...
