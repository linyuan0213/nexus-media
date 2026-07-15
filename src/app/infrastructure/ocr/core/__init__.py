"""Public core API exports for image recognition."""

from app.infrastructure.ocr.core.exceptions import (
    ImageDecodeError,
    ProviderNotFoundError,
    ProviderUnavailableError,
    RecognitionError,
)
from app.infrastructure.ocr.core.registry import ProviderRegistry
from app.infrastructure.ocr.core.result import RecognitionResult
from app.infrastructure.ocr.core.task import RecognitionTask, TaskType

__all__ = [
    "TaskType",
    "RecognitionTask",
    "RecognitionResult",
    "ProviderRegistry",
    "RecognitionError",
    "ProviderNotFoundError",
    "ProviderUnavailableError",
    "ImageDecodeError",
]
