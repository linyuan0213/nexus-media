"""Result models for image recognition tasks."""

from typing import Any

from pydantic import BaseModel


class RecognitionResult(BaseModel):
    """Result returned by a recognition provider."""

    success: bool = True
    text: str | None = None
    points: list[tuple[int, int]] | None = None
    distance: int | None = None
    angle: int | None = None
    confidence: float | None = None
    raw: dict[str, Any] | None = None

    model_config = {"extra": "allow"}
