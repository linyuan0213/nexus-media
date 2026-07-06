"""
索引器站点配置 Repository 适配器
将 IndexerSiteConfigRepository 的 ORM 操作适配为领域接口。
"""

from app.db.repositories.indexer_site_config_repository import IndexerSiteConfigRepository
from app.domain.entities.indexer_site_config import IndexerSiteConfigEntity
from app.domain.interfaces.indexer_site_config_repo import IIndexerSiteConfigRepository


class IndexerSiteConfigRepositoryAdapter(IIndexerSiteConfigRepository):
    """索引器站点配置仓储适配器"""

    def __init__(self, repo: IndexerSiteConfigRepository | None = None):
        self._repo = repo or IndexerSiteConfigRepository()

    def upsert_site(
        self,
        site_name: str,
        source: str,
        public: bool | None = None,
        enabled: bool | None = None,
        download_setting: int | None = None,
        default_settings: dict | None = None,
    ) -> None:
        self._repo.upsert_site(
            site_name=site_name,
            source=source,
            public=public,
            enabled=enabled,
            download_setting=download_setting,
            default_settings=default_settings,
        )

    def get_by_name(self, site_name: str) -> IndexerSiteConfigEntity | None:
        orm = self._repo.get_by_name(site_name)
        if orm is None:
            return None
        return IndexerSiteConfigEntity.from_orm(orm)

    def get_by_id(self, id: int | str) -> IndexerSiteConfigEntity | None:
        orm = self._repo.get_by_id(id)
        if orm is None:
            return None
        return IndexerSiteConfigEntity.from_orm(orm)

    def list_all(
        self, source: str | None = None, source_ne: str | None = None, enabled: bool | None = None
    ) -> list[IndexerSiteConfigEntity]:
        rows = self._repo.list_all(source=source, source_ne=source_ne, enabled=enabled)
        return [IndexerSiteConfigEntity.from_orm(r) for r in rows]

    def list_enabled_names(self, source: str | None = None) -> list[str]:
        return self._repo.list_enabled_names(source=source)

    def update_enabled(self, site_name: str, enabled: bool) -> None:
        self._repo.update_enabled(site_name=site_name, enabled=enabled)

    def delete_by_name(self, site_name: str) -> None:
        self._repo.delete_by_name(site_name)

    def update_download_setting(self, site_name: str, download_setting: int | None) -> None:
        self._repo.update_download_setting(site_name=site_name, download_setting=download_setting)

    def update_default_settings(self, site_name: str, default_settings: dict | None) -> None:
        self._repo.update_default_settings(site_name=site_name, default_settings=default_settings)

    def get_download_setting(self, site_name: str) -> str | None:
        entity = self.get_by_name(site_name)
        if entity and entity.enabled and entity.download_setting is not None:
            return str(entity.download_setting)
        return None

    def migrate_from_user_indexer_sites(self, user_indexer_sites: list[int], site_name_by_id: dict[int, str]) -> None:
        self._repo.migrate_from_user_indexer_sites(
            user_indexer_sites=user_indexer_sites,
            site_name_by_id=site_name_by_id,
        )
