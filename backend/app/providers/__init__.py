from app.config import settings
from app.providers.base import Completion, ModelProvider, ProviderError
from app.providers.mock import MockProvider
from app.providers.qwen import QwenProvider


def get_provider() -> ModelProvider:
    if settings.provider_mode == "mock":
        if settings.app_env != "development" and settings.app_env != "test":
            raise ProviderError("MOCK_FORBIDDEN_IN_PRODUCTION")
        return MockProvider()
    if settings.provider_mode in ("live", "qwen"):
        return QwenProvider(settings)
    raise ProviderError("PROVIDER_CONFIGURATION_INVALID")


__all__ = ["Completion", "ModelProvider", "ProviderError", "get_provider"]
