"""匹配链：按插件优先级执行 MatchProfile，未命中回退内置类型推断."""

from __future__ import annotations

from app.domain.media_types import ProviderMediaType
from app.media.parser.unified.type_inferrer import infer_type
from app.media.parser.unified.types import ParseContext

from .models import Detection, MatchResult
from .registry import MetadataRegistry
from .registry import registry as global_registry

CONFIDENCE_THRESHOLD = 0.85


class LegacyMatchProfile:
    """内置兜底：复用现有 infer_type，保证旧识别结果不变."""

    key = "default"
    content_profile = "default"
    base_media_type = ProviderMediaType.SERIES
    priority = 0

    def detect(self, ctx: ParseContext) -> Detection:
        return Detection(
            content_profile="default",
            confidence=0.5,
            base_media_type=infer_type(ctx),
        )

    def match(self, parsed: object, ctx: object) -> MatchResult:
        return MatchResult(content_profile="default")


class MatchChain:
    """插件 profile 优先，内置 profile 兜底."""

    def __init__(
        self,
        *,
        registry: MetadataRegistry | None = None,
        threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self._registry = registry or global_registry
        self._threshold = threshold

    def detect(self, ctx: object) -> Detection | None:
        profiles = [profile for profile in self._registry.list_profiles("match") if getattr(profile, "detect", None)]
        if not profiles:
            return None
        profiles.sort(key=lambda profile: getattr(profile, "priority", 0), reverse=True)
        for profile in profiles:
            try:
                detection = profile.detect(ctx)
            except Exception:  # noqa: BLE001 - 单个插件 profile 失败不影响通用解析
                continue
            if detection is None:
                continue
            if detection.confidence >= self._threshold:
                return detection
        return None

    def match(self, profile_key: str, parsed: object, ctx: object) -> MatchResult | None:
        profile = self._registry.get_profile("match", profile_key)
        if profile is None:
            return None
        return profile.match(parsed, ctx)
