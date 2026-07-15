"""Remote provider that delegates recognition to a nexus-verify service."""

from app.core.settings import settings
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.ocr.core.exceptions import ProviderUnavailableError, RecognitionError
from app.infrastructure.ocr.core.result import RecognitionResult
from app.infrastructure.ocr.core.task import RecognitionTask, TaskType
from app.infrastructure.ocr.providers.base import Provider


class RemoteProvider(Provider):
    """Provider that calls a nexus-verify compatible HTTP service."""

    name = "remote"
    tasks = {
        TaskType.CAPTCHA,
        TaskType.CLICK_CAPTCHA,
        TaskType.IMAGE_CLICK_CAPTCHA,
        TaskType.SLIDE_CAPTCHA,
        TaskType.ROTATE_CAPTCHA,
        TaskType.GAP_MATCH,
        TaskType.TEXT_OCR,
    }

    def __init__(self, base_url: str | None = None) -> None:
        if base_url is None:
            lab = settings.get("laboratory") or {}
            if not lab.get("ocr_enabled", True):
                base_url = ""
            else:
                base_url = lab.get("ocr_server_host") or ""
        base_url = base_url.rstrip("/") if base_url else ""
        self._base_url = base_url
        self._verify_url = f"{base_url}/verify" if base_url else None

    @property
    def available(self) -> bool:
        return bool(self._base_url)

    def verify(self, task: RecognitionTask) -> RecognitionResult:
        """Send the task to the remote service and parse the result."""
        if not self._verify_url:
            raise ProviderUnavailableError("Remote OCR server host is not configured")

        payload = task.model_dump(exclude_none=True)
        with HttpClient(config=HttpClientConfig(default_headers={"Content-Type": "application/json"})) as client:
            response = client.post(self._verify_url, json=payload)

        data = response.json()
        code = data.get("code", 0)
        if code != 0:
            raise RecognitionError(data.get("message", "Remote recognition failed"), code=code)

        result_data = (data.get("data") or {}).get("result") or {}
        return RecognitionResult(**result_data)
