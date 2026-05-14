"""
消息中心搜索服务
处理 Telegram/WeChat/Slack 等消息渠道的搜索、下载、订阅、对话请求
"""

import os
import re

import log
from app.agent import ChatAgent
from app.media import MediaService, meta_info
from app.message import Message
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.indexer_service import IndexerService
from app.services.search_pagination import pagination_mgr
from app.services.search_service import Searcher
from app.services.subscribe_service import SubscribeService as Subscribe
from app.sites import Sites
from app.utils import StringUtils, Torrent
from app.utils.types import IndexerType, MediaType, RssType, SearchType
from app.utils.web_utils import WebUtils
from config import Config


class MessageSearchService:
    """消息中心搜索服务"""

    def __init__(self):
        self._downloader = Downloader()
        self._searcher = Searcher()
        self._indexer = IndexerService()

    def handle(self, input_str: str, in_from: SearchType, user_id: str, user_name: str | None = None):
        """处理消息中心输入"""
        if not input_str:
            return
        input_str = str(input_str).strip()

        # 分页导航
        if input_str.lower() in ("n", "p"):
            self._handle_pagination(input_str.lower(), in_from, user_id)
            return

        # 数字选择
        if input_str.isdigit() and int(input_str) < 10:
            self._handle_selection(int(input_str), in_from, user_id, user_name)
            return

        # 文本输入
        self._handle_text(input_str, in_from, user_id, user_name)

    def _handle_pagination(self, direction: str, in_from: SearchType, user_id: str):
        """处理分页导航"""
        if not pagination_mgr.has_page(user_id):
            Message().send_channel_msg(channel=in_from, title="没有可用的搜索结果分页", user_id=user_id)
            return

        result = pagination_mgr.navigate(user_id, direction)
        if result and "error" in result:
            Message().send_channel_msg(channel=in_from, title=result["error"], user_id=user_id)
            return

        pagination_mgr.send_page_message(in_from, user_id)

    def _handle_selection(self, choose: int, in_from: SearchType, user_id: str, user_name: str | None = None):
        """处理数字选择"""
        # 优先从分页缓存选择
        if pagination_mgr.has_page(user_id):
            self._select_from_pagination(choose, in_from, user_id, user_name)
            return

        # 从媒体缓存选择
        media_list = pagination_mgr.get_media_cache(user_id)
        if not media_list or choose < 1 or choose > len(media_list):
            Message().send_channel_msg(channel=in_from, title="输入有误！", user_id=user_id)
            log.warn(f"【Web】错误的输入值：{choose}")
            return

        media_info = media_list[choose - 1]
        media_type = pagination_mgr.get_media_type(user_id)

        if media_type == "SUBSCRIBE":
            self._add_rss(in_from, media_info, user_id=user_id, user_name=user_name)
        else:
            self._search_and_download(in_from, media_info, user_id, user_name)

    def _select_from_pagination(self, choose: int, in_from: SearchType, user_id: str, user_name: str | None = None):
        """从分页结果中选择下载"""
        item = pagination_mgr.select_item(user_id, choose)
        if not item:
            Message().send_channel_msg(channel=in_from, title="输入有误！", user_id=user_id)
            return

        if not item.ENCLOSURE:
            Message().send_channel_msg(channel=in_from, title="选中的资源没有种子链接，无法下载", user_id=user_id)
            return

        title = item.TITLE or item.TORRENT_NAME or "未知标题"
        year = item.YEAR or ""

        if item.TYPE == "MOV":
            mtype = MediaType.MOVIE
        elif item.TYPE == "TV":
            mtype = MediaType.TV
        elif item.TYPE == "ANI":
            mtype = MediaType.ANIME
        else:
            mtype = MediaType.UNKNOWN

        tmdb_info = None
        if item.TMDBID:
            tmdb_info = MediaService().get_tmdb_info(mtype=mtype, tmdbid=item.TMDBID)
        else:
            tmdb_info = MediaService().get_media_info(title=title, year=year, mtype=mtype)

        media_info = meta_info(title=f"{title} {year}".strip(), mtype=mtype)
        media_info.set_tmdb_info(tmdb_info)

        if not media_info or not media_info.tmdb_info:
            Message().send_channel_msg(channel=in_from, title=f"无法识别媒体信息: {title}", user_id=user_id)
            pagination_mgr.clear_media_cache(user_id)
            return

        media_info.enclosure = item.ENCLOSURE
        media_info.page_url = item.PAGEURL or ""
        media_info.site = item.SITE
        media_info.size = item.SIZE or 0
        media_info.org_string = item.TORRENT_NAME or title

        self._downloader.download(media_info=media_info, in_from=in_from, user_name=user_name)
        pagination_mgr.clear_media_cache(user_id)

    def _handle_text(self, input_str: str, in_from: SearchType, user_id: str, user_name: str | None = None):
        """处理文本输入"""
        # 判断意图
        intent = self._parse_intent(input_str)

        if intent == "DOWNLOAD":
            self._download_from_url(input_str, in_from, user_id, user_name)
        elif intent == "ASK":
            self._chat(input_str, in_from, user_id)
        elif intent == "SUBSCRIBE":
            content = re.sub(r"订阅[:：\s]*", "", input_str)
            self._search_media(in_from, content, user_id, user_name, "SUBSCRIBE")
        else:
            content = re.sub(r"(搜索|下载)[:：\s]*", "", input_str)
            self._search_media(in_from, content, user_id, user_name, "SEARCH")

    @staticmethod
    def _parse_intent(input_str: str) -> str:
        """解析用户意图"""
        if input_str.startswith(("http", "magnet")):
            return "DOWNLOAD"
        if ChatAgent().ready:
            return "ASK"
        if input_str.startswith("订阅"):
            return "SUBSCRIBE"
        return "SEARCH"

    def _download_from_url(self, url: str, in_from: SearchType, user_id: str, user_name: str | None = None):
        """从 URL 下载种子"""
        site_info = Sites().get_sites(siteurl=url)
        filepath, content, retmsg = Torrent().save_torrent_file(
            url=url, cookie=site_info.get("cookie"), ua=site_info.get("ua"), proxy=site_info.get("proxy") or False
        )
        if (not content or not filepath) and retmsg:
            Message().send_channel_msg(channel=in_from, title=retmsg, user_id=user_id)
            return

        filename = os.path.basename(filepath)
        meta_info = MediaService().get_media_info(title=filename)
        if not meta_info:
            Message().send_channel_msg(channel=in_from, title="无法识别种子文件名！", user_id=user_id)
            return

        meta_info.set_torrent_info(enclosure=url)
        self._downloader.download(media_info=meta_info, torrent_file=filepath, in_from=in_from, user_name=user_name)

    def _chat(self, question: str, in_from: SearchType, user_id: str):
        """AI 对话（支持工具调用）"""
        try:
            answer = ChatAgent().chat_with_tools(question=question, session_id=str(user_id))
        except Exception as e:
            log.error(f"【ChatAgent】对话异常: {e}")
            answer = "AI出错了，请检查LLM配置，如需搜索电影/电视剧，请发送 搜索或下载 + 名称"
        if not answer:
            answer = "AI出错了，请检查LLM配置，如需搜索电影/电视剧，请发送 搜索或下载 + 名称"
        Message().send_channel_msg(channel=in_from, title="", text=str(answer).strip(), user_id=user_id)

    def _search_media(
        self, in_from: SearchType, content: str, user_id: str, user_name: str | None = None, mtype: str = "SEARCH"
    ):
        """搜索媒体并展示结果"""
        indexer_type = self._indexer.get_client_type()
        indexers = self._indexer.get_indexers()

        # 解析站点和下载设置
        rss_sites, content = StringUtils.get_idlist_from_string(
            content,
            [{"id": site.get("name"), "name": site.get("name")} for site in Sites().get_sites(rss=True, public=True)],
        )

        if indexer_type == IndexerType.BUILTIN:
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

        log.info(f"【Web】正在识别 {content} 的媒体信息...")
        if not content:
            Message().send_channel_msg(channel=in_from, title="无法识别搜索内容！", user_id=user_id)
            return

        medias = WebUtils.search_media_infos(keyword=content)
        if not medias:
            Message().send_channel_msg(channel=in_from, title=f"{content} 查询不到媒体信息！", user_id=user_id)
            return

        media_list = []
        for media_info in medias[:8]:
            media_info.rss_sites = rss_sites
            media_info.search_sites = search_sites
            media_info.set_download_info(download_setting=download_setting)
            media_list.append(media_info)

        pagination_mgr.set_media_cache(user_id, media_list, mtype)

        if len(media_list) == 1:
            media_info = media_list[0]
            if mtype == "SUBSCRIBE":
                self._add_rss(in_from, media_info, user_id=user_id, user_name=user_name)
            else:
                if media_info.douban_id:
                    title = media_info.get_title_string()
                    media_info = MediaService().get_media_info(
                        title=f"{media_info.title} {media_info.year}", mtype=media_info.type, strict=True
                    )
                    if not media_info or not media_info.tmdb_info:
                        Message().send_channel_msg(
                            channel=in_from, title=f"{title} 从TMDB查询不到媒体信息！", user_id=user_id
                        )
                        return
                Message().send_channel_msg(
                    channel=in_from,
                    title=media_info.get_title_vote_string(),
                    text=media_info.get_overview_string(),
                    image=media_info.get_message_image(),
                    url=media_info.get_detail_url(),
                    user_id=user_id,
                )
                self._search_and_download(in_from, media_info, user_id, user_name)
        else:
            Message().send_channel_list_msg(
                channel=in_from,
                title=f"共找到{len(media_list)}条相关信息，请回复对应序号",
                medias=media_list,
                user_id=user_id,
            )

    def _search_and_download(self, in_from: SearchType, media_info, user_id: str, user_name: str | None = None):
        """搜索并下载媒体"""
        exist_flag, no_exists, messages = self._downloader.check_exists_medias(meta_info=media_info)
        if messages:
            Message().send_channel_msg(channel=in_from, title="\n".join(messages), user_id=user_id)
        if exist_flag:
            return

        Message().send_channel_msg(channel=in_from, title=f"开始搜索 {media_info.title} ...", user_id=user_id)
        search_result, no_exists, search_count, download_count = self._searcher.search_one_media(
            media_info=media_info,
            in_from=in_from,
            no_exists=no_exists,
            sites=media_info.search_sites,
            user_name=user_name,
        )

        if not search_count:
            Message().send_channel_msg(channel=in_from, title=f"{media_info.title} 未搜索到任何资源", user_id=user_id)
            return

        if download_count is None:
            # 未开启自动下载，进入分页选择模式
            self._enter_pagination_mode(in_from, media_info, user_id)
            return

        if download_count == 0:
            Message().send_channel_msg(
                channel=in_from,
                title=f"{media_info.title} 共搜索到{search_count}个结果，但没有下载到任何资源",
                user_id=user_id,
            )

        if not search_result and Config().get_config("pt").get("search_no_result_rss"):
            self._add_rss(in_from, media_info, user_id, state="R", user_name=user_name)

    def _enter_pagination_mode(self, in_from: SearchType, media_info, user_id: str):
        """进入搜索结果分页选择模式"""
        search_results = self._searcher.get_search_results()
        if not search_results:
            Message().send_channel_msg(
                channel=in_from, title=f"{media_info.title} 共搜索到结果，但无法获取结果列表", user_id=user_id
            )
            return

        pagination_mgr.set_search_results(user_id, search_results, media_info.title)
        pagination_mgr.send_page_message(in_from, user_id)

    @staticmethod
    def _add_rss(in_from, media_info, user_id=None, state="D", user_name=None):
        """添加订阅"""
        mediaid = f"DB:{media_info.douban_id}" if media_info.douban_id else media_info.tmdb_id
        code, msg, media_info = Subscribe().add_rss_subscribe(
            mtype=media_info.type,
            name=media_info.title,
            year=media_info.year,
            channel=RssType.Auto.value,
            season=media_info.begin_season,
            mediaid=mediaid,
            state=state,
            rss_sites=media_info.rss_sites,
            search_sites=media_info.search_sites,
            download_setting=media_info.download_setting,
            in_from=in_from,
            user_name=user_name,
        )
        if code == 0:
            log.info(f"【Web】{media_info.type.value} {media_info.get_title_string()} 已添加订阅")
        else:
            if in_from in Message().get_search_types():
                log.info(f"【Web】{media_info.title} 添加订阅失败：{msg}")
                Message().send_channel_msg(
                    channel=in_from, title=f"{media_info.title} 添加订阅失败：{msg}", user_id=str(user_id or "")
                )
