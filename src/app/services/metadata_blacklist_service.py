"""识别黑名单服务."""

from typing import Any

from app.db.repositories.plugin_repo_adapter import MetadataBlacklistRepositoryAdapter
from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media.metadata.gateway import MetadataGateway
from app.media.parser._metainfo import meta_info


class MetadataBlacklistService:
    """按 provider + external_id 维护识别黑名单."""

    def __init__(
        self,
        metadata_gateway: MetadataGateway,
        metadata_blacklist_repo: Any = None,
    ):
        self._db = metadata_blacklist_repo or MetadataBlacklistRepositoryAdapter()
        self._metadata = metadata_gateway
        self._cache = get_cache_manager().get_or_create("metadata_blacklist", "memory", maxsize=1, ttl=300)

    def is_blacklisted(self, external_id, media_type=None, provider: str = "tmdb"):
        """检查 provider 引用是否在黑名单中."""
        return self._db.is_blacklisted(provider, external_id, media_type)

    def _get_cached_all_items(self):
        """带缓存的获取全部黑名单记录."""
        cached = self._cache.get("all")
        if cached is not None:
            return cached
        all_items = self._db.get_blacklist()
        self._cache.set("all", all_items)
        return all_items

    def get_blacklist(self, external_id=None, page=1, count=30, provider: str | None = None):
        """获取分页的黑名单记录."""
        all_items = self._get_cached_all_items()
        if provider:
            all_items = [item for item in all_items if str(item.PROVIDER) == str(provider)]
        if external_id:
            all_items = [item for item in all_items if str(item.EXTERNAL_ID) == str(external_id)]

        start = (page - 1) * count
        end = start + count
        formatted_items = []
        for item in all_items[start:end]:
            _mtype = MediaType.from_string(item.MEDIA_TYPE)
            formatted_items.append(
                {
                    "backdrop_path": item.BACKDROP_PATH,
                    "id": item.ID,
                    "media_type": _mtype.value,
                    "media_type_label": _mtype.display_name,
                    "note": item.NOTE,
                    "poster_path": item.POSTER_PATH,
                    "provider": item.PROVIDER,
                    "external_id": str(item.EXTERNAL_ID),
                    "title": item.TITLE,
                    "year": item.YEAR,
                }
            )
        return formatted_items, len(all_items)

    def add_to_blacklist(self, external_id, media_type="", provider: str = "tmdb"):
        """添加到黑名单；详情统一从 MetadataGateway 读取."""
        if not external_id:
            raise ValueError("external_id 不能为空")
        mtype = MediaType.from_string(media_type)
        info = self._metadata.details(provider, external_id, media_type=mtype)
        if not info:
            raise ValueError(f"元数据信息获取失败：provider={provider}, external_id={external_id}, type={media_type}")
        mi = meta_info(str(info.get("name") or info.get("title") or ""))
        mi.set_provider_data(info)
        self._db.insert_blacklist(
            provider=provider,
            external_id=external_id,
            title=mi.title,
            year=mi.year,
            media_type=media_type,
            poster_path=mi.poster_path,
            backdrop_path=mi.backdrop_path,
            note=str(mi.note),
        )
        self._cache.clear()

    def remove_from_blacklist(self, external_id, media_type=None, provider: str = "tmdb"):
        """从黑名单移除."""
        self._db.delete_blacklist(provider, external_id, media_type)
        self._cache.clear()

    def clear_blacklist(self, provider: str | None = None):
        """清空黑名单；provider 为空时清空全部."""
        self._db.clear_blacklist(provider)
        self._cache.clear()
