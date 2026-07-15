"""Abstract base class for image recognition providers."""

from abc import ABC, abstractmethod

from app.infrastructure.ocr.core.result import RecognitionResult
from app.infrastructure.ocr.core.task import RecognitionTask, TaskType


class Provider(ABC):
    """Base class for all image recognition providers."""

    name: str
    tasks: set[TaskType]

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the provider's dependencies are installed and usable."""

    @abstractmethod
    def verify(self, task: RecognitionTask) -> RecognitionResult:
        """Execute the recognition task."""
