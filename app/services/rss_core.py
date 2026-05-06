# -*- coding: utf-8 -*-
"""
RSS 核心模块

职责：RSS 订阅搜索下载、种子订阅匹配、RSS 历史管理。

处理流水线（四阶段）：
1. 获取订阅和站点 → 解析 RSS 收集所有条目
2. 批量媒体识别（去重后并发查询 TMDB，替代逐条识别）
3. 批量订阅匹配和过滤
4. 择优下载
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import log
from app.services.downloader_core import DownloaderCore as Downloader
from app.helper import RssHelper
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.db.repositories.rss_repo_adapter import RssHistoryRepositoryAdapter
from app.media import Media
from app.media.meta import MetaInfo
from app.sites import Sites, SiteConf
from app.services.subscribe_service import SubscribeService as Subscribe
from app.services.rss_matcher import RssMatcher
from app.utils import ExceptionUtils, Torrent, JsonUtils
from app.utils.commons import SingletonMeta
from app.utils.types import MediaType, SearchType

lock = Lock()


class Rss(metaclass=SingletonMeta):
    filter = None
    media = None
    sites = None
    siteconf = None
    downloader = None
    searcher = None
    download_repo = None
    rss_repo = None
    rsshelper = None
    subscribe = None
    matcher = None

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.media = Media()
        self.downloader = Downloader()
        self.sites = Sites()
        self.siteconf = SiteConf()
        self.download_repo = DownloadHistoryRepositoryAdapter()
        self.rss_repo = RssHistoryRepositoryAdapter()
        self.rsshelper = RssHelper()
        self.subscribe = Subscribe()
        self.matcher = RssMatcher()

    def rssdownload(self):
        """
        RSS订阅搜索下载入口，由定时服务调用
        
        四阶段流水线：
        1. 收集所有 RSS 条目的原始数据
        2. 批量识别媒体信息（去重后并发查询 TMDB）
        3. 批量订阅匹配和过滤
        4. 择优下载
        """
        rss_sites_info = self.sites.get_sites(rss=True)
        if not rss_sites_info:
            return

        with lock:
            log.info("【Rss】开始RSS订阅...")

            # 读取订阅清单
            rss_movies = self.subscribe.get_subscribe_movies(state='R')
            if not rss_movies:
                log.warn("【Rss】没有正在订阅的电影")
            else:
                log.info("【Rss】电影订阅清单：%s"
                         % " ".join('%s' % info.get("name") for _, info in rss_movies.items()))

            rss_tvs = self.subscribe.get_subscribe_tvs(state='R')
            if not rss_tvs:
                log.warn("【Rss】没有正在订阅的电视剧")
            else:
                log.info("【Rss】电视剧订阅清单：%s"
                         % " ".join('%s' % info.get("name") for _, info in rss_tvs.items()))

            if not rss_movies and not rss_tvs:
                return

            # 获取有订阅的站点范围
            check_sites = []
            check_all = False
            for rid, rinfo in rss_movies.items():
                rss_sites = rinfo.get("rss_sites")
                if not rss_sites:
                    check_all = True
                    break
                else:
                    check_sites += rss_sites
            if not check_all:
                for rid, rinfo in rss_tvs.items():
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

            # ---------- 阶段1：收集所有 RSS 条目的原始数据 ----------
            all_articles = []  # [(article, site_name, site_id, site_order, site_cookie, ...)]
            for site_info in rss_sites_info:
                if not site_info:
                    continue
                site_name = site_info.get("name")
                if check_sites and site_name not in check_sites:
                    continue
                rss_url = site_info.get("rssurl")
                if not rss_url:
                    log.info(f"【Rss】{site_name} 未配置rssurl，跳过...")
                    continue
                site_id = site_info.get("id")
                site_order = 100 - int(site_info.get("pri")) if site_info.get("pri") else 0

                log.info(f"【Rss】正在处理：{site_name}")
                rss_articles = self.rsshelper.parse_rssxml(url=rss_url)
                if rss_articles is None:
                    log.error(f"【Rss】站点 {site_name} RSS链接已过期，请重新获取！")
                    self.message.send_site_message(
                        title="【RSS链接过期提醒】",
                        text=f"站点：{site_name}\n链接：{rss_url}")
                    continue
                if not rss_articles:
                    log.warn(f"【Rss】{site_name} 未下载到数据")
                    continue

                log.info(f"【Rss】{site_name} 获取数据：{len(rss_articles)}")
                for article in rss_articles:
                    all_articles.append({
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
                    })

            if not all_articles:
                log.info("【Rss】所有站点RSS处理结束，无有效数据")
                return

            # ---------- 阶段2：批量媒体识别 ----------
            # 去重：按 enclosure 去重已下载的，按 title 去重需识别的
            seen_enclosures = set()
            to_identify = []  # [(index, title)]
            to_skip = set()   # indices to skip

            for idx, item in enumerate(all_articles):
                article = item["article"]
                title = article.get('title')
                enclosure = article.get('enclosure')

                if not title:
                    continue

                # 检查已下载
                if enclosure and enclosure in seen_enclosures:
                    continue
                if enclosure:
                    if self.rsshelper.is_rssd_by_enclosure(enclosure):
                        log.info(f"【Rss】{title} 已成功订阅过")
                        continue
                seen_enclosures.add(enclosure or "")

                to_identify.append((idx, title))

            if to_identify:
                log.info(f"【Rss】批量识别 {len(to_identify)} 条不重复结果 ...")
                identify_results = {}  # {idx: media_info}

                def _do_identify(args):
                    idx, title = args
                    try:
                        return idx, self.media.get_media_info(title=title)
                    except Exception as e:
                        log.error(f"【Rss】识别出错: {title}, {e}")
                        return idx, None

                max_workers = min(len(to_identify), 4)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(_do_identify, (idx, title)): idx
                              for idx, title in to_identify}
                    for future in as_completed(futures):
                        idx, media_info = future.result()
                        identify_results[idx] = media_info

            # ---------- 阶段3：批量订阅匹配和过滤 ----------
            rss_download_torrents = []
            rss_no_exists = {}
            res_num = 0

            for idx, item in enumerate(all_articles):
                try:
                    article = item["article"]
                    title = article.get('title')
                    if not title:
                        continue

                    enclosure = article.get('enclosure')
                    page_url = article.get('link')
                    size = article.get('size')
                    site_name = item["site_name"]
                    site_id = item["site_id"]
                    site_order = item["site_order"]

                    log.info(f"【Rss】开始处理：{title}")

                    if idx not in identify_results:
                        continue
                    media_info = identify_results[idx]
                    if not media_info:
                        log.warn(f"【Rss】{title} 无法识别出媒体信息！")
                        continue
                    elif not media_info.tmdb_info:
                        log.info(f"【Rss】{title} 识别为 {media_info.get_name()} 未匹配到TMDB媒体信息")

                    media_info.set_torrent_info(size=size,
                                                page_url=page_url,
                                                site=site_name,
                                                site_order=site_order,
                                                enclosure=enclosure)

                    # 检查下载历史
                    if media_info.tmdb_id:
                        season_episode = media_info.get_season_episode_string()
                        if self.download_repo.is_exists_download_history_by_tmdb(
                                media_info.tmdb_id, season_episode):
                            log.info(f"【Rss】{title} 已在下载历史中存在，跳过下载")
                            continue

                    # 匹配订阅
                    match_flag, match_msg, match_info = self.matcher.match(
                        media_info=media_info,
                        rss_movies=rss_movies,
                        rss_tvs=rss_tvs,
                        site_id=site_id,
                        site_filter_rule=item["site_filter_rule"],
                        site_cookie=item["site_cookie"],
                        site_parse=item["site_parse"],
                        site_ua=item["site_ua"],
                        site_headers=JsonUtils.is_valid_json(item["site_headers"]) and json.loads(item["site_headers"]) or {},
                        site_proxy=item["site_proxy"]
                    )

                    for msg in match_msg:
                        log.info(f"【Rss】{msg}")

                    if not match_flag:
                        continue

                    # 非模糊匹配命中，检查本地情况
                    if not match_info.get("fuzzy_match"):
                        if not media_info.tmdb_info and media_info.tmdb_id:
                            media_info.set_tmdb_info(
                                self.media.get_tmdb_info(mtype=media_info.type,
                                                         tmdbid=media_info.tmdb_id))
                        if not media_info.tmdb_info:
                            continue

                        if not match_info.get("over_edition"):
                            if media_info.type == MediaType.MOVIE:
                                exist_flag, rss_no_exists, _ = self.downloader.check_exists_medias(
                                    meta_info=media_info, no_exists=rss_no_exists)
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
                                    rss_no_exists[media_info.tmdb_id] = [{
                                        "season": season,
                                        "episodes": episodes,
                                        "total_episodes": total_ep
                                    }]
                                else:
                                    rss_no_exists[media_info.tmdb_id] = [{
                                        "season": season,
                                        "episodes": episodes,
                                        "total_episodes": total_ep
                                    }]
                                exist_flag, library_no_exists, _ = self.downloader.check_exists_medias(
                                    meta_info=media_info, total_ep={season: total_ep})
                                rss_no_exists = Torrent.get_intersection_episodes(
                                    target=rss_no_exists,
                                    source=library_no_exists,
                                    title=media_info.tmdb_id)
                                if rss_no_exists.get(media_info.tmdb_id):
                                    log.info("【Rss】%s 订阅缺失季集：%s" % (
                                        media_info.get_title_string(),
                                        rss_no_exists.get(media_info.tmdb_id)))
                            if exist_flag:
                                continue
                        else:
                            # 洗版模式
                            if media_info.type != MediaType.MOVIE and media_info.get_episode_list():
                                log.info(f"【Rss】{media_info.get_title_string()}{media_info.get_season_string()} "
                                         f"正在洗版，过滤掉季集不完整的资源：{title}")
                                continue
                            if not self.subscribe.check_subscribe_over_edition(
                                    rtype=media_info.type,
                                    rssid=match_info.get("id"),
                                    res_order=match_info.get("res_order")):
                                log.info(f"【Rss】{media_info.get_title_string()}{media_info.get_season_string()} "
                                         f"正在洗版，跳过低优先级或同优先级资源：{title}")
                                continue

                    # 站点流控
                    if self.sites.check_ratelimit(site_id):
                        continue

                    # 设置种子信息
                    media_info.set_torrent_info(
                        res_order=match_info.get("res_order"),
                        filter_rule=match_info.get("filter_rule"),
                        over_edition=match_info.get("over_edition"),
                        download_volume_factor=match_info.get("download_volume_factor"),
                        upload_volume_factor=match_info.get("upload_volume_factor"),
                        rssid=match_info.get("id"))
                    media_info.set_download_info(
                        download_setting=match_info.get("download_setting"),
                        save_path=match_info.get("save_path"))
                    self.rsshelper.insert_rss_torrents(media_info)
                    if media_info not in rss_download_torrents:
                        rss_download_torrents.append(media_info)
                        res_num += 1
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    log.error("【Rss】处理RSS发生错误：%s" % str(e))
                    continue

            log.info("【Rss】所有RSS处理结束，共 %s 个有效资源" % len(rss_download_torrents))
            self.download_rss_torrent(rss_download_torrents=rss_download_torrents,
                                      rss_no_exists=rss_no_exists)

    def check_torrent_rss(self,
                          media_info,
                          rss_movies,
                          rss_tvs,
                          site_id,
                          site_filter_rule,
                          site_cookie,
                          site_parse,
                          site_ua,
                          site_headers,
                          site_proxy):
        """
        判断种子是否命中订阅（委托给 RssMatcher）
        """
        return self.matcher.match(
            media_info=media_info,
            rss_movies=rss_movies,
            rss_tvs=rss_tvs,
            site_id=site_id,
            site_filter_rule=site_filter_rule,
            site_cookie=site_cookie,
            site_parse=site_parse,
            site_ua=site_ua,
            site_headers=site_headers,
            site_proxy=site_proxy
        )

    def download_rss_torrent(self, rss_download_torrents, rss_no_exists):
        """
        根据缺失情况以及匹配到的结果选择下载种子
        """
        if not rss_download_torrents:
            return

        finished_rss_torrents = []
        updated_rss_torrents = []

        def __finish_rss(download_item):
            if not download_item:
                return
            if not download_item.rssid or download_item.rssid in finished_rss_torrents:
                return
            finished_rss_torrents.append(download_item.rssid)
            self.subscribe.finish_rss_subscribe(rssid=download_item.rssid, media=download_item)

        def __update_tv_rss(download_item, left_media):
            if not download_item or not left_media:
                return
            if not download_item.rssid or download_item.rssid in updated_rss_torrents:
                return
            updated_rss_torrents.append(download_item.rssid)
            self.subscribe.update_subscribe_tv_lack(
                rssid=download_item.rssid,
                media_info=download_item,
                seasoninfo=left_media)

        def __update_over_edition(download_item):
            if not download_item:
                return
            if not download_item.rssid or download_item.rssid in updated_rss_torrents:
                return
            if download_item.get_episode_list():
                return
            updated_rss_torrents.append(download_item.rssid)
            self.subscribe.update_subscribe_over_edition(
                rtype=download_item.type,
                rssid=download_item.rssid,
                media=download_item)

        download_items, left_medias = self.downloader.batch_download(
            SearchType.RSS, rss_download_torrents, rss_no_exists)

        if download_items:
            for item in download_items:
                if not item.rssid:
                    continue
                if item.over_edition:
                    __update_over_edition(item)
                elif not left_medias or not left_medias.get(item.tmdb_id):
                    __finish_rss(item)
                else:
                    __update_tv_rss(item, left_medias.get(item.tmdb_id))
            log.info("【Rss】实际下载了 %s 个资源" % len(download_items))
        else:
            log.info("【Rss】未下载到任何资源")

    def delete_rss_history(self, rssid):
        """
        删除订阅历史
        """
        self.rss_repo.delete_rss_history(rssid=rssid)

    def get_rss_history(self, rtype=None, rid=None):
        """
        获取订阅历史
        """
        return self.rss_repo.get_rss_history(rtype=rtype, rid=rid)
