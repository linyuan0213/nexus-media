"""Image recognition engine."""

from app.infrastructure.ocr.core import ProviderRegistry, RecognitionResult, RecognitionTask
from app.infrastructure.ocr.providers import default_providers


class RecognitionEngine:
    """High-level engine that routes recognition tasks to providers."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()
        if not self.registry._providers:
            for provider in default_providers():
                self.registry.register(provider)

    def verify(self, task: RecognitionTask) -> RecognitionResult:
        """Route and execute a recognition task."""
        return self.registry.verify(task)

    def providers(self) -> list[dict[str, str | list[str] | bool]]:
        """Return metadata for all registered providers."""
        return [
            {
                "name": p.name,
                "tasks": [t.value for t in p.tasks],
                "available": p.available,
            }
            for p in self.registry.list_providers()
        ]
