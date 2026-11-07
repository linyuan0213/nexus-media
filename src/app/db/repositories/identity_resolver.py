"""统一媒体身份解析（仓储层实现）.

所有写入 SEARCH_RESULT_INFO / DOWNLOAD_HISTORY / TRANSFER_HISTORY /
MEDIA_LIFECYCLE 的链路都必须通过本解析器获取 IDENTITY_ID，避免各写各的兜底。

放在仓储层是为了让 Repository 只依赖同层组件与 domain/utils，不反向依赖 services。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.domain.media_ref import MediaRef
from app.utils.identity import fallback_identity


@dataclass(frozen=True)
class ResolvedIdentity:
    identity_id: str
    provider: str = ""
    external_id: str = ""
    content_profile: str = "default"
    identity: Any = None


class IdentityResolver:
    """身份解析唯一入口：显式身份 → 外部引用 → 标题/年份/类型 → 新建 → 兜底."""

    def __init__(self, repository: Any | None = None):
        self._repo = repository or MediaIdentityRepository()

    @staticmethod
    def _normalize_type(media_type: Any) -> str:
        value = str(media_type or "").strip().lower()
        if not value:
            return "unknown"
        return "tv" if value == "anime" else value

    @staticmethod
    def _media_season(media: Any) -> int:
        if hasattr(media, "get_season_seq"):
            try:
                return int(media.get_season_seq() or 0)
            except (TypeError, ValueError):
                return 0
        try:
            return int(getattr(media, "season", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def resolve_media(
        self,
        media: Any,
        *,
        allow_local: bool = True,
        create: bool = True,
    ) -> ResolvedIdentity:
        media_type = getattr(getattr(media, "type", None), "value", getattr(media, "type", "movie"))
        provider = getattr(media, "anchor_provider", None)
        external_id = getattr(media, "anchor_external_id", None)
        if not (provider and external_id):
            ref = media.get_media_ref() if hasattr(media, "get_media_ref") else None
            if isinstance(ref, MediaRef) and ref.provider and ref.external_id:
                provider = ref.provider
                external_id = ref.external_id
        return self.resolve_values(
            identity_id=getattr(media, "identity_id", None),
            provider=provider,
            external_id=external_id,
            title=getattr(media, "title", None),
            year=getattr(media, "year", None),
            media_type=media_type,
            content_profile=getattr(media, "content_profile", None),
            season=self._media_season(media),
            allow_local=allow_local,
            create=create,
        )

    def ensure_media(self, media: Any, *, create: bool = True) -> ResolvedIdentity:
        """解析并把规范身份回写到媒体对象；执行边界统一调用此方法."""
        identity_id = str(getattr(media, "identity_id", None) or "").strip()
        if identity_id:
            return ResolvedIdentity(
                identity_id=identity_id,
                provider=str(getattr(media, "anchor_provider", "") or ""),
                external_id=str(getattr(media, "anchor_external_id", "") or ""),
                content_profile=str(getattr(media, "content_profile", "") or "default"),
            )
        resolved = self.resolve_media(media, create=create)
        if resolved.identity_id:
            media.identity_id = resolved.identity_id
            if not getattr(media, "anchor_provider", None) and resolved.provider:
                media.anchor_provider = resolved.provider
            if not getattr(media, "anchor_external_id", None) and resolved.external_id:
                media.anchor_external_id = resolved.external_id
        return resolved

    def resolve_values(
        self,
        *,
        identity_id: Any = None,
        provider: Any = None,
        external_id: Any = None,
        title: Any = None,
        year: Any = None,
        media_type: Any = "movie",
        content_profile: Any = None,
        season: int = 0,
        scope: str = "default",
        allow_local: bool = True,
        create: bool = True,
    ) -> ResolvedIdentity:
        raw_type = str(media_type or "movie")
        ref_type = self._normalize_type(raw_type)
        provider_text = str(provider or "").strip()
        external_text = str(external_id or "").strip()
        profile = str(content_profile or "").strip() or "default"

        # 1. 显式 identity：local/preview 先清空；provider:external 直接按引用归一
        explicit = str(identity_id or "").strip()
        if explicit.startswith("local:") or explicit == "preview":
            explicit = ""
        elif explicit:
            prefix, separator, rest = explicit.partition(":")
            if separator and rest:
                found = self._repo.find_by_ref(prefix, rest, scope=scope, media_type=ref_type)
                if found is not None:
                    return self._result(found, provider_text or prefix, external_text or rest, profile)
                # 引用尚未落库：保留 provider/external 线索，继续走标题/新建流程，
                # 避免为同一作品创建第二个影子身份。
                provider_text = provider_text or prefix
                external_text = external_text or rest
            else:
                getter = getattr(self._repo, "get_identity", None)
                found = getter(explicit) if callable(getter) else None
                if found is None and create:
                    found = self._repo.ensure_identity(
                        identity_id=explicit,
                        media_type=ref_type,
                        content_profile=profile,
                        title=str(title or "") or None,
                        year=str(year or "") or None,
                    )
                if found is not None:
                    return self._result(found, provider_text, external_text, profile)

        # 2. 外部引用
        if provider_text and external_text:
            found = self._repo.find_by_ref(provider_text, external_text, scope=scope, media_type=ref_type)
            if found is not None:
                return self._result(found, provider_text, external_text, profile)

        # 2.5 跨 provider 同编号：内容锚点和真实 provider 引用必须归到同一身份
        if provider_text and external_text:
            finder = getattr(self._repo, "find_by_external_id", None)
            found: Any = finder(external_text, media_type=ref_type) if callable(finder) else None
            if found is not None:
                if create:
                    try:
                        self._repo.upsert_ref(
                            found.IDENTITY_ID,
                            provider=provider_text,
                            external_id=external_text,
                            media_type=ref_type,
                            scope=scope,
                            link_method="identity_resolver",
                        )
                    except ValueError:
                        pass
                return self._result(found, provider_text, external_text, profile)

        # 3. 标题/年份/类型族（动漫与剧集同族）
        title_text = str(title or "").strip()
        if title_text and (allow_local or (provider_text and external_text)):
            finder = getattr(self._repo, "find_by_title", None)
            found = finder(title_text, str(year or "") or None, ref_type) if callable(finder) else None
            if found is not None:
                if provider_text and external_text:
                    try:
                        self._repo.upsert_ref(
                            found.IDENTITY_ID,
                            provider=provider_text,
                            external_id=external_text,
                            media_type=ref_type,
                            link_method="identity_resolver",
                        )
                    except ValueError:
                        pass
                return self._result(found, provider_text, external_text, profile)

        # 4. 有 anchor 时创建规范身份（content_id 也作为 provider ref）
        if create and provider_text and external_text:
            creator = getattr(self._repo, "ensure_identity_for_ref", None)
            if not callable(creator):
                identity = self._repo.ensure_identity(
                    media_type=raw_type,
                    content_profile=profile,
                    title=title_text or None,
                    year=str(year or "") or None,
                )
                return self._result(identity, provider_text, external_text, profile)
            created = creator(
                provider_text,
                external_text,
                media_type=raw_type,
                scope=scope,
                content_profile=profile,
                title=title_text or None,
                year=str(year or "") or None,
            )
            if created:
                getter = getattr(self._repo, "get_identity", None)
                found = getter(created) if callable(getter) else None
                if found is not None:
                    return self._result(found, provider_text, external_text, profile)

        # 5. 仅历史/任务类记录允许本地兜底；搜索结果不创建 local
        if allow_local and (title_text or provider_text or external_text):
            local_id = fallback_identity(
                title_text,
                raw_type,
                int(season or 0),
                provider_text,
                external_text,
            )
            return ResolvedIdentity(
                identity_id=local_id,
                provider=provider_text,
                external_id=external_text,
                content_profile=profile,
            )

        return ResolvedIdentity("", provider_text, external_text, profile)

    def _result(
        self,
        identity: Any,
        provider: str,
        external_id: str,
        content_profile: str,
    ) -> ResolvedIdentity:
        resolved_provider = provider
        resolved_external = external_id
        if not resolved_provider:
            getter: Any = getattr(self._repo, "get_primary_ref", None)
            ref: Any = getter(identity.IDENTITY_ID) if callable(getter) else None
            if ref is not None:
                resolved_provider = str(ref.PROVIDER or "")
                resolved_external = resolved_external or str(ref.EXTERNAL_ID or "")
        profile = str(content_profile or "default")
        return ResolvedIdentity(
            identity_id=str(identity.IDENTITY_ID),
            provider=resolved_provider,
            external_id=resolved_external,
            content_profile=profile,
            identity=identity,
        )
