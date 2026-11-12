"""
消息中心搜索服务
处理 Telegram/WeChat/Slack 等消息渠道的搜索、下载、订阅、对话请求
"""

import os
import re
import time

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from app.domain.enums import SearchType, channel_key
from app.domain.interfaces.chat import ChatPort
from app.domain.media_types import ProviderMediaType, media_type_registry
from app.media import meta_info
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.media.metadata.registry import registry as metadata_registry
from app.media.service import MediaService
from app.message import Message
from app.message.formatter import dialect_for_channel, format_agent_message
from app.services.downloader_core import DownloaderCore
from app.services.indexer_service import IndexerService
from app.services.search_pagination import SearchPaginationManager
from app.services.search_service import Searcher
from app.services.subscribe_service import SubscribeService
from app.services.subscription_intent import resolve_subscription
from app.services.web.utils import search_media_infos
from app.sites.download.torrent import Torrent
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.utils import StringUtils


class MessageSearchService:
    """消息中心搜索服务"""

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        downloader: DownloaderCore,
        searcher: Searcher,
        indexer: IndexerService,
        site_cache: SiteCache,
        site_engine: SiteEngine,
        subscribe_service: SubscribeService,
        media_service: MediaService,
        agent_service: ChatPort,
        message: Message,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._downloader = downloader
        self._searcher = searcher
        self._indexer = indexer
        self._site_cache = site_cache
        self._site_engine = site_engine
        self._subscribe_service = subscribe_service
        self._media_service = media_service
        self._chat_port = agent_service
        self._message = message
        self._metadata_gateway = metadata_gateway
        self._pagination = SearchPaginationManager(message=message)
        self._pending_subscriptions: dict[str, dict] = {}

    def handle(
        self,
        input_str: str,
        in_from: SearchType,
        user_id: str,
        user_name: str | None = None,
        user_permissions: list[str] | None = None,
        bound_user_id: int | None = None,
    ):
        """处理消息中心输入（bound_user_id: IM 绑定解析出的系统用户 ID，用于数据归属）"""
        if not input_str:
            return
        input_str = str(input_str).strip()

        # 分页导航
        if input_str.lower() in ("n", "p"):
            self._handle_pagination(input_str.lower(), in_from, user_id)
            return

        # 数字选择
        if input_str.isdigit() and int(input_str) < 10:
            self._handle_selection(int(input_str), in_from, user_id, user_name, bound_user_id, user_permissions)
            return

        # 文本输入
        self._handle_text(input_str, in_from, user_id, user_name, user_permissions, bound_user_id)

    def _handle_pagination(self, direction: str, in_from: SearchType, user_id: str):
        """处理分页导航"""
        if not self._pagination.has_page(user_id):
            self._message.send_channel_msg(channel=in_from, title="没有可用的搜索结果分页", user_id=user_id)
            return

        result = self._pagination.navigate(user_id, direction)
        if result and "error" in result:
            self._message.send_channel_msg(channel=in_from, title=result["error"], user_id=user_id)
            return

        self._pagination.send_page_message(in_from, user_id)

    def _handle_selection(
        self,
        choose: int,
        in_from: SearchType,
        user_id: str,
        user_name: str | None = None,
        bound_user_id: int | None = None,
        user_permissions: list[str] | None = None,
    ):
        """处理数字选择"""
        pending = self._pending_subscriptions.get(user_id)
        if pending:
            if time.monotonic() - pending["created"] > 300:
                self._pending_subscriptions.pop(user_id, None)
            else:
                hits = pending["hits"]
                if choose < 1 or choose > len(hits):
                    self._message.send_channel_msg(channel=in_from, title="输入有误！", user_id=user_id)
                    return
                hit = hits[choose - 1]
                ref = hit.get("ref") or {}
                self._pending_subscriptions.pop(user_id, None)
                self._add_metadata_subscription(
                    in_from,
                    pending["provider"],
                    str(ref.get("external_id") or ""),
                    str(hit.get("title") or pending["query"]),
                    user_id,
                    bound_user_id=bound_user_id,
                    permissions=pending.get("permissions") or user_permissions,
                )
                return
        # 优先从分页缓存选择
        if self._pagination.has_page(user_id):
            self._select_from_pagination(choose, in_from, user_id, user_name, bound_user_id=bound_user_id)
            return

        # 从媒体缓存选择
        media_list = self._pagination.get_media_cache(user_id)
        if not media_list or choose < 1 or choose > len(media_list):
            self._message.send_channel_msg(channel=in_from, title="输入有误！", user_id=user_id)
            log.warn(f"[Web]错误的输入值：{choose}")
            return

        media_info = media_list[choose - 1]
        media_type = self._pagination.get_media_type(user_id)

        if media_type == "SUBSCRIBE":
            self._add_rss(in_from, media_info, user_id=user_id, user_name=user_name, bound_user_id=bound_user_id)
        else:
            self._search_and_download(in_from, media_info, user_id, user_name, bound_user_id=bound_user_id)

    def _select_from_pagination(
        self,
        choose: int,
        in_from: SearchType,
        user_id: str,
        user_name: str | None = None,
        bound_user_id: int | None = None,
    ):
        """从分页结果中选择下载（bound_user_id 为数据归属用户）"""
        item = self._pagination.select_item(user_id, choose)
        if not item:
            self._message.send_channel_msg(channel=in_from, title="输入有误！", user_id=user_id)
            return

        if not item.ENCLOSURE:
            self._message.send_channel_msg(channel=in_from, title="选中的资源没有种子链接，无法下载", user_id=user_id)
            return

        title = item.TITLE or item.TORRENT_NAME or "未知标题"
        year = item.YEAR or ""

        mtype = ProviderMediaType.from_value(item.TYPE)

        if self._metadata_gateway is None:
            self._message.send_channel_msg(channel=in_from, title="元数据网关不可用", user_id=user_id)
            return
        media_info = meta_info(title=f"{title} {year}".strip(), mtype=mtype)
        if item.TMDBID:
            media_info.set_provider_data(self._metadata_gateway.details("tmdb", item.TMDBID, media_type=mtype))
        else:
            resolved = self._metadata_gateway.resolve_by_title(f"{title} {year or ''}".strip(), media_type=mtype)
            if resolved is not None:
                media_info = resolved

        if not media_info or not media_info.provider_data:
            self._message.send_channel_msg(channel=in_from, title=f"无法识别媒体信息: {title}", user_id=user_id)
            self._pagination.clear_media_cache(user_id)
            return

        media_info.enclosure = item.ENCLOSURE
        media_info.page_url = item.PAGEURL or ""
        media_info.site = item.SITE
        media_info.size = item.SIZE or 0
        media_info.org_string = item.TORRENT_NAME or title

        self._downloader.download(media_info=media_info, in_from=in_from, user_name=user_name, user_id=bound_user_id)
        self._pagination.clear_media_cache(user_id)

    _METADATA_ALIASES = {
        "tmdb": "tmdb",
        "豆瓣": "douban",
        "douban": "douban",
        "bangumi": "bangumi",
        "bgm": "bangumi",
        "番组": "bangumi",
    }

    def _parse_metadata_subscription(self, text: str):
        """解析订阅语法：订阅 <provider> <标题> 或 <provider>:<id> [名称]。"""
        match = re.match(r"^(?:订阅|/rss)[:：\s]+([^\s:：]+)(?:\s*[:：]\s*(\S+)(?:\s+(.+))?|\s+(.+))?$", text)
        if not match:
            return None
        raw_provider = match.group(1).strip()
        provider = self._METADATA_ALIASES.get(raw_provider.lower()) or self._METADATA_ALIASES.get(raw_provider)
        if not provider and metadata_registry.get_provider(raw_provider):
            provider = raw_provider
        if not provider:
            return None
        external_id = (match.group(2) or "").strip()
        if external_id:
            name = (match.group(3) or external_id).strip()
            return provider, external_id, name, True
        title = (match.group(4) or "").strip()
        if not title:
            return None
        return provider, title, title, False

    def _subscribe_by_text(
        self,
        in_from: SearchType,
        provider: str,
        value: str,
        name: str,
        is_id: bool,
        user_id: str,
        bound_user_id=None,
        permissions=None,
    ) -> None:
        profile = self._profile_for_provider(provider)
        if profile != "default" and "metadata:private:view" not in set(permissions or []):
            self._message.send_channel_msg(
                channel=in_from, title="当前用户无 metadata:private:view 权限", user_id=user_id
            )
            return
        external_id = value
        title = name
        media_type = (
            media_type_registry.resolve_profile(profile) or media_type_registry.resolve(None, profile)
        ).content_type
        if not is_id and profile == "default":
            if self._metadata_gateway is None:
                self._message.send_channel_msg(channel=in_from, title="元数据服务未启用", user_id=user_id)
                return
            content_profile = profile
            context = MetadataContext(
                permissions=frozenset(permissions or ()),
                content_profile=content_profile,
                purpose="message",
                allow_private=False,
            )
            try:
                hits = self._metadata_gateway.search(
                    query=value,
                    context=context,
                    provider=provider,
                    media_type=media_type,
                    content_profile=content_profile,
                    limit=5,
                )
            except Exception as exc:  # noqa: BLE001
                self._message.send_channel_msg(channel=in_from, title=f"元数据搜索失败: {exc}", user_id=user_id)
                return
            if not hits:
                self._message.send_channel_msg(
                    channel=in_from, title=f"{value} 未找到 {provider} 元数据", user_id=user_id
                )
                return
            if len(hits) > 1:
                self._pending_subscriptions[user_id] = {
                    "created": time.monotonic(),
                    "provider": provider,
                    "query": value,
                    "hits": hits,
                    "permissions": set(permissions or []),
                }
                lines = []
                for index, item in enumerate(hits[:8], start=1):
                    year = f" ({item.get('year')})" if item.get("year") else ""
                    lines.append(f"{index}. {item.get('title') or item.get('name') or ''}{year}")
                self._message.send_channel_msg(
                    channel=in_from,
                    title="请选择订阅结果",
                    text="\n".join(lines) + "\n\n回复序号继续",
                    user_id=user_id,
                )
                return
            ref = hits[0].get("ref") or {}
            external_id = str(ref.get("external_id") or "").strip()
            title = str(hits[0].get("title") or name)
            if not external_id:
                self._message.send_channel_msg(channel=in_from, title="元数据结果缺少外部 ID", user_id=user_id)
                return
        self._add_metadata_subscription(
            in_from,
            provider,
            external_id,
            title,
            user_id,
            bound_user_id=bound_user_id,
            permissions=permissions,
        )

    @staticmethod
    def _profile_for_provider(provider: str) -> str:
        item = metadata_registry.get_provider(provider) if provider else None
        descriptor = getattr(item, "descriptor", None)
        profiles = {
            str(value)
            for value in getattr(descriptor, "content_profiles", frozenset())
            if str(value) and str(value) != "default"
        }
        return sorted(profiles)[0] if profiles else "default"

    def _add_metadata_subscription(
        self,
        in_from: SearchType,
        provider: str,
        external_id: str,
        name: str,
        user_id: str,
        bound_user_id=None,
        permissions=None,
    ):
        intent = resolve_subscription(provider, external_id, name)
        if intent is None:
            self._message.send_channel_msg(channel=in_from, title=f"未注册的元数据来源: {provider}", user_id=user_id)
            return
        code, msg, _ = self._subscribe_service.add_rss_subscribe(
            mtype=intent.media_type,
            name=intent.name,
            year=None,
            channel="auto",
            season=None,
            state="R",
            in_from=in_from,
            user_id=int(bound_user_id) if bound_user_id and str(bound_user_id).isdigit() else None,
            metadata_ref=intent.metadata_ref,
            metadata_policy=intent.metadata_policy,
            content_profile=intent.content_profile,
            keyword=intent.keyword,
            mediaid=intent.mediaid,
            allow_private=intent.allow_private,
            permissions=set(permissions or []),
        )
        if code != 0:
            self._message.send_channel_msg(channel=in_from, title=msg or "订阅失败", user_id=user_id)

    def _handle_text(
        self,
        input_str: str,
        in_from: SearchType,
        user_id: str,
        user_name: str | None = None,
        user_permissions: list[str] | None = None,
        bound_user_id: int | None = None,
    ):
        """处理文本输入"""
        metadata_subscribe = self._parse_metadata_subscription(input_str)
        if metadata_subscribe is not None:
            provider, value, name, is_id = metadata_subscribe
            self._subscribe_by_text(
                in_from,
                provider,
                value,
                name,
                is_id,
                user_id,
                bound_user_id=bound_user_id,
                permissions=user_permissions,
            )
            return
        # 判断意图
        intent = self._parse_intent(input_str)

        if intent == "DOWNLOAD":
            self._download_from_url(input_str, in_from, user_id, user_name)
        elif intent == "ASK":
            self._chat(input_str, in_from, user_id, user_permissions)
        elif intent == "SUBSCRIBE":
            content = re.sub(r"订阅[:：\s]*", "", input_str)
            if not content.strip():
                self._message.send_channel_msg(
                    channel=in_from, title="请输入要订阅的关键词，例如：订阅 进击的巨人", user_id=user_id
                )
                return
            self._search_media(in_from, content, user_id, user_name, "SUBSCRIBE", bound_user_id=bound_user_id)
        else:
            content = re.sub(r"/(rss|ssa)[\s:：]*", "", input_str)
            content = re.sub(r"(搜索|下载)[:：\s]*", "", content)
            if not content.strip():
                self._message.send_channel_msg(
                    channel=in_from,
                    title="请输入要搜索/订阅的关键词，例如：搜索 进击的巨人 或 订阅 进击的巨人",
                    user_id=user_id,
                )
                return
            self._search_media(in_from, content, user_id, user_name, "SEARCH", bound_user_id=bound_user_id)

    def _parse_intent(self, input_str: str) -> str:
        """解析用户意图"""
        if input_str.startswith(("http", "magnet")):
            return "DOWNLOAD"
        if self._chat_port.ready:
            return "ASK"
        if input_str.startswith("订阅"):
            return "SUBSCRIBE"
        return "SEARCH"

    def _download_from_url(self, url: str, in_from: SearchType, user_id: str, user_name: str | None = None):
        """从 URL 下载种子"""
        site_info: dict = self._site_cache.get_sites(siteurl=url)  # type: ignore[assignment]
        filepath, content, retmsg = Torrent(site_engine=self._site_engine).save_torrent_file(
            url=url,
            cookie=site_info.get("cookie"),
            api_key=site_info.get("api_key"),
            bearer_token=site_info.get("bearer_token"),
            ua=site_info.get("ua"),
            proxy=site_info.get("proxy") or False,
        )
        if (not content or not filepath) and retmsg:
            self._message.send_channel_msg(channel=in_from, title=retmsg, user_id=user_id)
            return

        filename = os.path.basename(filepath)
        if self._metadata_gateway is None:
            self._message.send_channel_msg(channel=in_from, title="元数据网关不可用", user_id=user_id)
            return
        meta_info = self._metadata_gateway.resolve_by_title(filename)
        if not meta_info:
            self._message.send_channel_msg(channel=in_from, title="无法识别种子文件名！", user_id=user_id)
            return

        meta_info.set_torrent_info(enclosure=url)
        self._downloader.download(media_info=meta_info, torrent_file=filepath, in_from=in_from, user_name=user_name)

    def _chat(self, question: str, in_from: SearchType, user_id: str, user_permissions: list[str] | None = None):
        """AI 对话（支持工具调用）"""
        try:
            answer = self._chat_port.chat_with_tools(
                question=question,
                session_id=str(user_id),
                channel=channel_key(in_from),
                user_id=str(user_id),
                user_permissions=user_permissions,
            )
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            log.error(f"[AgentChat]对话异常: {e}")
            answer = "AI出错了，请检查LLM配置，如需搜索电影/电视剧，请发送 搜索或下载 + 名称"
        if not answer:
            answer = "AI出错了，请检查LLM配置，如需搜索电影/电视剧，请发送 搜索或下载 + 名称"
        answer_text = format_agent_message(str(answer).strip(), dialect_for_channel(in_from))
        self._message.send_channel_msg(channel=in_from, title="", text=answer_text, user_id=user_id)

    def _search_media(
        self,
        in_from: SearchType,
        content: str,
        user_id: str,
        user_name: str | None = None,
        mtype: str = "SEARCH",
        bound_user_id: int | None = None,
    ):
        """搜索媒体并展示结果"""
        indexer_type = self._indexer.get_client_type()
        indexers = self._indexer.get_indexers()

        # 解析站点和下载设置
        rss_sites, content = StringUtils.get_idlist_from_string(
            content,
            [
                {"id": site.get("name"), "name": site.get("name")}
                for site in self._site_cache.get_sites(rss=True, public=True)
            ],
        )

        if indexer_type == "builtin":
            search_sites = []
        else:
            search_sites, content = StringUtils.get_idlist_from_string(
                content, [{"id": indexer.name, "name": indexer.name} for indexer in indexers]
            )

        download_settings = self._downloader.get_download_setting().values()
        download_setting, content = StringUtils.get_idlist_from_string(
            content, [{"id": dl.get("id"), "name": dl.get("name")} for dl in download_settings]
        )
        if download_setting:
            download_setting = download_setting[0]

        log.info(f"[Web]正在识别 {content} 的媒体信息...")
        if not content:
            self._message.send_channel_msg(channel=in_from, title="无法识别搜索内容！", user_id=user_id)
            return

        medias = search_media_infos(keyword=content)
        if not medias:
            self._message.send_channel_msg(channel=in_from, title=f"{content} 查询不到媒体信息！", user_id=user_id)
            return

        media_list = []
        for media_info in medias[:8]:
            media_info.rss_sites = rss_sites
            media_info.search_sites = search_sites
            media_info.set_download_info(download_setting=download_setting)
            media_list.append(media_info)

        self._pagination.set_media_cache(user_id, media_list, mtype)

        if len(media_list) == 1:
            media_info = media_list[0]
            if mtype == "SUBSCRIBE":
                self._add_rss(in_from, media_info, user_id=user_id, user_name=user_name)
            else:
                if media_info.douban_id:
                    title = media_info.get_title_string()
                    if self._metadata_gateway is None:
                        self._message.send_channel_msg(channel=in_from, title="元数据网关不可用", user_id=user_id)
                        return
                    media_info = self._metadata_gateway.resolve_by_title(
                        f"{media_info.title} {media_info.year}", media_type=media_info.type, strict=True
                    )
                    if not media_info or not media_info.provider_data:
                        self._message.send_channel_msg(
                            channel=in_from, title=f"{title} 从TMDB查询不到媒体信息！", user_id=user_id
                        )
                        return
                self._message.send_channel_msg(
                    channel=in_from,
                    title=media_info.get_title_vote_string(),
                    text=media_info.get_overview_string(),
                    image=media_info.get_message_image(),
                    url=media_info.get_detail_url(),
                    user_id=user_id,
                )
                self._search_and_download(in_from, media_info, user_id, user_name, bound_user_id=bound_user_id)
        else:
            self._message.send_channel_list_msg(
                channel=in_from,
                title=f"共找到{len(media_list)}条相关信息，请回复对应序号",
                medias=media_list,
                user_id=user_id,
            )

    def _search_and_download(
        self,
        in_from: SearchType,
        media_info,
        user_id: str,
        user_name: str | None = None,
        bound_user_id: int | None = None,
    ):
        """搜索并下载媒体"""
        exist_flag, no_exists, messages = self._downloader.check_exists_medias(meta_info=media_info)
        if messages:
            self._message.send_channel_msg(channel=in_from, title="\n".join(messages), user_id=user_id)
        if exist_flag:
            return

        self._message.send_channel_msg(channel=in_from, title=f"开始搜索 {media_info.title} ...", user_id=user_id)
        search_result, no_exists, search_count, download_count = self._searcher.search_one_media(
            media_info=media_info,
            in_from=in_from,
            no_exists=no_exists,
            sites=media_info.search_sites,
            user_name=user_name,
            user_id=bound_user_id,
        )

        if not search_count:
            self._message.send_channel_msg(
                channel=in_from, title=f"{media_info.title} 未搜索到任何资源", user_id=user_id
            )
            return

        if download_count is None:
            # 未开启自动下载，进入分页选择模式
            self._enter_pagination_mode(in_from, media_info, user_id)
            return

        if download_count == 0:
            self._message.send_channel_msg(
                channel=in_from,
                title=f"{media_info.title} 共搜索到{search_count}个结果，但没有下载到任何资源",
                user_id=user_id,
            )

        if not search_result and settings.get("pt").get("search_no_result_rss"):
            self._add_rss(in_from, media_info, user_id, state="R", user_name=user_name, bound_user_id=bound_user_id)

    def _enter_pagination_mode(self, in_from: SearchType, media_info, user_id: str):
        """进入搜索结果分页选择模式"""
        search_results = self._searcher.get_search_results()
        if not search_results:
            self._message.send_channel_msg(
                channel=in_from, title=f"{media_info.title} 共搜索到结果，但无法获取结果列表", user_id=user_id
            )
            return

        self._pagination.set_search_results(user_id, search_results, media_info.title)
        self._pagination.send_page_message(in_from, user_id)

    def _add_rss(self, in_from, media_info, user_id=None, state="D", user_name=None, bound_user_id=None):
        """添加订阅（bound_user_id 为数据归属用户）"""
        ref = media_info.get_media_ref()
        mediaid = f"{ref.provider}:{ref.external_id}" if ref else None
        code, msg, media_info = self._subscribe_service.add_rss_subscribe(
            mtype=media_info.type,
            name=media_info.title,
            year=media_info.year,
            channel="auto",
            season=media_info.begin_season,
            mediaid=mediaid,
            metadata_ref=mediaid,
            content_profile=media_info.content_profile,
            state=state,
            rss_sites=media_info.rss_sites,
            search_sites=media_info.search_sites,
            download_setting=media_info.download_setting,
            in_from=in_from,
            user_name=user_name,
            user_id=bound_user_id,
        )
        if code == 0:
            log.info(f"[Web]{media_info.type.value} {media_info.get_title_string()} 已添加订阅")
        else:
            if channel_key(in_from) in self._message.get_search_types():
                log.info(f"[Web]{media_info.title} 添加订阅失败：{msg}")
                self._message.send_channel_msg(
                    channel=in_from, title=f"{media_info.title} 添加订阅失败：{msg}", user_id=str(user_id or "")
                )
