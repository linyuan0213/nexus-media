"""
DoubanSync Plugin v2
同步豆瓣在看、想看、看过记录，自动添加订阅或搜索下载
"""

import contextlib
import json
import random
from datetime import datetime
from threading import Lock
from time import sleep

from app.media import DouBan, meta_info
from app.plugin_framework.context import PluginContext
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.search_service import Searcher
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils.types import MediaType, RssType, SearchType
from app.utils.web_utils import WebUtils

_lock = Lock()


class DoubanSyncPlugin:
    """豆瓣同步插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._douban = DouBan()
        self._searcher = Searcher()
        self._downloader = Downloader()
        self._subscribe = Subscribe()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("豆瓣同步插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("豆瓣同步插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()
        elif event == "media.douban_sync":
            self._sync()

    def run(self):
        """立即运行同步"""
        self.ctx.info("手动触发豆瓣同步")
        self._sync()

    def _start_service(self):
        config = self._get_config()
        enable = config.get("enable", False)
        if not enable:
            return

        sync_type = config.get("sync_type", "0")
        interval = config.get("interval", 0)
        rss_interval = config.get("rss_interval", 0)

        if sync_type == "0" and interval and int(interval) > 0:
            self.ctx.info(f"豆瓣全量同步服务启动，周期：{interval} 小时")
            self.ctx.schedule_interval(
                "sync_full",
                self._sync,
                hours=int(interval),
            )
        elif sync_type == "1" and rss_interval and int(rss_interval) > 0:
            sec = int(rss_interval)
            if sec < 300:
                sec = 300
            self.ctx.info(f"豆瓣近期动态同步服务启动，周期：{sec} 秒")
            self.ctx.schedule_interval(
                "sync_rss",
                self._sync,
                seconds=sec,
            )

    def _stop_service(self):
        for job_id in ["sync_full", "sync_rss", "sync_once"]:
            with contextlib.suppress(Exception):
                self.ctx.remove_schedule(job_id)

    def _is_enabled(self) -> bool:
        config = self._get_config()
        return bool(config.get("enable", False) and config.get("users") and config.get("types"))

    def _sync(self):
        with _lock:
            self._do_sync()

    def _do_sync(self):
        config = self._get_config()
        users = config.get("users", "")
        types = config.get("types", "")
        sync_type = config.get("sync_type", "0")
        days = config.get("days", 0)
        config.get("cookie", "")
        auto_search = config.get("auto_search", False)
        auto_rss = config.get("auto_rss", False)

        if not users or not types:
            self.ctx.info("豆瓣配置：用户ID或同步类型未配置")
            return

        user_list = users.split(",") if isinstance(users, str) else users
        type_list = types.split(",") if isinstance(types, str) else types

        self.ctx.info(f"同步方式：{'近期动态' if sync_type == '1' else '全量同步'}")

        douban_ids = {}

        for user in user_list:
            if not user:
                continue

            userinfo = self._douban.get_user_info(userid=user)
            if not userinfo:
                self.ctx.warn(f"用户名获取失败，请检查豆瓣ID {user} 是否正确")
                continue

            user_name = userinfo.get("name", "")

            if sync_type != "1":
                self._sync_full_user(user, user_name, type_list, days, douban_ids)
            else:
                self._sync_rss_user(user, user_name, type_list, days, douban_ids)

        self.ctx.info(f"所有用户解析完成，共获取到 {len(douban_ids)} 个媒体")

        # 查询豆瓣详情并处理
        for doubanid, info in douban_ids.items():
            self._process_douban_media(doubanid, info, auto_search, auto_rss)

        self.ctx.info("豆瓣数据同步完成")

    def _sync_full_user(self, user, user_name, type_list, days, douban_ids):
        perpage = 15
        for mtype in type_list:
            if not mtype:
                continue
            self.ctx.info(f"开始获取 {user_name or user} 的 {mtype} 数据...")
            start = 0
            while True:
                page = int(start / perpage + 1)
                self.ctx.debug(f"开始解析第 {page} 页数据...")
                try:
                    items = self._douban.get_douban_wish(dtype=mtype, userid=user, start=start, wait=True)
                    if not items:
                        self.ctx.warn(f"第 {page} 页未获取到数据")
                        break

                    continue_next = True
                    for item in items:
                        date = item.get("date")
                        if not date:
                            continue_next = False
                            break
                        mark_date = datetime.strptime(date, "%Y-%m-%d")
                        if days and int(days) > 0:
                            if (datetime.now() - mark_date).days >= int(days):
                                continue_next = False
                                break

                        doubanid = item.get("id")
                        if str(doubanid).isdigit():
                            self.ctx.info(f"解析到媒体：{doubanid}")
                            if doubanid not in douban_ids:
                                douban_ids[doubanid] = {"user_name": user_name}

                    if not continue_next:
                        break
                    start += perpage
                except Exception as e:
                    self.ctx.error(f"{user_name or user} 第 {page} 页解析出错：{e}")
                    break

    def _sync_rss_user(self, user, user_name, type_list, days, douban_ids):
        all_items = self._douban.get_latest_douban_interests(dtype="all", userid=user, wait=True)
        for mtype in type_list:
            items = [x for x in all_items if x.get("type") == mtype]
            for item in items:
                date = item.get("date")
                if not date:
                    continue
                mark_date = datetime.strptime(date, "%Y-%m-%d")
                if days and int(days) > 0:
                    if (datetime.now() - mark_date).days >= int(days):
                        continue
                doubanid = item.get("id")
                if str(doubanid).isdigit():
                    self.ctx.info(f"解析到媒体：{doubanid}")
                    if doubanid not in douban_ids:
                        douban_ids[doubanid] = {"user_name": user_name}

    def _process_douban_media(self, doubanid, info, auto_search, auto_rss):
        douban_info = self._douban.get_douban_detail(doubanid=doubanid, wait=True)
        if not douban_info:
            douban_info = self._douban.get_media_detail_from_web(doubanid)
            if not douban_info:
                self.ctx.warn(f"{doubanid} 无权限访问，需要配置豆瓣Cookie")
                sleep(round(random.uniform(1, 5), 1))
                return

        media_type = MediaType.TV if douban_info.get("episodes_count") else MediaType.MOVIE
        mi = meta_info(title="{} {}".format(douban_info.get("title"), douban_info.get("year") or ""))
        mi.douban_id = doubanid
        mi.type = media_type
        mi.overview = douban_info.get("intro")
        mi.poster_path = douban_info.get("cover_url")
        rating = douban_info.get("rating", {}) or {}
        mi.vote_average = rating.get("value") or ""
        mi.imdb_id = douban_info.get("imdbid")
        mi.user_name = info.get("user_name")

        history = self._get_history(doubanid)
        if history and history.get("state") != "NEW":
            self.ctx.info(f"{doubanid} {mi.get_name()} 已处理过(state={history.get('state')})")
            sleep(round(random.uniform(1, 5), 1))
            return

        try:
            if auto_search:
                self.ctx.info(f"{doubanid} {mi.get_name()} 开始自动搜索...")
                self._auto_search_media(mi, auto_rss)
            else:
                if auto_rss:
                    self.ctx.info(f"{doubanid} {mi.get_name()} 开始自动订阅...")
                    self._auto_subscribe_media(mi, state="R")
                else:
                    if history:
                        self.ctx.info(f"{doubanid} {meta_info.get_name()} 已存在NEW记录，跳过")
                    else:
                        self.ctx.info(f"{doubanid} {meta_info.get_name()} 记录到历史")
                        self._update_history(meta_info, state="NEW")
        except Exception as e:
            self.ctx.error(f"{doubanid} {meta_info.get_name()} 处理失败：{e}")

        sleep(round(random.uniform(1, 5), 1))

    def _auto_search_media(self, media_info, auto_rss):
        try:
            mediainfo = WebUtils.get_mediainfo_from_id(
                mtype=media_info.type,
                mediaid=f"DB:{media_info.douban_id}",
                wait=True,
            )
            if not mediainfo or not mediainfo.tmdb_info:
                self.ctx.warn(f"{media_info.get_name()} 未查询到媒体信息")
                self._update_history(media=media_info, state="FAILED")
                return

            exist_flag, no_exists, _ = self._downloader.check_exists_medias(meta_info=mediainfo)
            if exist_flag:
                self.ctx.info(f"{mediainfo.title} 已存在")
                self._update_history(media=mediainfo, state="DOWNLOADED")
                return

            if not auto_rss:
                self.ctx.info(f"{mediainfo.title} 开始自动搜索...")
                search_result, no_exists, search_count, download_count = self._searcher.search_one_media(
                    media_info=mediainfo,
                    in_from=SearchType.DB,
                    no_exists=no_exists,
                    user_name=mediainfo.user_name,
                )
                if search_result:
                    self._update_history(media=mediainfo, state="DOWNLOADED")
                else:
                    self.ctx.warn(f"{mediainfo.title} 搜索无结果")
                    self._update_history(media=mediainfo, state="SEARCH_FAILED")
            else:
                self.ctx.info(f"{mediainfo.title} 更新到订阅中...")
                code, msg, _ = self._subscribe.add_rss_subscribe(
                    mtype=mediainfo.type,
                    name=mediainfo.title,
                    year=mediainfo.year,
                    channel=RssType.Auto.value,
                    mediaid=f"DB:{mediainfo.douban_id}",
                    in_from=SearchType.DB.value,
                )
                self.ctx.info(f"订阅返回 code={code}, msg={msg}")
                if code == 0 or code == 9:
                    self._update_history(media=mediainfo, state="RSS")
                else:
                    self.ctx.error(f"{mediainfo.title} 添加订阅失败：{msg}")
                    self._update_history(media=mediainfo, state="RSS_FAILED")
        except Exception as e:
            import traceback

            self.ctx.error(f"_auto_search_media 内部异常: {e}")
            self.ctx.error(traceback.format_exc())
            with contextlib.suppress(Exception):
                self._update_history(media=media_info, state="FAILED")

    def _auto_subscribe_media(self, media_info, state="R"):
        self.ctx.info(f"{media_info.get_name()} 更新到订阅中...")
        try:
            result = self._subscribe.add_rss_subscribe(
                mtype=media_info.type,
                name=media_info.get_name(),
                year=media_info.year,
                channel=RssType.Auto.value,
                mediaid=f"DB:{media_info.douban_id}",
                in_from=SearchType.DB.value,
            )
            self.ctx.info(f"订阅返回 result={result}")
            code, msg, _ = result
            self.ctx.info(f"订阅返回 code={code}, msg={msg}")
            if code == 0 or code == 9:
                self.ctx.info("code 匹配，准备调用 _update_history")
                self._update_history(media=media_info, state="RSS")
                self.ctx.info("_update_history 调用完成")
            else:
                self.ctx.error(f"{media_info.get_name()} 添加订阅失败：{msg}")
        except Exception as e:
            import traceback

            self.ctx.error(f"_auto_subscribe_media 内部异常: {e}")
            self.ctx.error(traceback.format_exc())

    def _get_history(self, douban_id: str | None = None) -> dict:
        data = self._load_history()
        if douban_id:
            return data.get(str(douban_id))
        return data

    def _load_history(self) -> dict:
        content = self.ctx.read_data("history.json")
        if content:
            try:
                return json.loads(content)
            except Exception:
                self.ctx.warn("history.json 解析失败，将重新创建")
        return {}

    def _save_history(self, data: dict) -> None:
        self.ctx.write_data("history.json", json.dumps(data, ensure_ascii=False, indent=2))

    def _update_history(self, media, state: str) -> None:
        self.ctx.info(f"_update_history 开始执行: douban_id={media.douban_id}, state={state}")
        data = self._load_history()
        self.ctx.info(f"_load_history 返回 {len(data)} 条记录")
        key = str(media.douban_id)
        title = media.title or media.get_name()
        # 兼容 media.type 可能是枚举或字符串
        media_type = media.type.value if hasattr(media.type, "value") else str(media.type)
        # 兼容 get_poster_image 可能不存在
        try:
            image = media.get_poster_image()
        except Exception:
            image = media.poster_path or ""
        data[key] = {
            "id": media.douban_id,
            "name": title,
            "year": media.year,
            "type": media_type,
            "rating": media.vote_average,
            "image": image,
            "state": state,
            "add_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.ctx.info(f"准备保存 history.json，key={key}")
        self._save_history(data)
        self.ctx.info(f"历史记录已更新: {title} [{state}]")

    def delete_history(self, douban_id: str) -> bool:
        data = self._load_history()
        key = str(douban_id)
        if key in data:
            del data[key]
            self._save_history(data)
            return True
        return False
