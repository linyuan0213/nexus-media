# -*- coding: utf-8 -*-
"""
DownloadCore - 下载核心业务逻辑

职责：
- 单个资源下载（download）
- 批量下载（batch_download）
- 媒体库存在性检查（check_exists_medias）
- 种子文件解析（get_torrent_episodes）
- 历史记录查询

依赖注入：所有外部依赖通过构造函数传入。
"""
import json
import os
from typing import Optional

import log
from app.conf import SystemConfig
from app.db.repositories import DownloadRepository
from app.downloader.client._base import _IDownloadClient
from app.entities import torrent
from app.helper import ThreadHelper
from app.media import Media
from app.media.meta import MetaInfo
from app.mediaserver import MediaServer
from app.message import Message
from app.plugins import EventManager
from app.services.downloader_client_factory import DownloadClientFactory
from app.services.download_strategies import MovieDownloadStrategy, SeasonPackStrategy, EpisodeStrategy
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.sites import Sites, SiteSubtitle, SiteConf
from app.utils import Torrent, StringUtils, ExceptionUtils
from app.utils.types import MediaType, DownloaderType, SearchType, EventType
from config import RMT_MEDIAEXT


class DownloadCore:
    """
    下载核心业务服务
    """

    def __init__(self,
                 client_factory: Optional[DownloadClientFactory] = None,
                 message: Optional[Message] = None,
                 mediaserver: Optional[MediaServer] = None,
                 filetransfer: Optional[FileTransfer] = None,
                 media: Optional[Media] = None,
                 sites: Optional[Sites] = None,
                 siteconf: Optional[SiteConf] = None,
                 sitesubtitle: Optional[SiteSubtitle] = None,
                 eventmanager: Optional[EventManager] = None,
                 download_repo: Optional[DownloadRepository] = None,
                 systemconfig: Optional[SystemConfig] = None):
        self._client_factory = client_factory or DownloadClientFactory()
        self._message = message or Message()
        self._mediaserver = mediaserver or MediaServer()
        self._filetransfer = filetransfer or FileTransfer()
        self._media = media or Media()
        self._sites = sites or Sites()
        self._siteconf = siteconf or SiteConf()
        self._sitesubtitle = sitesubtitle or SiteSubtitle()
        self._eventmanager = eventmanager or EventManager()
        self._download_repo = download_repo or DownloadRepository()
        self._systemconfig = systemconfig or SystemConfig()

    # ---------- 核心下载方法 ----------

    def download(self,
                 media_info,
                 is_paused=None,
                 tag=None,
                 download_dir=None,
                 download_setting=None,
                 downloader_id=None,
                 upload_limit=None,
                 download_limit=None,
                 torrent_file=None,
                 in_from=None,
                 user_name=None,
                 proxy=None):
        """
        添加下载任务
        :return: 下载器类型, 种子ID，错误信息
        """

        def _download_fail(msg):
            self._eventmanager.send_event(EventType.DownloadFail, {
                "media_info": media_info.to_dict(),
                "reason": msg
            })
            if in_from:
                self._message.send_download_fail_message(media_info, f"添加下载任务失败：{msg}")

        # 触发下载事件
        self._eventmanager.send_event(EventType.DownloadAdd, {
            "media_info": media_info.to_dict(),
            "is_paused": is_paused,
            "tag": tag,
            "download_dir": download_dir,
            "download_setting": download_setting,
            "downloader_id": downloader_id,
            "torrent_file": torrent_file
        })

        title = media_info.org_string
        page_url = media_info.page_url
        site_info, dl_files_folder, dl_files, retmsg = {}, "", [], ""
        torrent_attr = {}
        file_path = None
        url = None

        if torrent_file:
            url = os.path.basename(torrent_file)
            content, dl_files_folder, dl_files, retmsg = Torrent().read_torrent_content(torrent_file)
        else:
            url = media_info.enclosure
            if media_info.page_url and not media_info.enclosure:
                url = self.get_download_url(media_info.page_url)
            if not url:
                _download_fail("下载链接为空")
                return None, None, "下载链接为空"
            if url.startswith("magnet:"):
                content = url
            else:
                site_info = self._sites.get_sites(siteurl=url)
                cookie = site_info.get("cookie")
                if 'm-team' in url:
                    cookie = None
                headers = site_info.get("headers")
                headers = json.loads(headers) if headers else {'User-Agent': __import__('config').Config().get_ua()}
                if page_url:
                    torrent_attr = self._siteconf.check_torrent_attr(
                        torrent_url=page_url,
                        cookie=cookie,
                        ua=site_info.get("ua"),
                        headers=headers,
                        proxy=proxy if proxy is not None else site_info.get("proxy")
                    )
                file_path, content, dl_files_folder, dl_files, retmsg = Torrent().get_torrent_info(
                    url=url,
                    cookie=cookie,
                    ua=site_info.get("ua"),
                    referer=page_url if not site_info.get("referer") else site_info.get("referer"),
                    proxy=proxy if proxy is not None else site_info.get("proxy")
                )

        if retmsg:
            log.warn("【Downloader】%s" % retmsg)

        if not content:
            _download_fail(retmsg)
            return None, None, retmsg

        # 下载设置处理
        download_attr = self._resolve_download_setting(media_info, download_setting)
        download_setting_name = download_attr.get('name')

        # 下载器实例
        if not downloader_id:
            downloader_id = download_attr.get("downloader")
        downloader_conf = self._client_factory.get_downloader_conf(downloader_id)
        downloader = self._client_factory.get_client(downloader_id)

        if not downloader or not downloader_conf:
            _download_fail("请检查下载设置所选下载器是否有效且启用")
            return None, None, f"下载设置 {download_setting_name} 所选下载器失效"
        downloader_name = downloader_conf.get("name")

        try:
            category = download_attr.get("category")
            tags = self._build_tags(tag, download_attr, site_info, torrent_attr)
            is_paused = self._resolve_is_paused(is_paused, download_attr)
            upload_limit = upload_limit or download_attr.get("upload_limit")
            download_limit = download_limit or download_attr.get("download_limit")
            ratio_limit = download_attr.get("ratio_limit")
            seeding_time_limit = download_attr.get("seeding_time_limit")

            if not download_dir:
                download_info = DownloadClientFactory.get_download_dir_info(
                    media_info, downloader_conf.get("download_dir")
                )
                download_dir = download_info.get('path')
                if not category:
                    category = download_info.get('category')

            print_url = content if isinstance(content, str) else url
            log.info(
                f"【Downloader】下载器 {downloader_name} {'添加任务并暂停' if is_paused else '添加任务'}：%s，目录：%s，Url：%s"
                % (title, download_dir, print_url)
            )

            downloader_type = downloader.get_type()
            download_id = self._add_to_downloader(
                downloader=downloader,
                downloader_type=downloader_type,
                content=content,
                is_paused=is_paused,
                download_dir=download_dir,
                tags=tags,
                category=category,
                upload_limit=upload_limit,
                download_limit=download_limit,
                ratio_limit=ratio_limit,
                seeding_time_limit=seeding_time_limit,
                cookie=site_info.get("cookie"),
                url=url,
            )

            if not download_id:
                _download_fail("请检查下载任务是否已存在")
                return downloader_id, None, f"下载器 {downloader_name} 添加下载任务失败，请检查下载任务是否已存在"

            # 处理QB已存在的情况
            if downloader_type == DownloaderType.QB and download_id == "EXISTS":
                return downloader_id, None, ""

            # 计算数据文件保存路径
            save_dir = subtitle_dir = None
            visit_dir = self._client_factory.get_download_visit_dir(download_dir)
            if visit_dir:
                if dl_files_folder:
                    save_dir = os.path.join(visit_dir, dl_files_folder)
                    subtitle_dir = save_dir
                elif dl_files:
                    save_dir = os.path.join(visit_dir, dl_files[0])
                    subtitle_dir = visit_dir
                elif url and url.startswith("magnet:"):
                    save_dir = None
                    subtitle_dir = visit_dir
                else:
                    save_dir = None
                    subtitle_dir = visit_dir
                    downloader.delete_torrents(ids=download_id, delete_file=True)
                    _download_fail("请检查下载任务保存目录是否正确")
                    return downloader_id, None, f"下载器 {downloader_name} 添加下载任务失败，请检查下载任务保存目录是否正确"

            # 登记下载历史
            self._download_repo.insert_download_history(
                media_info=media_info,
                downloader=downloader_id,
                download_id=download_id,
                save_dir=save_dir
            )

            # 下载站点字幕文件
            if page_url and subtitle_dir and site_info and site_info.get("subtitle"):
                ThreadHelper().start_thread(
                    self._sitesubtitle.download,
                    (media_info, site_info.get("id"), site_info.get("cookie"),
                     site_info.get("ua"), subtitle_dir)
                )

            # 发送下载消息
            if in_from:
                media_info.user_name = user_name
                media_info.hit_and_run = bool(torrent_attr and torrent_attr.get('hr'))
                self._message.send_download_message(
                    in_from=in_from,
                    can_item=media_info,
                    download_setting_name=download_setting_name,
                    downloader_name=downloader_name
                )
            return downloader_id, download_id, ""

        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            _download_fail(str(e))
            log.error(f"【Downloader】下载器 {downloader_name} 添加任务出错：%s" % str(e))
            return None, None, str(e)
        finally:
            if url and not url.startswith("magnet:"):
                try:
                    if file_path:
                        Torrent().delete_torrent_file(file_path)
                except Exception:
                    pass

    # ---------- 内部辅助方法 ----------

    def _resolve_download_setting(self, media_info, download_setting):
        """解析最终使用的下载设置"""
        if not download_setting and media_info.site:
            download_setting = self._sites.get_site_download_setting(media_info.site)
        if download_setting == "-2":
            return {}
        elif download_setting:
            return self._client_factory.get_download_setting(download_setting) \
                or self._client_factory.get_download_setting(self._client_factory.default_download_setting_id)
        else:
            return self._client_factory.get_download_setting(self._client_factory.default_download_setting_id)

    def _build_tags(self, tag, download_attr, site_info, torrent_attr):
        """构建并排序标签"""
        tags = download_attr.get("tags")
        if tags:
            tags = str(tags).split(";")
            if tag:
                if isinstance(tag, list):
                    tags.extend(tag)
                else:
                    tags.append(tag)
        else:
            if tag:
                if isinstance(tag, list):
                    tags = tag
                else:
                    tags = [tag]
            else:
                tags = []
        if torrent_attr and torrent_attr.get('hr'):
            tags.append("HR")
        if site_info and site_info.get("tag"):
            tags.append(site_info.get("tag"))
        site_tag = site_info.get("tag") if site_info else None
        if tags:
            tags.sort(key=lambda x: (
                0 if x == "NASTOOL" else
                1 if x == site_tag else
                2, x
            ))
        return tags

    def _resolve_is_paused(self, is_paused, download_attr):
        """解析是否暂停"""
        if is_paused is None:
            return StringUtils.to_bool(download_attr.get("is_paused"))
        return bool(is_paused)

    def _add_to_downloader(self, downloader, downloader_type, content, is_paused,
                           download_dir, tags, category, upload_limit, download_limit,
                           ratio_limit, seeding_time_limit, cookie, url):
        """
        调用具体下载器客户端添加任务
        :return: 下载ID 或特殊标记 "EXISTS"
        """
        if downloader_type == DownloaderType.TR:
            ret = downloader.add_torrent(content,
                                         is_paused=is_paused,
                                         download_dir=download_dir,
                                         cookie=cookie)
            if ret:
                download_id = ret.hashString
                downloader.change_torrent(tid=download_id,
                                          tag=tags,
                                          upload_limit=upload_limit,
                                          download_limit=download_limit,
                                          ratio_limit=ratio_limit,
                                          seeding_time_limit=seeding_time_limit)
                return download_id
        elif downloader_type == DownloaderType.QB:
            exists, torrent_hash = downloader.check_torrent_exists(content)
            if exists:
                log.info(f"【Downloader】下载器中已存在该任务，跳过添加")
                return "EXISTS"
            torrent_tag = "NT" + StringUtils.generate_random_str(5)
            if tags:
                tags += [torrent_tag]
            else:
                tags = [torrent_tag]
            ret = downloader.add_torrent(content,
                                         is_paused=is_paused,
                                         download_dir=download_dir,
                                         tag=tags,
                                         category=category,
                                         content_layout="Original",
                                         upload_limit=upload_limit,
                                         download_limit=download_limit,
                                         ratio_limit=ratio_limit,
                                         seeding_time_limit=seeding_time_limit,
                                         cookie=cookie)
            if ret:
                download_id = downloader.get_torrent_id_by_tag(torrent_tag)
                if not download_id:
                    _, torrent_hash = downloader.check_torrent_exists(content)
                    if torrent_hash:
                        return "EXISTS"
                    log.warn(f"【Downloader】下载器添加任务成功但无法获取任务ID")
                    return None
                return download_id
        else:
            ret = downloader.add_torrent(content,
                                         is_paused=is_paused,
                                         tag=tags,
                                         download_dir=download_dir,
                                         category=category)
            if ret:
                return ret
        return None

    # ---------- 批量下载 ----------

    def batch_download(self,
                       in_from: SearchType,
                       media_list: list,
                       need_tvs: dict = None,
                       user_name=None):
        """
        根据命中的种子媒体信息，添加下载
        :return: 已经添加了下载的媒体信息列表、剩余未下载到的媒体信息
        """
        return_items = []
        download_list = Torrent().get_download_list(media_list, self._client_factory.download_order)

        def _download_item(download_item, torrent_file=None, tag=None, is_paused=None):
            _downloader_id, did, msg = self.download(
                media_info=download_item,
                download_dir=download_item.save_path,
                download_setting=download_item.download_setting,
                torrent_file=torrent_file,
                tag=tag,
                is_paused=is_paused,
                in_from=in_from,
                user_name=user_name
            )
            if did:
                if download_item not in return_items:
                    return_items.append(download_item)
            else:
                log.error(f"【Downloader】下载失败: {download_item.title}, 错误: {msg}")
            return _downloader_id, did, msg

        # 电影下载
        movie_items = MovieDownloadStrategy.download_movies(
            download_list=download_list,
            download_callback=lambda item: _download_item(item),
            get_download_url_callback=self.get_download_url
        )
        for it in movie_items:
            if it not in return_items:
                return_items.append(it)

        # 整季包下载
        need_seasons = SeasonPackStrategy.build_need_seasons(need_tvs)
        if need_seasons:
            season_items, _, need_tvs = SeasonPackStrategy.find_season_packs(
                download_list=download_list,
                need_seasons=need_seasons,
                need_tvs=need_tvs,
                get_download_url_callback=self.get_download_url,
                download_callback=lambda item, torrent_file=None: _download_item(item, torrent_file=torrent_file),
                get_torrent_episodes_callback=self.get_torrent_episodes
            )
            for it in season_items:
                if it not in return_items:
                    return_items.append(it)

        # 单集下载
        if need_tvs:
            return_items, need_tvs = EpisodeStrategy.download_episodes(
                download_list=download_list,
                need_tvs=need_tvs,
                get_download_url_callback=self.get_download_url,
                download_callback=lambda item: _download_item(item),
                get_torrent_episodes_callback=self.get_torrent_episodes,
                set_files_status_callback=self.set_files_status,
                start_torrents_callback=self.start_torrents,
                return_items=return_items
            )

        # 从整季包中选取需要的集数
        if need_tvs:
            return_items, need_tvs = EpisodeStrategy.download_from_season_pack(
                download_list=download_list,
                need_tvs=need_tvs,
                get_download_url_callback=self.get_download_url,
                download_callback=lambda item, torrent_file=None, is_paused=None: _download_item(
                    item, torrent_file=torrent_file, is_paused=is_paused
                ),
                get_torrent_episodes_callback=self.get_torrent_episodes,
                set_files_status_callback=self.set_files_status,
                start_torrents_callback=self.start_torrents,
                return_items=return_items
            )

        return return_items, need_tvs

    # ---------- 存在性检查 ----------

    def check_exists_medias(self, meta_info, no_exists=None, total_ep=None):
        """
        检查媒体库，查询是否存在
        """
        if not no_exists:
            no_exists = {}
        if not total_ep:
            total_ep = {}

        search_season = None if not meta_info.begin_season else meta_info.get_season_list()
        search_episode = meta_info.get_episode_list()
        if search_episode and not search_season:
            search_season = [1]

        message_list = []

        if meta_info.type != MediaType.MOVIE:
            return_flag = False
            tv_info = self._media.get_tmdb_info(mtype=MediaType.TV, tmdbid=meta_info.tmdb_id)
            if tv_info:
                total_seasons = []
                if search_season:
                    for season in search_season:
                        if total_ep.get(season):
                            episode_num = total_ep.get(season)
                        else:
                            episode_num = self._media.get_tmdb_season_episodes_num(tv_info=tv_info, season=season)
                        if not episode_num:
                            log.info("【Downloader】%s 第%s季 不存在" % (meta_info.get_title_string(), season))
                            message_list.append("%s 第%s季 不存在" % (meta_info.get_title_string(), season))
                            continue
                        total_seasons.append({"season_number": season, "episode_count": episode_num})
                        log.info("【Downloader】%s 第%s季 共有 %s 集" % (
                            meta_info.get_title_string(), season, episode_num))
                else:
                    total_seasons = self._media.get_tmdb_tv_seasons(tv_info=tv_info)
                    log.info("【Downloader】%s %s 共有 %s 季" % (
                        meta_info.type.value, meta_info.get_title_string(), len(total_seasons)))
                    message_list.append("%s %s 共有 %s 季" % (
                        meta_info.type.value, meta_info.get_title_string(), len(total_seasons)))

                if not total_seasons:
                    return_flag = None
                else:
                    for season in total_seasons:
                        season_number = season.get("season_number")
                        episode_count = season.get("episode_count")
                        if not season_number or not episode_count:
                            continue
                        no_exists_episodes = self._mediaserver.get_no_exists_episodes(meta_info,
                                                                                      season_number,
                                                                                      episode_count)
                        if no_exists_episodes is None:
                            no_exists_episodes = self._filetransfer.get_no_exists_medias(meta_info,
                                                                                         season_number,
                                                                                         episode_count)
                        if no_exists_episodes:
                            no_exists_episodes.sort()
                            if not no_exists.get(meta_info.tmdb_id):
                                no_exists[meta_info.tmdb_id] = []
                            exists_tvs_str = "、".join(["%s" % tv for tv in no_exists_episodes])
                            if len(no_exists_episodes) >= episode_count:
                                no_item = {"season": season_number, "episodes": [], "total_episodes": episode_count}
                                log.info("【Downloader】%s 第%s季 缺失 %s 集" % (
                                    meta_info.get_title_string(), season_number, episode_count))
                                if search_season:
                                    message_list.append("%s 第%s季 缺失 %s 集" % (
                                        meta_info.title, season_number, episode_count))
                                else:
                                    message_list.append("第%s季 缺失 %s 集" % (season_number, episode_count))
                            else:
                                no_item = {"season": season_number, "episodes": no_exists_episodes,
                                           "total_episodes": episode_count}
                                log.info("【Downloader】%s 第%s季 缺失集：%s" % (
                                    meta_info.get_title_string(), season_number, exists_tvs_str))
                                if search_season:
                                    message_list.append("%s 第%s季 缺失集：%s" % (
                                        meta_info.title, season_number, exists_tvs_str))
                                else:
                                    message_list.append("第%s季 缺失集：%s" % (season_number, exists_tvs_str))
                            if no_item not in no_exists.get(meta_info.tmdb_id):
                                no_exists[meta_info.tmdb_id].append(no_item)
                            if search_episode:
                                if not set(search_episode).intersection(set(no_exists_episodes)):
                                    msg = f"媒体库中已存在剧集：\n" \
                                          f" • {meta_info.get_title_string()} {meta_info.get_season_episode_string()}"
                                    log.info(f"【Downloader】{msg}")
                                    message_list.append(msg)
                                    return_flag = True
                                    break
                        else:
                            log.info("【Downloader】%s 第%s季 共%s集 已全部存在" % (
                                meta_info.get_title_string(), season_number, episode_count))
                            if search_season:
                                message_list.append("%s 第%s季 共%s集 已全部存在" % (
                                    meta_info.title, season_number, episode_count))
                            else:
                                message_list.append("第%s季 共%s集 已全部存在" % (season_number, episode_count))
            else:
                log.info("【Downloader】%s 无法查询到媒体详细信息" % meta_info.get_title_string())
                message_list.append("%s 无法查询到媒体详细信息" % meta_info.get_title_string())
                return_flag = None

            if return_flag is False and not no_exists.get(meta_info.tmdb_id):
                return_flag = True
            return return_flag, no_exists, message_list
        else:
            exists_movies = self._mediaserver.get_movies(meta_info.title, meta_info.year)
            if exists_movies is None:
                exists_movies = self._filetransfer.get_no_exists_medias(meta_info)
            if exists_movies:
                movies_str = "\n • ".join(["%s (%s)" % (m.get('title'), m.get('year')) for m in exists_movies])
                msg = f"媒体库中已存在电影：\n • {movies_str}"
                log.info(f"【Downloader】{msg}")
                message_list.append(msg)
                return True, {}, message_list
            return False, {}, message_list

    # ---------- 种子操作代理 ----------

    def get_torrents(self, downloader_id=None, ids=None, tag=None) -> list[torrent.Torrent]:
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return None
        try:
            torrents, error_flag = _client.get_torrents(tag=tag, ids=ids)
            if error_flag:
                return None
            return torrents
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return None

    def get_remove_torrents(self, downloader_id=None, config=None):
        if not config or not downloader_id:
            return []
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return []
        config["filter_tags"] = []
        from config import PT_TAG
        if config.get("onlynastool"):
            config["filter_tags"] = config["tags"] + [PT_TAG]
        else:
            config["filter_tags"] = config["tags"]
        torrents = _client.get_remove_torrents(config=config)
        torrents.sort(key=lambda x: x.get("name"))
        return torrents

    def get_downloading_torrents(self, downloader_id=None, ids=None, tag=None) -> list[torrent.Torrent]:
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return None
        try:
            return _client.get_downloading_torrents(tag=tag, ids=ids)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return None

    def get_downloading_progress(self, downloader_id=None, ids=None):
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        downloader_conf = self._client_factory.get_downloader_conf(downloader_id)
        only_nastool = downloader_conf.get("only_nastool") if downloader_conf else None
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return []
        from config import PT_TAG
        tag = [PT_TAG] if only_nastool else None
        return _client.get_downloading_progress(tag=tag, ids=ids)

    def get_completed_torrents(self, downloader_id=None, ids=None, tag=None) -> list[torrent.Torrent]:
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return None
        return _client.get_completed_torrents(ids=ids, tag=tag)

    def set_torrents_tag(self, downloader_id=None, ids=None, tags=None):
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return None
        _client.set_torrents_tag(ids=ids, tags=tags)

    def start_torrents(self, downloader_id=None, ids=None):
        if not ids:
            return False
        _client = self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        if not _client:
            return False
        return _client.start_torrents(ids)

    def stop_torrents(self, downloader_id=None, ids=None):
        if not ids:
            return False
        _client = self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        if not _client:
            return False
        return _client.stop_torrents(ids)

    def delete_torrents(self, downloader_id=None, ids=None, delete_file=False):
        if not ids:
            return False
        _client = self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        if not _client:
            return False
        return _client.delete_torrents(delete_file=delete_file, ids=ids)

    def get_files(self, tid, downloader_id=None):
        _client = self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        if not _client:
            return []
        torrent_files = _client.get_files(tid)
        if not torrent_files:
            return []
        ret_files = []
        if _client.get_type() == DownloaderType.TR:
            for file_id, torrent_file in enumerate(torrent_files):
                ret_files.append({"id": file_id, "name": torrent_file.name})
        elif _client.get_type() == DownloaderType.QB:
            for torrent_file in torrent_files:
                ret_files.append({"id": torrent_file.get("index"), "name": torrent_file.get("name")})
        return ret_files

    def set_files_status(self, tid, need_episodes, downloader_id=None):
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        downloader_conf = self._client_factory.get_downloader_conf(downloader_id)
        if not _client:
            return []
        torrent_files = self.get_files(tid=tid, downloader_id=downloader_id)
        if not torrent_files:
            return []
        sucess_epidised = []
        if downloader_conf.get("type") == "transmission":
            files_info = {}
            for torrent_file in torrent_files:
                file_id = torrent_file.get("id")
                file_name = torrent_file.get("name")
                meta_info = MetaInfo(file_name)
                if not meta_info.get_episode_list():
                    selected = False
                else:
                    selected = set(meta_info.get_episode_list()).issubset(set(need_episodes))
                    if selected:
                        sucess_epidised = list(set(sucess_epidised).union(set(meta_info.get_episode_list())))
                if not files_info.get(tid):
                    files_info[tid] = {file_id: {'priority': 'normal', 'selected': selected}}
                else:
                    files_info[tid][file_id] = {'priority': 'normal', 'selected': selected}
            if sucess_epidised and files_info:
                _client.set_files(file_info=files_info)
        elif downloader_conf.get("type") == "qbittorrent":
            file_ids = []
            for torrent_file in torrent_files:
                file_id = torrent_file.get("id")
                file_name = torrent_file.get("name")
                meta_info = MetaInfo(file_name)
                if not meta_info.get_episode_list() or not set(meta_info.get_episode_list()).issubset(
                        set(need_episodes)):
                    file_ids.append(file_id)
                else:
                    sucess_epidised = list(set(sucess_epidised).union(set(meta_info.get_episode_list())))
            if sucess_epidised and file_ids:
                _client.set_files(torrent_hash=tid, file_ids=file_ids, priority=0)
        return sucess_epidised

    def recheck_torrents(self, downloader_id=None, ids=None):
        if not ids:
            return False
        _client = self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        if not _client:
            return False
        return _client.recheck_torrents(ids)

    def set_speed_limit(self, downloader_id=None, download_limit=None, upload_limit=None):
        if not downloader_id:
            return
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return
        try:
            download_limit = int(download_limit) if download_limit else 0
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            download_limit = 0
        try:
            upload_limit = int(upload_limit) if upload_limit else 0
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            upload_limit = 0
        _client.set_speed_limit(download_limit=download_limit, upload_limit=upload_limit)

    # ---------- 种子解析 ----------

    def get_torrent_episodes(self, url, page_url=None):
        if not url:
            log.error("【Downloader】url 链接为空")
            return [], None
        site_info = self._sites.get_sites(siteurl=url)
        file_path, _, _, files, retmsg = Torrent().get_torrent_info(
            url=url,
            cookie=site_info.get("cookie"),
            ua=site_info.get("ua"),
            referer=page_url if site_info.get("referer") else None,
            proxy=site_info.get("proxy")
        )
        if not files:
            log.error("【Downloader】读取种子文件集数出错：%s" % retmsg)
            if file_path:
                Torrent().delete_torrent_file(file_path)
            return [], None
        episodes = []
        for file in files:
            if os.path.splitext(file)[-1] not in RMT_MEDIAEXT:
                continue
            meta = MetaInfo(file)
            if not meta.begin_episode:
                continue
            episodes = list(set(episodes).union(set(meta.get_episode_list())))
        return episodes, file_path

    # ---------- 历史记录 / 配置 CRUD 代理 ----------

    def get_download_history(self, date=None, hid=None, num=30, page=1):
        return self._download_repo.get_download_history(date=date, hid=hid, num=num, page=page)

    def get_download_history_by_title(self, title):
        return self._download_repo.get_download_history_by_title(title=title) or []

    def get_download_history_by_downloader(self, downloader, download_id):
        return self._download_repo.get_download_history_by_downloader(downloader=downloader, download_id=download_id)

    # ---------- 下载器 CRUD ----------

    def update_downloader(self, did, name, enabled, dtype, transfer,
                          only_nastool, match_path, rmt_mode, config, download_dir):
        from app.db.repositories import ConfigRepository
        ret = ConfigRepository().update_downloader(
            did=did, name=name, enabled=enabled, dtype=dtype, transfer=transfer,
            only_nastool=only_nastool, match_path=match_path, rmt_mode=rmt_mode,
            config=config, download_dir=download_dir
        )
        self._client_factory.init_config()
        return ret

    def delete_downloader(self, did):
        from app.db.repositories import ConfigRepository
        ret = ConfigRepository().delete_downloader(did=did)
        self._client_factory.init_config()
        return ret

    def check_downloader(self, did=None, transfer=None, only_nastool=None, enabled=None, match_path=None):
        from app.db.repositories import ConfigRepository
        ret = ConfigRepository().check_downloader(
            did=did, transfer=transfer, only_nastool=only_nastool,
            enabled=enabled, match_path=match_path
        )
        self._client_factory.init_config()
        return ret

    def delete_download_setting(self, sid):
        ret = self._download_repo.delete_download_setting(sid=sid)
        self._client_factory.init_config()
        return ret

    def update_download_setting(self, sid, name, category, tags, is_paused,
                                upload_limit, download_limit, ratio_limit,
                                seeding_time_limit, downloader):
        ret = self._download_repo.update_download_setting(
            sid=sid, name=name, category=category, tags=tags,
            is_paused=is_paused, upload_limit=upload_limit,
            download_limit=download_limit, ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit, downloader=downloader
        )
        self._client_factory.init_config()
        return ret

    # ---------- 静态工具 ----------

    @staticmethod
    def get_download_url(page_url):
        from urllib.parse import urlsplit
        import re
        from app.utils import JsonUtils, RequestUtils
        from config import MT_URL, Config
        if 'm-team' in page_url:
            base_url = MT_URL
        else:
            split_url = urlsplit(page_url)
            base_url = f"{split_url.scheme}://{split_url.netloc}"
        site_info = Sites().get_sites(siteurl=base_url)
        headers = site_info.get("headers")
        proxy = site_info.get("proxy")
        cookie = site_info.get("cookie")
        media_id = (re.findall(r'\d+', page_url) or [''])[0]
        if JsonUtils.is_valid_json(headers):
            headers = json.loads(headers)
        else:
            headers = {}
        headers.update({
            "contentType": "application/json; charset=utf-8",
            "User-Agent": f"{site_info.get('ua')}"
        })
        if 'm-team' in page_url:
            res = RequestUtils(headers=headers,
                               proxies=Config().get_proxies() if proxy else None,
                               timeout=15).post_res(url=f'{base_url}/api/torrent/genDlToken', data={'id': media_id})
            if res and res.status_code == 200:
                return res.json().get('data', '')
        if 'yemapt' in page_url:
            res = RequestUtils(headers=headers,
                               cookies=cookie,
                               proxies=Config().get_proxies() if proxy else None,
                               timeout=15).get_res(
                url=f'{base_url}/api/torrent/generateDownloadKey?id={media_id}')
            if res and res.status_code == 200:
                token = res.json().get('data', '')
                if token:
                    return f'{base_url}/api/torrent/download1?token={token}'
                return ''
        return None
