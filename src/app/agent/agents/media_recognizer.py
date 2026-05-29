"""媒体文件名识别 Agent"""

from pydantic import BaseModel

import log
from app.agent.prompts.media import MEDIA_BATCH_PROMPT, MEDIA_RECOGNITION_PROMPT
from app.core.settings import settings
from app.di import container


class MediaResult(BaseModel):
    """媒体识别结果"""

    title_en: str | None = None
    title_cn: str | None = None
    alternate_titles: list = []
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    end_season: int | None = None
    end_episode: int | None = None
    resolution: str | None = None
    source: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    language: list = []
    platform: str | None = None
    release_group: str | None = None
    format: str | None = None
    edition: str | None = None
    type: str | None = None


class BatchResult(BaseModel):
    """批量识别结果"""

    items: list[MediaResult] = []


class MediaRecognizer:
    """媒体文件名识别器 — 基于 LLM"""

    def __init__(self):
        self._svc = container.agent_service()

    @property
    def ready(self) -> bool:
        return self._svc.ready

    def recognize(self, filename: str) -> MediaResult | None:
        """识别单个文件名"""
        if not self.ready:
            return None
        log.info(f"[MediaRecognizer]识别单个文件名: {filename[:80]}...")
        result = self._svc.structured_chat(
            messages=[{"role": "user", "content": filename}],
            system_prompt=MEDIA_RECOGNITION_PROMPT,
            response_model=MediaResult,
        )
        if result and (result.title_en or result.title_cn):
            log.info(f"[MediaRecognizer]识别成功: cn={result.title_cn}, en={result.title_en}, type={result.type}")
        else:
            log.warn("[MediaRecognizer]识别失败或返回空结果")
        return result

    def recognize_batch(self, filenames: list[str], batch_size: int = 0) -> list[MediaResult | None]:
        """批量识别文件名"""
        if not self.ready:
            log.warn("[MediaRecognizer]批量识别失败：Provider 未就绪")
            return [None] * len(filenames)

        if batch_size <= 0:
            batch_size = (settings.get("agent") or {}).get("batch_size", 100)

        total = len(filenames)
        log.info(f"[MediaRecognizer]批量识别开始: {total} 条, batch_size={batch_size}")
        results: list[MediaResult | None] = []
        success_count = 0
        for i in range(0, total, batch_size):
            batch = filenames[i : i + batch_size]
            texts = "\n".join(f"[{j}] {f}" for j, f in enumerate(batch))
            prompt = (
                f"识别以下 {len(batch)} 个文件名，按原始顺序返回 JSON 数组。\n"
                f"每个元素对应一个文件名的识别结果。\n\n{texts}"
            )
            try:
                result = self._svc.structured_chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=MEDIA_BATCH_PROMPT,
                    response_model=BatchResult,
                )
                batch_results = result.items if result else []
                for j in range(len(batch)):
                    r = batch_results[j] if j < len(batch_results) else None
                    results.append(r)
                    if r and (r.title_en or r.title_cn):
                        success_count += 1
            except Exception as e:
                log.warn(f"[MediaRecognizer]Batch {i // batch_size + 1} 失败: {e}, fallback 单条识别")
                for f in batch:
                    try:
                        r = self.recognize(f)
                        results.append(r)
                        if r and (r.title_en or r.title_cn):
                            success_count += 1
                    except Exception:
                        results.append(None)
        log.info(f"[MediaRecognizer]批量识别完成: {success_count}/{total} 成功")
        return results
