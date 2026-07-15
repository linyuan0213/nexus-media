"""OCR 验证码识别 facade."""

from typing import Any

from app.infrastructure.ocr.core import RecognitionResult, RecognitionTask, TaskType
from app.infrastructure.ocr.core.exceptions import RecognitionError
from app.infrastructure.ocr.engine import RecognitionEngine
from app.infrastructure.ocr.utils import fetch_image_b64


class OcrRecognizer:
    """High-level recognizer backed by the nexus-verify remote engine."""

    def __init__(self, engine: RecognitionEngine | None = None) -> None:
        self._engine = engine or RecognitionEngine()

    def get_captcha_text(
        self,
        image_url: str | None = None,
        image_b64: str | None = None,
        cookie: str | None = None,
        ua: str | None = None,
    ) -> str:
        """
        根据图片地址或 base64，识别验证码内容。

        :param image_url: 图片地址
        :param image_b64: 图片 base64，若提供则跳过下载
        :param cookie: 下载图片使用的 cookie
        :param ua: 下载图片使用的 User-Agent
        """
        if not image_b64 and image_url:
            image_b64 = fetch_image_b64(image_url, cookie=cookie, ua=ua)

        if not image_b64:
            return ""

        task = RecognitionTask(task_type=TaskType.CAPTCHA, image_b64=image_b64)
        try:
            result = self._engine.verify(task)
        except RecognitionError:
            return ""
        return result.text or ""

    def recognize(
        self,
        task: RecognitionTask | dict[str, Any],
        cookie: str | None = None,
        ua: str | None = None,
    ) -> RecognitionResult:
        """Execute an arbitrary recognition task."""
        if isinstance(task, dict):
            task = RecognitionTask.model_validate(task)
        if not task.image_b64 and task.image_url:
            task.image_b64 = fetch_image_b64(task.image_url, cookie=cookie, ua=ua)
        return self._engine.verify(task)
