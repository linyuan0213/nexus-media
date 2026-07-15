"""OCR 与图片识别模块."""

from app.infrastructure.ocr.core import (
    RecognitionResult,
    RecognitionTask,
    TaskType,
)
from app.infrastructure.ocr.engine import RecognitionEngine
from app.infrastructure.ocr.recognizer import OcrRecognizer

__all__ = ["OcrRecognizer", "RecognitionEngine", "TaskType", "RecognitionTask", "RecognitionResult"]
