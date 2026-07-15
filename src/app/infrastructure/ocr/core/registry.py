"""Provider registry for image recognition."""

from typing import Any

from app.infrastructure.ocr.core.exceptions import ProviderNotFoundError, ProviderUnavailableError
from app.infrastructure.ocr.core.result import RecognitionResult
from app.infrastructure.ocr.core.task import RecognitionTask, TaskType


class ProviderRegistry:
    """Registry for recognition providers."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register(self, provider: Any) -> None:
        """Register a provider instance."""
        self._providers[provider.name] = provider

    def list_providers(self, task_type: TaskType | None = None) -> list[Any]:
        """Return providers, optionally filtered by supported task type."""
        providers = list(self._providers.values())
        if task_type is not None:
            providers = [p for p in providers if task_type in p.tasks]
        return providers

    def get(self, task: RecognitionTask) -> Any:
        """Select a provider for the given task."""
        task_type = task.task_type

        if task.provider:
            provider = self._providers.get(task.provider)
            if provider is None:
                raise ProviderNotFoundError(f"Provider '{task.provider}' not found")
            if task_type not in provider.tasks:
                raise ProviderNotFoundError(f"Provider '{task.provider}' does not support {task_type}")
            return self._ensure_available(provider)

        candidates = self.list_providers(task_type)
        if not candidates:
            raise ProviderNotFoundError(f"No provider supports {task_type}")

        return self._ensure_available(candidates[0])

    def _ensure_available(self, provider: Any) -> Any:
        if not provider.available:
            raise ProviderUnavailableError(f"Provider '{provider.name}' is not available (missing dependencies)")
        return provider

    def verify(self, task: RecognitionTask) -> RecognitionResult:
        """Route a task to the selected provider and return its result."""
        provider = self.get(task)
        return provider.verify(task)


__all__ = ["ProviderRegistry"]
