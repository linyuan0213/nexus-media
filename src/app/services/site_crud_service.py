"""站点增删改业务."""

from typing import Any

import log
from app.domain.entities.site import SiteEntity
from app.domain.enums import SiteUseType
from app.schemas.site import SiteUpdateResultDTO
from app.utils.json_utils import JsonUtils


class SiteCrudService:
    """站点写入流程；依赖由门面在调用时传入，保持测试可替换性."""

    @staticmethod
    def delete_site(
        *,
        sites: Any,
        site_entity_repo: Any,
        indexer_site_config_repo: Any,
        tid: str | None,
    ) -> int | None:
        if not tid:
            return 0
        try:
            site = site_entity_repo.get_by_id(int(tid))
            if not site:
                return 0
            site_entity_repo.delete(int(tid))
            indexer_site_config_repo.upsert_site(site_name=site.name, source="builtin", enabled=False)
            sites.refresh()
            return 1
        except Exception:
            return 0

    @staticmethod
    def update_site(
        *,
        data: dict,
        sites: Any,
        site_entity_repo: Any,
        site_engine: Any,
        site_user_info: Any,
        indexer_site_config_repo: Any,
    ) -> SiteUpdateResultDTO:
        """新增或更新站点信息（使用领域实体 + ISiteRepository）"""
        tid = data.get("site_id")
        name = data.get("site_name")
        site_pri = data.get("site_pri")
        rssurl = data.get("site_rssurl")
        signurl = data.get("site_signurl")
        cookie = data.get("site_cookie")
        api_key = data.get("site_api_key")
        bearer_token = data.get("site_bearer_token")
        headers = data.get("site_headers")
        note = data.get("site_note")
        if isinstance(note, str):
            try:
                note = JsonUtils.loads(note)
            except Exception:
                note = {}
        note = note or {}
        api_credentials = note.pop("api_credentials", None)

        rss_enable = data.get("rss_enable")
        brush_enable = data.get("brush_enable")
        statistic_enable = data.get("statistic_enable")
        if any(v is not None for v in (rss_enable, brush_enable, statistic_enable)):
            # 基于现有 rss_uses 增量更新，只修改传入的开关，未传入的保持原样
            existing = site_entity_repo.get_by_id(int(tid)) if tid else None
            uses = list(existing.rss_uses or "") if existing else []
            has_auth = bool(cookie or headers or api_key or bearer_token)
            if rss_enable is not None:
                uses = [u for u in uses if u != SiteUseType.RSS.value]
                if rss_enable and rssurl:
                    uses.append(SiteUseType.RSS.value)
            if brush_enable is not None:
                uses = [u for u in uses if u != SiteUseType.BRUSH.value]
                if brush_enable and rssurl and has_auth:
                    uses.append(SiteUseType.BRUSH.value)
            if statistic_enable is not None:
                uses = [u for u in uses if u != SiteUseType.STATISTIC.value]
                if statistic_enable and (rssurl or signurl) and has_auth:
                    uses.append(SiteUseType.STATISTIC.value)
            rss_uses = "".join(uses)
        else:
            rss_uses = data.get("site_include")

        # 将 note 中的功能开关统一规范化为布尔值
        switch_keys = ("parse", "message", "chrome", "proxy", "subtitle", "tag", "public")
        for key in switch_keys:
            if key in note:
                value = note[key]
                if isinstance(value, str):
                    note[key] = value.strip().lower() in ("y", "yes", "true", "1")
                else:
                    note[key] = bool(value)

        if SiteCrudService.is_site_duplicate(site_entity_repo, name, tid):
            return SiteUpdateResultDTO(code=400, msg="站点名称重复")

        entity = SiteEntity(
            id=int(tid) if tid else 0,
            name=name or "",
            pri=int(site_pri) if site_pri else 0,
            rss_url=rssurl,
            sign_url=signurl,
            cookie=cookie,
            api_key=api_key,
            bearer_token=bearer_token,
            headers=headers,
            note=note or {},
            rss_uses=rss_uses,
        )

        if tid:
            existing = site_entity_repo.get_by_id(int(tid))
            if not existing:
                return SiteUpdateResultDTO(code=400, msg="站点不存在")
            # 部分更新：请求显式携带的字段用新值，未携带的保留存量（修复"维护编辑只发部分
            # 字段时 cookie/headers/api_key/bearer_token 被覆盖成 NULL 导致配置丢失"）
            explicit_fields: set[str] = set()
            for data_key, attr in (
                ("site_name", "name"),
                ("site_pri", "pri"),
                ("site_rssurl", "rss_url"),
                ("site_signurl", "sign_url"),
                ("site_cookie", "cookie"),
                ("site_api_key", "api_key"),
                ("site_bearer_token", "bearer_token"),
                ("site_headers", "headers"),
                ("site_note", "note"),
            ):
                if data.get(data_key) is not None:
                    explicit_fields.add(attr)
            if data.get("site_include") is not None or any(
                v is not None for v in (rss_enable, brush_enable, statistic_enable)
            ):
                explicit_fields.add("rss_uses")
            entity = SiteCrudService.merge_partial_update(existing, entity, explicit_fields)
            try:
                if api_credentials is not None:
                    site_entity_repo.update_with_credentials(entity, api_credentials)
                else:
                    site_entity_repo.update(entity)
                if name and name != existing.name and existing.name:
                    site_user_info.update_site_name(name, existing.name)
                sites.refresh()
                return SiteUpdateResultDTO(code=0)
            except Exception as e:
                log.error(f"[SiteService]更新站点失败: {e}")
                return SiteUpdateResultDTO(code=500, msg=str(e))
        else:
            if not site_engine.get_by_name(name or ""):
                return SiteUpdateResultDTO(code=400, msg="站点不存在于站点定义中，无法添加")
            try:
                site_entity_repo.insert(entity)
                if api_credentials:
                    inserted = site_entity_repo.list_by_name(name or "")
                    if inserted:
                        for profile, credential in (api_credentials or {}).items():
                            if isinstance(credential, dict):
                                site_entity_repo.upsert_site_api_credentials(
                                    int(inserted[0].id), str(profile), credential
                                )
                # 删除站点会保留一条 disabled 配置行；重新添加时必须重新启用。
                indexer_site_config_repo.upsert_site(
                    site_name=str(name or ""),
                    source="builtin",
                    enabled=True,
                )
                sites.refresh()
                return SiteUpdateResultDTO(code=0)
            except Exception as e:
                log.error(f"[SiteService]新增站点失败: {e}")
                return SiteUpdateResultDTO(code=500, msg=str(e))

    @staticmethod
    def update_cookie_ua(*, sites: Any, site_entity_repo: Any, siteid: int | str, cookie: str, ua: str) -> None:
        site_entity_repo.update_cookie_ua(int(siteid), cookie, ua)
        sites.refresh()

    @staticmethod
    def is_site_duplicate(site_entity_repo: Any, name: str | None, tid: str | None) -> bool:
        if not name:
            return False
        sites = site_entity_repo.list_by_name(name)
        return any(str(site.id) != str(tid or "") for site in sites)

    @staticmethod
    def merge_partial_update(existing, entity: SiteEntity, explicit_fields: set[str]) -> SiteEntity:
        """部分更新合并：显式携带的字段用实体新值，其余保留存量.

        修复：站点维护页只编辑部分字段时，未发送的 cookie/headers/api_key/
        bearer_token/rssurl/signurl/name 等不能被覆盖为空。
        """
        attrs = {
            "name",
            "pri",
            "rss_url",
            "sign_url",
            "cookie",
            "api_key",
            "bearer_token",
            "headers",
            "note",
            "rss_uses",
        }
        for attr in attrs - explicit_fields:
            setattr(entity, attr, getattr(existing, attr, None))
        return entity
