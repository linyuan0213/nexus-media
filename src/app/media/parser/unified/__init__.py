"""统一解析引擎主入口"""

from __future__ import annotations

from app.domain.media_types import ProviderMediaType
from app.media.metadata.matching import MatchChain
from app.media.metadata.parsing import ParserChain
from app.media.parser.base import BaseParser, ParserResult

from .match_profiles import ensure_builtin_match_profiles
from .name_extractor import clean_names, extract_name
from .preprocessor import prepare_title
from .rules import get_rule_engine
from .type_inferrer import infer_type
from .types import ParseContext


class UnifiedParser(BaseParser):
    """统一标题解析器 — 合并动漫/影视两条管线"""

    def __init__(
        self,
        match_chain: MatchChain | None = None,
        parser_chain: ParserChain | None = None,
    ) -> None:
        self._engine = get_rule_engine()
        ensure_builtin_match_profiles()
        self._match_chain = match_chain or MatchChain()
        self._parser_chain = parser_chain or ParserChain()

    def parse(self, title: str, subtitle: str = "") -> ParserResult | None:
        if not title:
            return None

        # Phase 0: 插件 ParserProfile 高置信度短路
        profile_result = self._parser_chain.extract(title, subtitle)
        if profile_result is not None:
            return profile_result

        # Phase 1: 预处理
        prepared = prepare_title(title)

        # Phase 2: 元素提取
        ctx = ParseContext(text=prepared)
        self._engine.apply(ctx)

        # Phase 3: 名称提取
        extract_name(ctx, title)
        clean_names(ctx)

        # Phase 4: 类型推断：插件 MatchProfile 高置信度优先，否则走旧规则
        detection = self._match_chain.detect(ctx) if self._match_chain else None
        media_type = detection.base_media_type if detection and detection.base_media_type else infer_type(ctx)
        content_profile = detection.content_profile if detection else "default"

        # Phase 5: 组装结果
        return self._build_result(ctx, media_type, title, content_profile=content_profile, detection=detection)

    def _build_result(
        self,
        ctx: ParseContext,
        media_type: ProviderMediaType,
        original: str,
        *,
        content_profile: str = "",
        detection=None,
    ) -> ParserResult:
        confidence = self._calculate_confidence(ctx)
        season, end_season = self._to_int_pair(ctx.season)
        episode, end_episode = self._to_int_pair(ctx.episode)

        return ParserResult(
            title_en=ctx.en_name,
            title_cn=ctx.cn_name,
            year=ctx.year,
            season=season,
            end_season=end_season,
            episode=episode,
            end_episode=end_episode,
            resource_pix=ctx.resolution,
            resource_type=ctx.source,
            video_encode=ctx.video_codec,
            audio_encode=ctx.audio_codec,
            resource_team=ctx.resource_team or ctx.release_group,
            type=media_type,
            confidence=confidence,
            org_string=original,
            content_profile=content_profile or ("anime" if media_type == ProviderMediaType.ANIME else "default"),
            anchor_provider=getattr(getattr(detection, "anchor_hint", None), "provider", None),
            anchor_external_id=getattr(getattr(detection, "anchor_hint", None), "external_id", None),
        )

    def _calculate_confidence(self, ctx: ParseContext) -> float:
        if not ctx.elements:
            return 0.3
        total = sum(e.confidence for e in ctx.elements)
        avg = total / len(ctx.elements)
        # 有名称时提升置信度
        if ctx.cn_name or ctx.en_name:
            avg = min(avg + 0.1, 0.98)
        return round(avg, 2)

    def _to_int_pair(self, value: int | list[int] | None) -> tuple[int | None, int | None]:
        if value is None:
            return None, None
        if isinstance(value, list):
            if len(value) == 1:
                return value[0], None
            return value[0], value[-1]
        return value, None
