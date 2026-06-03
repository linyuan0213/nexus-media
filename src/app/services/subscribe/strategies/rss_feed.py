"""RSS Feed 轮询策略 — 从站点 RSS Feed 收集资源并匹配订阅."""

import json
from threading import Lock

import log
from app.core.exceptions import (
    DownloadError,
    IndexerError,
    MediaError,
    NetworkError,
    RepositoryError,
    ServiceError,
)
from app.db.repositories.subscribe_repo_adapter import SubscribeHistoryRepositoryAdapter
from app.di import container
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.services.subscribe.matcher import SubscribeMatcher
from app.sites.torrent import Torrent
from app.utils import ExceptionUtils, JsonUtils
from app.domain.mediatypes import MediaType
from app.domain.enums import SearchType

lock = Lock()


class RssFeedStrategy:
    """RSS Feed 轮询策略：从站点 RSS Feed 收集资源，识别媒体，匹配订阅，择优下载."""

    def __init__(
        self,
        media=None,
        downloader=None,
        sites=None,
        siteconf=None,
        download_repo=None,
        rss_repo=None,
        rsshelper=None,
        subscribe=None,
        matcher=None,
        message=None,
        coordinator=None,
    ):
        self.media = media or container.media_service()
        self.sites = sites or container.sites()
        self.siteconf = siteconf or container.site_conf()
        self.downloader = downloader or container.downloader_core()
        self.download_repo = download_repo or container.download_history_repo()
        self.rss_repo = rss_repo or SubscribeHistoryRepositoryAdapter()
        self.rsshelper = rsshelper or container.rss_helper()
        self.subscribe = subscribe or container.subscribe_service()
        self.matcher = matcher or SubscribeMatcher()
        self.message = message or container.message()
        self._coordinator = coordinator

    def run(self) -> None:
        """RSS Feed 轮询入口，由 SubscriptionMonitor 调用."""
        dist_lock = get_lock_manager().create_lock("rss:download", ttl_seconds=1800)
        acquired = dist_lock.acquire()
        if not acquired:
            log.info("[RssFeedStrategy] RSS 轮询正在其他实例执行，跳过")
            return
        try:
            self._do_rss_poll()
        finally:
            dist_lock.release()

    def _do_rss_poll(self) -> None:
        if self.sites is None:
            return
        if self.subscribe is None:
            return
        rss_sites_info = self.sites.get_sites(rss=True, public=True)
        if not rss_sites_info:
            return

        with lock:
            log.info("[RssFeedStrategy] 开始 RSS 订阅轮询...")

        rss_movies = self.subscribe.get_subscribe_movies(state="R")
        if not rss_movies:
            log.warn(f"[RssFeedStrategy] 没有正在订阅的{MediaType.MOVIE.display_name}")
        else:
            log.info(
                "[RssFeedStrategy] {}订阅清单：{}".format(
                    MediaType.MOVIE.display_name,
                    " ".join("{}".format(info.get("name")) for info in rss_movies.values()),
                )
            )

        rss_tvs = self.subscribe.get_subscribe_tvs(state="R")
        if not rss_tvs:
            log.warn(f"[RssFeedStrategy] 没有正在订阅的{MediaType.TV.display_name}")
        else:
            log.info(
                "[RssFeedStrategy] {}订阅清单：{}".format(
                    MediaType.TV.display_name, " ".join("{}".format(info.get("name")) for info in rss_tvs.values())
                )
            )

        if not rss_movies and not rss_tvs:
            return

        check_sites = []
        check_all = False
        for rinfo in rss_movies.values():
            rss_sites = rinfo.get("rss_sites")
            if not rss_sites:
                check_all = True
                break
            else:
                check_sites += rss_sites
        if not check_all:
            for rinfo in rss_tvs.values():
                rss_sites = rinfo.get("rss_sites")
                if not rss_sites:
                    check_all = True
                    break
                else:
                    check_sites += rss_sites
        if check_all:
            check_sites = []
        else:
            check_sites = list(set(check_sites))

        all_articles = []
        for site_info in rss_sites_info:
            if not site_info:
                continue
            site_name = site_info.get("name")
            if check_sites and site_name not in check_sites:
                continue
            rss_url = site_info.get("rssurl")
            if not rss_url:
                log.info(f"[RssFeedStrategy] {site_name} 未配置 rssurl，跳过...")
                continue
            site_id = site_info.get("id")
            site_order = 100 - int(site_info.get("pri")) if site_info.get("pri") else 0

            log.info(f"[RssFeedStrategy] 正在处理：{site_name}")
            rss_articles = self.rsshelper.parse_rssxml(url=rss_url)
            if rss_articles is None:
                log.error(f"[RssFeedStrategy] 站点 {site_name} RSS 链接已过期，请重新获取！")
                self.message.send_site_message(title="[RSS 链接过期提醒]", text=f"站点：{site_name}\n链接：{rss_url}")
                continue
            if not rss_articles:
                log.warn(f"[RssFeedStrategy] {site_name} 未下载到数据")
                continue

            log.info(f"[RssFeedStrategy] {site_name} 获取数据：{len(rss_articles)}")
            for article in rss_articles:
                all_articles.append(
                    {
                        "article": article,
                        "site_name": site_name,
                        "site_id": site_id,
                        "site_order": site_order,
                        "site_cookie": site_info.get("cookie"),
                        "site_ua": site_info.get("ua"),
                        "site_headers": site_info.get("headers"),
                        "site_parse": site_info.get("parse"),
                        "site_proxy": site_info.get("proxy"),
                        "site_filter_rule": site_info.get("rule"),
                    }
                )

        if not all_articles:
            log.info("[RssFeedStrategy] 所有站点 RSS 处理结束，无有效数据")
            return

        seen_enclosures = set()
        to_identify = []

        for idx, item in enumerate(all_articles):
            article = item["article"]
            title = article.get("title")
            enclosure = article.get("enclosure")

            if not title:
                continue

            if enclosure and enclosure in seen_enclosures:
                continue
            if enclosure and self.rsshelper.is_rssd_by_enclosure(enclosure):
                log.info(f"[RssFeedStrategy] {title} 已成功订阅过")
                continue
            seen_enclosures.add(enclosure or "")

            to_identify.append({"idx": idx, "title": title})

        identify_results = {}
        if to_identify:
            log.info(f"[RssFeedStrategy] 批量识别 {len(to_identify)} 条不重复结果 ...")
            try:
                batch_results = self.media.identify_batch(to_identify)
                for item, info in zip(to_identify, batch_results, strict=False):
                    identify_results[item["idx"]] = info
            except (MediaError, NetworkError) as e:
                log.error(f"[RssFeedStrategy] 批量识别出错: {e}")

        rss_download_torrents = []
        rss_no_exists = {}

        for idx, item in enumerate(all_articles):
            try:
                article = item["article"]
                title = article.get("title")
                if not title:
                    continue

                enclosure = article.get("enclosure")
                page_url = article.get("link")
                size = article.get("size")
                site_name = item["site_name"]
                site_id = item["site_id"]
                site_order = item["site_order"]

                log.info(f"[RssFeedStrategy] 开始处理：{title}")

                if idx not in identify_results:
                    continue
                media_info = identify_results[idx]
                if not media_info:
                    log.warn(f"[RssFeedStrategy] {title} 无法识别出媒体信息！")
                    continue
                elif not media_info.tmdb_info:
                    log.info(f"[RssFeedStrategy] {title} 识别为 {media_info.get_name()} 未匹配到 TMDB 媒体信息")

                media_info.set_torrent_info(
                    size=size, page_url=page_url, site=site_name, site_order=site_order, enclosure=enclosure
                )

                if media_info.tmdb_id:
                    season_episode = media_info.get_season_episode_string()
                    if self.download_repo.is_exists_download_history_by_tmdb(media_info.tmdb_id, season_episode):
                        log.info(f"[RssFeedStrategy] {title} 已在下载历史中存在，跳过下载")
                        continue

                match_flag, match_msg, match_info = self.matcher.match(
                    media_info=media_info,
                    rss_movies=rss_movies,
                    rss_tvs=rss_tvs,
                    site_id=site_id,
                    site_filter_rule=item["site_filter_rule"],
                    site_cookie=item["site_cookie"],
                    site_parse=item["site_parse"],
                    site_ua=item["site_ua"],
                    site_headers=JsonUtils.is_valid_json(item["site_headers"])
                    and json.loads(item["site_headers"])
                    or {},
                    site_proxy=item["site_proxy"],
                )

                for msg in match_msg:
                    log.info(f"[RssFeedStrategy] {msg}")

                if not match_flag:
                    continue

                if not match_info.get("fuzzy_match"):
                    if not media_info.tmdb_info and media_info.tmdb_id:
                        media_info.set_tmdb_info(
                            self.media.get_tmdb_info(mtype=media_info.type, tmdbid=media_info.tmdb_id)
                        )
                    if not media_info.tmdb_info:
                        continue

                    if not match_info.get("over_edition"):
                        if media_info.type == MediaType.MOVIE:
                            exist_flag, rss_no_exists, _ = self.downloader.check_exists_medias(
                                meta_info=media_info, no_exists=rss_no_exists
                            )
                        else:
                            season = 1
                            if match_info.get("season"):
                                season = int(str(match_info.get("season")).replace("S", ""))
                            total_ep = match_info.get("total")
                            current_ep = match_info.get("current_ep")
                            episodes = self.subscribe.get_subscribe_tv_episodes(match_info.get("id"))
                            if episodes is None:
                                episodes = []
                                if current_ep:
                                    episodes = list(range(int(current_ep), int(total_ep) + 1))
                            if media_info.tmdb_id not in rss_no_exists:
                                rss_no_exists[media_info.tmdb_id] = []
                            rss_no_exists[media_info.tmdb_id].append(
                                {
                                    "season": season,
                                    "episodes": episodes,
                                    "total_episodes": total_ep,
                                }
                            )
                            exist_flag, library_no_exists, _ = self.downloader.check_exists_medias(
                                meta_info=media_info, total_ep={season: total_ep}
                            )
                            rss_no_exists = Torrent.get_intersection_episodes(
                                target=rss_no_exists, source=library_no_exists, title=media_info.tmdb_id
                            )
                            if rss_no_exists.get(media_info.tmdb_id):
                                log.info(
                                    f"[RssFeedStrategy] {media_info.get_title_string()} 订阅缺失季集：{rss_no_exists.get(media_info.tmdb_id)}"
                                )
                        if exist_flag:
                            continue
                    else:
                        if media_info.type != MediaType.MOVIE and media_info.get_episode_list():
                            log.info(
                                f"[RssFeedStrategy] {media_info.get_title_string()}{media_info.get_season_string()} "
                                f"正在洗版，过滤掉季集不完整的资源：{title}"
                            )
                            continue
                        if not self.subscribe.check_subscribe_over_edition(
                            rtype=media_info.type, rssid=match_info.get("id"), res_order=match_info.get("res_order")
                        ):
                            log.info(
                                f"[RssFeedStrategy] {media_info.get_title_string()}{media_info.get_season_string()} "
                                f"正在洗版，跳过低优先级或同优先级资源：{title}"
                            )
                            continue

                if self.sites.check_ratelimit(site_id):
                    continue

                media_info.set_torrent_info(
                    res_order=match_info.get("res_order"),
                    filter_rule=match_info.get("filter_rule"),
                    over_edition=match_info.get("over_edition"),
                    download_volume_factor=match_info.get("download_volume_factor"),
                    upload_volume_factor=match_info.get("upload_volume_factor"),
                    rssid=match_info.get("id"),
                )
                media_info.set_download_info(
                    download_setting=match_info.get("download_setting"), save_path=match_info.get("save_path")
                )
                self.rsshelper.insert_rss_torrents(media_info)
                if media_info not in rss_download_torrents:
                    rss_download_torrents.append(media_info)
            except (MediaError, DownloadError, IndexerError, RepositoryError, ServiceError, NetworkError) as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"[RssFeedStrategy] 处理 RSS 发生错误：{e!s}")
                continue

        log.info(f"[RssFeedStrategy] 所有 RSS 处理结束，共 {len(rss_download_torrents)} 个有效资源")
        self._download_matched_torrents(rss_download_torrents=rss_download_torrents, rss_no_exists=rss_no_exists)

    def _download_matched_torrents(self, rss_download_torrents, rss_no_exists):
        if not rss_download_torrents:
            return

        if self.subscribe is None:
            return
        if self.downloader is None:
            return
        finished_rss_torrents = []
        updated_rss_torrents = []

        def __finish_rss(download_item):
            if not download_item:
                return
            if not download_item.rssid or download_item.rssid in finished_rss_torrents:
                return
            finished_rss_torrents.append(download_item.rssid)
            if self.subscribe is None:
                return
            self.subscribe.finish_rss_subscribe(rssid=download_item.rssid, media=download_item)

        def __update_tv_rss(download_item, left_media):
            if not download_item or not left_media:
                return
            if not download_item.rssid or download_item.rssid in updated_rss_torrents:
                return
            updated_rss_torrents.append(download_item.rssid)
            if self.subscribe is None:
                return
            self.subscribe.update_subscribe_tv_lack(
                rssid=download_item.rssid, media_info=download_item, seasoninfo=left_media
            )

        def __update_over_edition(download_item):
            if not download_item:
                return
            if not download_item.rssid or download_item.rssid in updated_rss_torrents:
                return
            if download_item.get_episode_list():
                return
            updated_rss_torrents.append(download_item.rssid)
            if self.subscribe is None:
                return
            self.subscribe.update_subscribe_over_edition(
                rtype=download_item.type, rssid=download_item.rssid, media=download_item
            )

        for media in rss_download_torrents:
            if media.type not in (MediaType.TV, MediaType.ANIME):
                continue
            if media.begin_episode is not None:
                continue
            if not media.enclosure or media.enclosure.startswith("magnet:"):
                continue
            try:
                episodes, file_path = self.downloader.get_torrent_episodes(media.enclosure, media.page_url)
                if file_path:
                    Torrent().delete_torrent_file(file_path)
                if episodes:
                    media.total_episodes = len(episodes)
                    media.begin_episode = min(episodes)
                    media.end_episode = max(episodes)
                    log.info(
                        f"[RssFeedStrategy] {media.org_string or media.title} 解析种子实际集数：{len(episodes)} 集"
                    )
                else:
                    log.info(f"[RssFeedStrategy] {media.org_string or media.title} 解析种子未识别出集数，视为单集")
            except DownloadError as e:
                log.debug(f"[RssFeedStrategy] 解析种子失败：{e!s}")

        def _rss_sort_key(x):
            episode_list = x.get_episode_list() if hasattr(x, "get_episode_list") else []
            episode_count = max(len(episode_list), getattr(x, "total_episodes", 0))
            if episode_count > 1:
                collection_priority = 2
            elif (
                getattr(x, "type", None) in (MediaType.TV, MediaType.ANIME)
                and getattr(x, "begin_season", None) is not None
                and getattr(x, "begin_episode", None) is None
            ):
                collection_priority = 1
            else:
                collection_priority = 0
            return (collection_priority, episode_count, x.res_order, x.site_order, x.seeders)

        rss_download_torrents.sort(key=_rss_sort_key, reverse=True)

        if self._coordinator:
            filtered = []
            for item in rss_download_torrents:
                if self._coordinator.try_acquire(item):
                    filtered.append(item)
                else:
                    log.info(f"[RssFeedStrategy] {item.title} 已被其他策略锁定，跳过")
            rss_download_torrents = filtered

        download_items, _ = self.downloader.batch_download(SearchType.SUBSCRIBE, rss_download_torrents, rss_no_exists)

        if download_items:
            for item in download_items:
                if not item.rssid:
                    continue
                if item.over_edition:
                    __update_over_edition(item)
                elif not rss_no_exists or not rss_no_exists.get(item.tmdb_id):
                    __finish_rss(item)
                else:
                    __update_tv_rss(item, rss_no_exists.get(item.tmdb_id))
            log.info(f"[RssFeedStrategy] 实际下载了 {len(download_items)} 个资源")
        else:
            log.info("[RssFeedStrategy] 未下载到任何资源")
