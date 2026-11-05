"""MessageBuilder - 业务消息构建与发送."""

import re
import threading
import time
from enum import Enum
from typing import Any

import log
from app.db.repositories.rbac.rbac_user_repo_adapter import RBACUserRepositoryAdapter
from app.domain.mediatypes import MediaType
from app.media.metadata.registry import registry as metadata_registry
from app.message.template_registry import message_template_registry
from app.schemas.auth import SUPERADMIN_ROLE_CODE
from app.services.subscription_context import resolve_subscription_context
from app.services.web import WebUtils
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils

_FAIL_NOTIFY_INTERVAL = 600
_fail_notify_cache: dict[str, float] = {}
_fail_notify_lock = threading.Lock()


def _should_notify_fail(key: str) -> bool:
    """失败通知去重：同一媒体+链接在间隔内只通知一次，避免重复刷屏."""
    now = time.monotonic()
    with _fail_notify_lock:
        last = _fail_notify_cache.get(key)
        if last is not None and now - last < _FAIL_NOTIFY_INTERVAL:
            return False
        _fail_notify_cache[key] = now
        return True


def _type_label(media_info, profile: str) -> str:
    """消息中的用户可见类型：普通媒体用电影/电视剧，扩展画像用插件标签."""
    if profile and profile != "default":
        label = message_template_registry.label(profile)
        if label:
            return label
        if profile.lower() in {"anime", "tv", "movie"}:
            return media_info.type.display_name
    return media_info.type.display_name


def _source_provider(item) -> str:
    """消息中的来源展示：优先真实 provider，聚合源回退到订阅备注的真实来源。"""
    provider = str(getattr(item, "provider", "") or getattr(item, "anchor_provider", "") or "").strip()
    metadata_ref = str(getattr(item, "metadata_ref", "") or "").strip()
    if (not provider or provider == "content_id") and ":" in metadata_ref:
        provider = metadata_ref.split(":", 1)[0].strip()
    desc = getattr(metadata_registry.get_provider(provider), "descriptor", None)
    provider_data = getattr(item, "provider_data", None)
    if isinstance(provider_data, dict):
        real_source = str(provider_data.get("source_provider") or "").strip()
        reusable = not provider or provider == "content_id" or desc is None
        if real_source and (reusable or getattr(desc, "virtual", False)):
            provider = real_source
            desc = getattr(metadata_registry.get_provider(provider), "descriptor", None)
    if not provider:
        return ""
    if provider == "content_id" and not metadata_ref:
        return "番号识别"
    if getattr(desc, "virtual", False):
        return "未知来源"
    return str(getattr(desc, "display_name", "") or provider)


def _message_variables(item, *, source_provider: str | None = None) -> dict[str, Any]:
    """订阅通知统一变量：来源、关键词与过滤条件，供插件模板消费。"""
    profile = str(getattr(item, "content_profile", "") or "default")
    source = source_provider if source_provider is not None else _source_provider(item)
    return {
        "content_profile": profile,
        "profile_label": message_template_registry.label(profile) or "",
        "type_label": _type_label(item, profile),
        "source_provider": source,
        "keyword": str(getattr(item, "keyword", "") or ""),
        "filter_restype": str(getattr(item, "filter_restype", "") or ""),
        "filter_pix": str(getattr(item, "filter_pix", "") or ""),
        "filter_team": str(getattr(item, "filter_team", "") or ""),
        "filter_rule": getattr(item, "filter_rule", None),
        "filter_include": str(getattr(item, "filter_include", "") or ""),
        "filter_exclude": str(getattr(item, "filter_exclude", "") or ""),
        "filter_free": bool(getattr(item, "filter_free", False)),
    }


class MessageBuilder:
    """负责各类业务场景的消息内容构建和发送."""

    def __init__(self, client_manager, dispatcher, messagecenter, template_engine=None):
        self._client_manager = client_manager
        self._dispatcher = dispatcher
        self._messagecenter = messagecenter
        self._template_engine = template_engine

    def _send_admin_msg(
        self,
        title: str,
        text: str,
        url: str | None = None,
        image: str | None = None,
        msg_type: str | None = None,
        variables: dict | None = None,
    ) -> bool:
        """系统/人工介入类事件定向推送给超级管理员（Web + 其绑定渠道）.

        返回是否有管理员被通知；无管理员时退化为全局系统消息。
        """
        try:
            admin_ids = RBACUserRepositoryAdapter().get_user_ids_by_role_code(SUPERADMIN_ROLE_CODE)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Message]查询管理员失败: {e}")
            admin_ids = []
        if not admin_ids:
            if self._messagecenter:
                self._insert_system_message(msg_type, variables, title, text)
            return False
        for uid in admin_ids:
            self._dispatcher.send_user_msg(
                uid,
                title,
                text,
                image=image,
                url=url,
                msg_type=msg_type,
                variables=variables,
                template_engine=self._template_engine,
            )
        return True

    def send_download_message(self, in_from, can_item, download_setting_name=None, downloader_name=None) -> None:
        self._enrich_from_subscription(can_item)
        msg_title = f"⬇️ {can_item.get_title_ep_string()} 开始下载"
        msg_text = f"{can_item.get_star_string()}"
        msg_text = f"{msg_text}\n📥 来自：{StringUtils.resolve_in_from_display(in_from)}"
        message_image = can_item.get_message_image() if hasattr(can_item, "get_message_image") else ""
        log.debug(f"[MessageBuilder]下载消息图片: {message_image}")
        if download_setting_name:
            msg_text = f"{msg_text}\n⚙️ 下载设置：{download_setting_name}"
        if downloader_name:
            msg_text = f"{msg_text}\n🖥️ 下载器：{downloader_name}"
        if can_item.user_name:
            msg_text = f"{msg_text}\n👤 用户：{can_item.user_name}"
        if can_item.site:
            if StringUtils.resolve_in_from_display(in_from) == "自定义订阅":
                msg_text = f"{msg_text}\n📌 任务：{can_item.site}"
            else:
                msg_text = f"{msg_text}\n🌐 站点：{can_item.site}"
        if can_item.get_resource_type_string():
            msg_text = f"{msg_text}\n📦 质量：{can_item.get_resource_type_string()}"
        if can_item.size:
            if str(can_item.size).isdigit():
                size = StringUtils.str_filesize(can_item.size)
            else:
                size = can_item.size
            msg_text = f"{msg_text}\n💾 大小：{size}"
        if can_item.org_string:
            msg_text = f"{msg_text}\n🎬 种子：{can_item.org_string}"
        if can_item.seeders:
            msg_text = f"{msg_text}\n做种数：{can_item.seeders}"
        msg_text = f"{msg_text}\n促销：{can_item.get_volume_factor_string()}"
        if can_item.hit_and_run:
            msg_text = f"{msg_text}\nHit&Run：是"
        if can_item.description:
            html_re = re.compile(r"<[^>]+>", re.S)
            description = html_re.sub("", can_item.description)
            can_item.description = re.sub(r"<[^>]+>", "", description)
            msg_text = f"{msg_text}\n描述：{can_item.description}"
        size_str = StringUtils.str_filesize(can_item.size) if can_item.size else ""
        description_clean = ""
        if can_item.description:
            description_clean = re.sub(r"<[^>]+>", "", can_item.description)
        variables = {
            "item": can_item,
            "in_from": StringUtils.resolve_in_from_display(in_from),
            "download_setting_name": download_setting_name or "",
            "downloader_name": downloader_name or "",
            "title": can_item.title or can_item.get_name() or "",
            "year": can_item.year or "",
            "season": can_item.get_season_string() if hasattr(can_item, "get_season_string") else "",
            "episode": can_item.get_episode_string() if hasattr(can_item, "get_episode_string") else "",
            "site": can_item.site or "",
            "size": can_item.size or 0,
            "size_str": size_str,
            "seeders": can_item.seeders or 0,
            "peers": can_item.peers or 0,
            "org_string": can_item.org_string or "",
            "description": description_clean,
            "description_raw": can_item.description or "",
            "resource_type": can_item.get_resource_type_string()
            if hasattr(can_item, "get_resource_type_string")
            else "",
            "volume_factor": can_item.get_volume_factor_string()
            if hasattr(can_item, "get_volume_factor_string")
            else "未知",
            "hit_and_run": can_item.hit_and_run or False,
            "user_name": can_item.user_name or "",
            "page_url": can_item.page_url or "",
            "vote_average": can_item.vote_average or 0,
            "star_string": can_item.get_star_string() if hasattr(can_item, "get_star_string") else "",
            "title_ep_string": can_item.get_title_ep_string() if hasattr(can_item, "get_title_ep_string") else "",
            "title_string": can_item.get_title_string() if hasattr(can_item, "get_title_string") else "",
            **_message_variables(can_item),
        }
        # 归属用户的下载事件：定向推送（Web + 绑定渠道），不广播全局外部渠道（ADR-021 5.6）
        owner_user_id = getattr(can_item, "user_id", None)
        if owner_user_id:
            self._dispatcher.send_user_msg(
                owner_user_id,
                msg_title,
                msg_text,
                image=message_image,
                url="downloading",
                msg_type="download_start",
                variables=variables,
                template_engine=self._template_engine,
            )
            return
        self._insert_system_message("download_start", variables, msg_title, msg_text)
        for client in self._client_manager.active_clients:
            if "download_start" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_text,
                    image=message_image,
                    url="downloading",
                    msg_type="download_start",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def _insert_system_message(self, msg_type, variables, title, text):
        if self._messagecenter is None:
            return
        title, text = self._render_system_message(msg_type, variables, title, text)
        self._messagecenter.insert_system_message(title=title, content=text)

    def _render_system_message(self, msg_type, variables, title, text):
        """Web 系统消息同样应用插件/渠道模板，避免退化为手写纯文本."""
        if self._template_engine is None:
            return title, text
        tpl_title, tpl_text = self._template_engine.apply_client_template(
            {},
            msg_type,
            variables,
            content_profile=str((variables or {}).get("content_profile") or ""),
        )
        return tpl_title or title, tpl_text or text

    def send_transfer_movie_message(self, in_from, media_info, exist_filenum, category_flag) -> None:
        self._enrich_from_subscription(media_info)
        msg_title = f"✅ {media_info.get_title_string()} 已入库"
        profile = str(getattr(media_info, "content_profile", "") or "default")
        type_label = _type_label(media_info, profile)
        if media_info.vote_average:
            msg_str = f"{media_info.get_vote_string()}，类型：{type_label}"
        else:
            msg_str = f"类型：{type_label}"
        if media_info.category:
            if category_flag:
                msg_str = f"{msg_str}，类别：{media_info.category}"
        if media_info.get_resource_type_string():
            msg_str = f"{msg_str}，质量：{media_info.get_resource_type_string()}"
        msg_str = (
            f"{msg_str}，大小：{StringUtils.str_filesize(media_info.size)}，"
            f"来自：{StringUtils.resolve_in_from_display(in_from)}"
        )
        if exist_filenum != 0:
            msg_str = f"{msg_str}，{exist_filenum}个文件已存在"
        variables = {
            "media_info": media_info,
            "in_from": StringUtils.resolve_in_from_display(in_from),
            "exist_filenum": exist_filenum,
            "category_flag": category_flag,
            **_message_variables(media_info),
        }
        # 归属用户的入库事件：定向推送（ADR-021 5.6）
        owner_user_id = getattr(media_info, "user_id", None)
        if owner_user_id:
            self._dispatcher.send_user_msg(
                owner_user_id,
                msg_title,
                msg_str,
                image=media_info.get_message_image(),
                url="history",
                msg_type="transfer_finished",
                variables=variables,
                template_engine=self._template_engine,
            )
            return
        self._insert_system_message("transfer_finished", variables, msg_title, msg_str)
        for client in self._client_manager.active_clients:
            if "transfer_finished" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url="history",
                    msg_type="transfer_finished",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_transfer_tv_message(
        self, message_medias: dict, in_from: Enum, exist_filenum: int = 0, category_flag: bool = False
    ) -> None:
        for item_info in message_medias.values():
            self._enrich_from_subscription(item_info)
            if item_info.total_episodes == 1:
                msg_title = f"✅ {item_info.get_title_string()} {item_info.get_season_episode_string()} 已入库"
            else:
                msg_title = (
                    f"✅ {item_info.get_title_string()} {item_info.get_season_string()} "
                    f"共{item_info.total_episodes}集 已入库"
                )
            if item_info.vote_average:
                msg_str = f"{item_info.get_vote_string()}，类型：{item_info.type.display_name}"
            else:
                msg_str = f"类型：{item_info.type.display_name}"
            if item_info.category:
                msg_str = f"{msg_str}，类别：{item_info.category}"
            from_source = f"，来自：{StringUtils.resolve_in_from_display(in_from)}"
            if item_info.total_episodes == 1:
                msg_str = f"{msg_str}，大小：{StringUtils.str_filesize(item_info.size)}{from_source}"
            else:
                msg_str = f"{msg_str}，总大小：{StringUtils.str_filesize(item_info.size)}{from_source}"
            variables = {
                "media_info": item_info,
                "in_from": StringUtils.resolve_in_from_display(in_from),
                "exist_filenum": exist_filenum,
                "category_flag": category_flag,
                "total_episodes": item_info.total_episodes if hasattr(item_info, "total_episodes") else 1,
                "season_episode": item_info.get_season_episode_string()
                if hasattr(item_info, "get_season_episode_string")
                else "",
                **_message_variables(item_info),
            }
            # 归属用户的入库事件：定向推送（ADR-021 5.6）
            owner_user_id = getattr(item_info, "user_id", None)
            if owner_user_id:
                self._dispatcher.send_user_msg(
                    owner_user_id,
                    msg_title,
                    msg_str,
                    image=item_info.get_message_image(),
                    url="history",
                    msg_type="transfer_finished",
                    variables=variables,
                    template_engine=self._template_engine,
                )
                continue
            self._insert_system_message("transfer_finished", variables, msg_title, msg_str)
            for client in self._client_manager.active_clients:
                if "transfer_finished" in (client.get("switches") or ""):
                    self._dispatcher.sendmsg(
                        client=client,
                        title=msg_title,
                        text=msg_str,
                        image=item_info.get_message_image(),
                        url="history",
                        msg_type="transfer_finished",
                        variables=variables,
                        template_engine=self._template_engine,
                    )

    @staticmethod
    def _format_season_episode(item) -> str:
        """生成季集标识；单集条目缺失 E 编号时用 get_episode_list 兜底补齐."""
        tag = ""
        if hasattr(item, "get_season_episode_string"):
            tag = item.get_season_episode_string() or ""
        if "E" not in tag and hasattr(item, "get_episode_list"):
            episodes = item.get_episode_list() or []
            if episodes:
                seq = f"E{episodes[0]:02d}" if len(episodes) == 1 else f"E{episodes[0]:02d}-E{episodes[-1]:02d}"
                tag = f"{tag} {seq}".strip()
        if not tag and hasattr(item, "get_season_string"):
            tag = item.get_season_string() or ""
        return tag

    @staticmethod
    def _subscription_context(item):
        return resolve_subscription_context(item)

    def _enrich_from_subscription(self, item):
        """统一给下载/入库/完成消息补订阅名称、来源和海报."""
        subscription = self._subscription_context(item)
        if subscription is None:
            return None
        if not str(getattr(item, "poster_path", "") or ""):
            image = str(getattr(subscription, "image", "") or "")
            if image:
                item.poster_path = image
        desc = str(getattr(subscription, "desc", "") or "")
        note = JsonUtils.loads(desc) if desc and JsonUtils.is_valid_json(desc) else {}
        if not isinstance(note, dict):
            note = {}
        if not str(getattr(item, "poster_path", "") or ""):
            note_poster = str(note.get("poster") or "")
            if note_poster:
                item.poster_path = note_poster
        real_source = str(note.get("source_provider") or "").strip()
        if real_source:
            item.provider_data = {
                **(getattr(item, "provider_data", None) or {}),
                "source_provider": real_source,
            }
        provider = str(getattr(subscription, "provider", "") or "")
        if not str(getattr(item, "anchor_provider", "") or ""):
            anchor = str(getattr(subscription, "anchor_provider", "") or "")
            if anchor:
                item.anchor_provider = anchor
        if provider:
            item.provider = provider
        metadata_ref = str(getattr(subscription, "metadata_ref", "") or "")
        if metadata_ref:
            item.metadata_ref = metadata_ref
        if not getattr(item, "rssid", None):
            item.rssid = getattr(subscription, "id", None)
        if not str(getattr(item, "keyword", "") or ""):
            keyword = str(getattr(subscription, "keyword", "") or "")
            if keyword:
                item.keyword = keyword
        profile = str(getattr(subscription, "content_profile", "") or "")
        if profile:
            # 订阅画像优先于搜索条目的临时画像，避免普通番剧被按 AV 规则处理。
            item.content_profile = profile
        return subscription

    def send_download_fail_message(self, item, error_msg: str) -> None:
        subscription = self._enrich_from_subscription(item)
        # 同一订阅/同一媒体在短时间内只通知一次，避免 1080P、4K 等
        # 多个种子连续失败时刷屏。
        failure_key = str(getattr(item, "rssid", None) or getattr(item, "tmdb_id", None) or item.get_title_string())
        if not _should_notify_fail(f"download-fail:{failure_key}"):
            return
        if subscription is not None:
            subscription_image = str(getattr(subscription, "image", "") or "")
            if subscription_image and not str(getattr(item, "poster_path", "") or ""):
                item.poster_path = subscription_image
            if not getattr(item, "title", ""):
                item.title = getattr(subscription, "name", "") or item.title
        title = f"❌ {item.get_title_string()} {self._format_season_episode(item)} 添加下载任务失败".strip()
        site = getattr(item, "site", "") or ""
        org_string = getattr(item, "org_string", "") or ""
        enclosure = getattr(item, "enclosure", "") or ""
        subscription_line = ""
        if subscription is not None:
            source = _source_provider(subscription) or "未知"
            keyword = str(getattr(subscription, "keyword", "") or "").strip()
            subscription_line = (
                f"📺 订阅：{getattr(subscription, 'name', '')} (#{getattr(subscription, 'id', '')})\n"
                f"📡 来源：{source}\n"
            )
            if keyword:
                subscription_line += f"🔢 关键词：{keyword}\n"
        text = (
            f"{subscription_line}"
            f"🌐 站点：{site or '未知'}\n"
            f"🎬 种子：{org_string or '未知'}\n"
            f"🔗 链接：{enclosure or '无'}\n"
            f"❗ 原因：{error_msg}"
        )
        owner_user_id = getattr(item, "user_id", None)
        if owner_user_id:
            self._dispatcher.send_user_msg(
                owner_user_id,
                title,
                text,
                image=item.get_message_image(),
                msg_type="download_fail",
                variables={
                    "item": item,
                    "error_msg": error_msg,
                    **_message_variables(item),
                    "subscription": subscription,
                },
                template_engine=self._template_engine,
            )
            return
        # 无归属的失败事件 → 定向超级管理员
        variables = {
            "item": item,
            "error_msg": error_msg,
            **_message_variables(item),
            "subscription": subscription,
        }
        self._send_admin_msg(
            title,
            text,
            image=item.get_message_image(),
            msg_type="download_fail",
            variables=variables,
        )
        for client in self._client_manager.active_clients:
            if "download_fail" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=item.get_message_image(),
                    msg_type="download_fail",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_subscribe_success_message(self, in_from: Enum, media_info) -> None:
        self._enrich_from_subscription(media_info)
        if media_info.type == MediaType.MOVIE:
            msg_title = f"📌 {media_info.get_title_string()} 已添加订阅"
        else:
            msg_title = f"📌 {media_info.get_title_string()} {media_info.get_season_string()} 已添加订阅"
        profile = str(getattr(media_info, "content_profile", "") or "default")
        source = _source_provider(media_info)
        keyword = str(getattr(media_info, "keyword", "") or "").strip()
        msg_str = f"📺 类型：{_type_label(media_info, profile)}"
        if keyword:
            msg_str = f"{msg_str}\n🔢 关键词：{keyword}"
        if source:
            msg_str = f"{msg_str}\n📡 来源：{source}"
        if media_info.vote_average:
            msg_str = f"{msg_str}\n⭐ {media_info.get_vote_string()}"
        msg_str = f"{msg_str}\n📥 来自：{StringUtils.resolve_in_from_display(in_from)}"
        if media_info.user_name:
            msg_str = f"{msg_str}\n👤 用户：{media_info.user_name}"
        variables = {
            "media_info": media_info,
            "in_from": StringUtils.resolve_in_from_display(in_from),
            **_message_variables(media_info, source_provider=source),
        }
        # 归属用户的订阅事件：定向推送给该用户（Web + 绑定渠道），不广播到全局外部渠道（ADR-021 5.6）
        owner_user_id = getattr(media_info, "user_id", None)
        if owner_user_id:
            self._dispatcher.send_user_msg(
                owner_user_id,
                msg_title,
                msg_str,
                image=media_info.get_message_image(),
                url="movie_rss" if media_info.type == MediaType.MOVIE else "tv_rss",
                msg_type="rss_added",
                variables=variables,
                template_engine=self._template_engine,
            )
            return
        self._insert_system_message("rss_added", variables, msg_title, msg_str)
        for client in self._client_manager.active_clients:
            if "rss_added" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url="movie_rss" if media_info.type == MediaType.MOVIE else "tv_rss",
                    msg_type="rss_added",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_rss_finished_message(self, media_info, owner_user_id: int | None = None) -> None:
        self._enrich_from_subscription(media_info)
        profile = str(getattr(media_info, "content_profile", "") or "default")
        if owner_user_id is None:
            owner_user_id = getattr(media_info, "user_id", None)
        if media_info.over_edition:
            msg_title = f"🎉 {media_info.get_title_string()} {media_info.get_season_string()} 已完成洗版"
        else:
            msg_title = f"🎉 {media_info.get_title_string()} {media_info.get_season_string()} 已完成订阅"
        source = _source_provider(media_info)
        keyword = str(getattr(media_info, "keyword", "") or "").strip()
        msg_str = f"📺 类型：{_type_label(media_info, profile)}"
        if keyword:
            msg_str = f"{msg_str}\n🔢 关键词：{keyword}"
        if source:
            msg_str = f"{msg_str}\n📡 来源：{source}"
        if media_info.vote_average:
            msg_str = f"{msg_str}\n⭐ {media_info.get_vote_string()}"
        variables = {
            "media_info": media_info,
            "over_edition": media_info.over_edition if hasattr(media_info, "over_edition") else False,
            **_message_variables(media_info, source_provider=source),
        }
        # 归属用户的订阅完成事件：定向推送（ADR-021 5.6）
        if owner_user_id:
            self._dispatcher.send_user_msg(
                owner_user_id,
                msg_title,
                msg_str,
                image=media_info.get_message_image(),
                url="downloaded",
                msg_type="rss_finished",
                variables=variables,
                template_engine=self._template_engine,
            )
            return
        self._insert_system_message("rss_finished", variables, msg_title, msg_str)
        for client in self._client_manager.active_clients:
            if "rss_finished" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url="downloaded",
                    msg_type="rss_finished",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_site_signin_message(self, msgs: list) -> None:
        if not msgs:
            return
        title = "📊 站点签到"
        text = "\n".join(msgs)
        variables = {"msgs": msgs}
        self._insert_system_message("site_signin", variables, title, text)
        for client in self._client_manager.active_clients:
            if "site_signin" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    msg_type="site_signin",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_site_message(self, title=None, text=None) -> None:
        if not title:
            return
        title = f"📬 {title}"
        if not text:
            text = ""
        variables = {"title": title, "text": text}
        self._insert_system_message("site_message", variables, title, text)
        for client in self._client_manager.active_clients:
            if "site_message" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    msg_type="site_message",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_site_parse_health_message(self, title=None, text=None) -> None:
        """站点解析健康告警：独立开关 site_parse_health，与通用站点通知分开控制."""
        if not title:
            return
        title = f"🩺 {title}"
        if not text:
            text = ""
        variables = {"title": title, "text": text}
        self._insert_system_message("site_parse_health", variables, title, text)
        for client in self._client_manager.active_clients:
            if "site_parse_health" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    msg_type="site_parse_health",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_transfer_fail_message(self, path: str, count: int, text: str) -> None:
        if not path or not count:
            return
        title = f"❌ [{count} 个文件入库失败]"
        text = f"📁 源路径：{path}\n❗ 原因：{text}"
        # 失败/人工介入类事件定向给超级管理员（ADR-021 5.6），不再广播给所有用户
        variables = {"path": path, "count": count, "text": text}
        self._send_admin_msg(
            title,
            text,
            url="unidentification",
            msg_type="transfer_fail",
            variables=variables,
        )

    def send_auto_remove_torrents_message(self, title: str, text: str) -> None:
        if not title or not text:
            return
        variables = {"title": title, "text": text}
        self._insert_system_message("auto_remove_torrents", variables, title, text)
        for client in self._client_manager.active_clients:
            if "auto_remove_torrents" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="torrent_remove",
                    msg_type="auto_remove_torrents",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_brushtask_remove_message(self, title: str, text: str) -> None:
        if not title or not text:
            return
        title = f"🗑️ {title}"
        variables = {"title": title, "text": text}
        self._insert_system_message("brushtask_remove", variables, title, text)
        for client in self._client_manager.active_clients:
            if "brushtask_remove" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask",
                    msg_type="brushtask_remove",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_brushtask_added_message(self, title: str, text: str) -> None:
        if not title or not text:
            return
        title = f"🌊 {title}"
        variables = {"title": title, "text": text}
        self._insert_system_message("brushtask_added", variables, title, text)
        for client in self._client_manager.active_clients:
            if "brushtask_added" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask",
                    msg_type="brushtask_added",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_brushtask_pause_message(self, title: str, text: str) -> None:
        if not title or not text:
            return
        title = f"⏸️ {title}"
        variables = {"title": title, "text": text}
        self._insert_system_message("brushtask_pause", variables, title, text)
        for client in self._client_manager.active_clients:
            if "brushtask_pause" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask",
                    msg_type="brushtask_pause",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_mediaserver_message(self, event_info: dict, channel: Any, image_url: str | None) -> None:
        if not event_info or not channel:
            return
        _webhook_actions = {
            "library.new": "新入库",
            "system.webhooktest": "测试",
            "playback.start": "开始播放",
            "playback.stop": "停止播放",
            "user.authenticated": "登录成功",
            "user.authenticationfailed": "登录失败",
            "media.play": "开始播放",
            "media.stop": "停止播放",
            "PlaybackStart": "开始播放",
            "PlaybackStop": "停止播放",
            "item.rate": "标记了",
        }
        _webhook_images = {
            "Emby": "https://emby.media/notificationicon.png",
            "Plex": "https://www.plex.tv/wp-content/uploads/2022/04/new-logo-process-lines-gray.png",
            "Jellyfin": "https://play-lh.googleusercontent.com/SCsUK3hCCRqkJbmLDctNYCfehLxsS4ggD1ZPHIFrrAN1Tn9yhjmGMPep2D9lMaaa9eQi",
        }
        if not _webhook_actions.get(event_info.get("event") or ""):
            return
        item_type = event_info.get("item_type") or ""
        parsed = MediaType.from_string(item_type)
        action = _webhook_actions.get(event_info.get("event") or "<unknown>")
        if parsed in (MediaType.TV, MediaType.ANIME) or item_type == "show":
            message_title = f"{action}{MediaType.TV.display_name} {event_info.get('item_name')}"
        elif parsed == MediaType.MOVIE:
            message_title = f"{action}{MediaType.MOVIE.display_name} {event_info.get('item_name')}"
        elif event_info.get("item_type") == "AUD":
            message_title = f"{action}有声书 {event_info.get('item_name')}"
        else:
            message_title = f"{action}"
        message_texts = []
        if event_info.get("user_name"):
            message_texts.append(f"用户：{event_info.get('user_name')}")
        if event_info.get("device_name"):
            message_texts.append(f"设备：{event_info.get('client')} {event_info.get('device_name')}")
        if event_info.get("ip"):
            message_texts.append(f"位置：{event_info.get('ip')} {WebUtils.get_location(event_info.get('ip'))}")
        if event_info.get("percentage"):
            percentage = round(float(event_info.get("percentage") or 0), 2)
            message_texts.append(f"进度：{percentage}%")
        if event_info.get("overview"):
            message_texts.append(f"剧情：{event_info.get('overview')}")
        message_texts.append(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")
        if not image_url:
            image_url = _webhook_images.get(channel)
        message_content = "\n".join(message_texts)
        url = event_info.get("play_url") or ""
        variables = {
            "event_info": event_info,
            "channel": channel,
            "message_title": message_title,
            "message_content": message_content,
            "image_url": image_url,
            "url": url,
        }
        self._insert_system_message("mediaserver_message", variables, message_title, message_content)
        for client in self._client_manager.active_clients:
            if "mediaserver_message" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=message_title,
                    text=message_content,
                    image=image_url,
                    url=url,
                    msg_type="mediaserver_message",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_plugin_message(
        self, title: str, text: str | None = "", image: str | None = "", url: str | None = ""
    ) -> None:
        if not title:
            return
        variables = {"title": title, "text": text, "url": url, "image": image}
        self._insert_system_message("custom_message", variables, title, text)
        for client in self._client_manager.active_clients:
            if "custom_message" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url=url,
                    image=image,
                    msg_type="custom_message",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_custom_message(self, clients, title: str, text: str = "", image: str = "") -> None:
        if not title:
            return
        if not clients:
            return
        variables = {"title": title, "text": text, "image": image}
        self._insert_system_message("custom_message", variables, title, text)
        for client in self._client_manager.active_clients:
            if str(client.get("id")) in clients:
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=image,
                    msg_type="custom_message",
                    variables=variables,
                    template_engine=self._template_engine,
                )

    def send_user_statistics_message(self, msgs: list) -> None:
        if not msgs:
            return
        title = "站点数据统计"
        text = "\n".join(msgs)
        variables = {"msgs": msgs, "title": title, "text": text}
        self._insert_system_message("ptrefresh_date_message", variables, title, text)
        for client in self._client_manager.active_clients:
            if "ptrefresh_date_message" in (client.get("switches") or ""):
                self._dispatcher.sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    msg_type="ptrefresh_date_message",
                    variables=variables,
                    template_engine=self._template_engine,
                )
