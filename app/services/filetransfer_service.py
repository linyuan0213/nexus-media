# -*- coding: utf-8 -*-
"""
FileTransferService - 文件转移业务 Facade
将 app/filetransfer.py 重构为依赖注入模式，
底层实现拆分到 TransferActionEngine 与 TransferCoordinator。
保留与原 FileTransfer 兼容的公共 API。
"""
import argparse
import os
import random
import re
import shutil
import traceback
from time import sleep
from typing import Optional

import log
from app.conf import ModuleConf
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.db.repositories.transfer_repo_adapter import (
    TransferBlacklistRepositoryAdapter,
    TransferHistoryRepositoryAdapter,
    TransferUnknownRepositoryAdapter,
)
from app.domain.interfaces.download_repo import IDownloadHistoryRepository
from app.domain.interfaces.transfer_repo import (
    ITransferBlacklistRepository,
    ITransferHistoryRepository,
    ITransferUnknownRepository,
)
from app.helper import ProgressHelper, ThreadHelper
from app.media import Media, Category, Scraper
from app.media.meta import MetaInfo
from app.message import Message
from app.plugins import EventManager
from app.services.transfer_action_engine import TransferActionEngine
from app.utils import PathUtils, StringUtils, SystemUtils, ExceptionUtils, NumberUtils
from app.utils.types import EventType, MediaType, MovieTypes, ProgressKey, RmtMode, SyncType
from config import RMT_MEDIAEXT, RMT_FAVTYPE, RMT_MIN_FILESIZE, DEFAULT_MOVIE_FORMAT, \
    DEFAULT_TV_FORMAT, Config


class FileTransferService:
    """
    文件转移业务 Facade
    保留与原 FileTransfer 兼容的公共 API，移除 SingletonMeta，改为依赖注入。
    """

    def __init__(self,
                 media: Optional[Media] = None,
                 message: Optional[Message] = None,
                 category: Optional[Category] = None,
                 scraper: Optional[Scraper] = None,
                 threadhelper: Optional[ThreadHelper] = None,
                 transfer_repo: Optional[ITransferHistoryRepository] = None,
                 transfer_blacklist_repo: Optional[ITransferBlacklistRepository] = None,
                 transfer_unknown_repo: Optional[ITransferUnknownRepository] = None,
                 download_repo: Optional[IDownloadHistoryRepository] = None,
                 progress: Optional[ProgressHelper] = None,
                 eventmanager: Optional[EventManager] = None,
                 engine: Optional[TransferActionEngine] = None):
        self.media = media or Media()
        self.message = message or Message()
        self.category = category or Category()
        self.scraper = scraper or Scraper()
        self.threadhelper = threadhelper or ThreadHelper()
        self.transfer_repo = transfer_repo or TransferHistoryRepositoryAdapter()
        self.transfer_blacklist_repo = transfer_blacklist_repo or TransferBlacklistRepositoryAdapter()
        self.transfer_unknown_repo = transfer_unknown_repo or TransferUnknownRepositoryAdapter()
        self.download_repo = download_repo or DownloadHistoryRepositoryAdapter()
        self.progress = progress or ProgressHelper()
        self.eventmanager = eventmanager or EventManager()
        self._default_rmt_mode = None
        self._movie_path: list = []
        self._tv_path: list = []
        self._anime_path: list = []
        self._movie_category_flag = None
        self._tv_category_flag = None
        self._anime_category_flag = None
        self._unknown_path: list = []
        self._min_filesize = RMT_MIN_FILESIZE
        self._filesize_cover = False
        self._movie_dir_rmt_format = ""
        self._movie_file_rmt_format = ""
        self._tv_dir_rmt_format = ""
        self._tv_season_rmt_format = ""
        self._tv_file_rmt_format = ""
        self._ignored_paths: Optional[re.Pattern[str]] = None
        self._ignored_files: Optional[re.Pattern[str]] = None
        self._engine = engine or TransferActionEngine()
        self.init_config()

    def init_config(self):
        self.media = Media()
        self.message = Message()
        self.category = Category()
        self.scraper = Scraper()
        self.threadhelper = ThreadHelper()
        self.transfer_repo = TransferHistoryRepositoryAdapter()
        self.transfer_blacklist_repo = TransferBlacklistRepositoryAdapter()
        self.transfer_unknown_repo = TransferUnknownRepositoryAdapter()
        self.download_repo = DownloadHistoryRepositoryAdapter()
        self.progress = ProgressHelper()
        self.eventmanager = EventManager()

        media = Config().get_config('media')
        if media:
            movie_path = media.get('movie_path')
            if not isinstance(movie_path, list):
                if movie_path:
                    movie_path = [movie_path]
                else:
                    movie_path = []
            self._movie_path = movie_path
            self._movie_category_flag = self.category.movie_category_flag
            tv_path = media.get('tv_path')
            if not isinstance(tv_path, list):
                if tv_path:
                    tv_path = [tv_path]
                else:
                    tv_path = []
            self._tv_path = tv_path
            self._tv_category_flag = self.category.tv_category_flag
            anime_path = media.get('anime_path')
            if not isinstance(anime_path, list):
                if anime_path:
                    anime_path = [anime_path]
                else:
                    anime_path = []
            self._anime_path = anime_path
            self._anime_category_flag = self.category.anime_category_flag
            if not self._anime_path:
                self._anime_path = self._tv_path
                self._anime_category_flag = self._tv_category_flag
            unknown_path = media.get('unknown_path')
            if not isinstance(unknown_path, list):
                if unknown_path:
                    unknown_path = [unknown_path]
                else:
                    unknown_path = []
            self._unknown_path = unknown_path
            min_filesize = media.get('min_filesize')
            if isinstance(min_filesize, int):
                self._min_filesize = min_filesize * 1024 * 1024
            elif isinstance(min_filesize, str) and min_filesize.isdigit():
                self._min_filesize = int(min_filesize) * 1024 * 1024
            ignored_paths = media.get('ignored_paths')
            if ignored_paths:
                if ignored_paths.endswith(";"):
                    ignored_paths = ignored_paths[:-1]
                self._ignored_paths = re.compile(r'%s' % re.sub(r';', r'|', ignored_paths))
            ignored_files = media.get('ignored_files')
            if ignored_files:
                if ignored_files.endswith(";"):
                    ignored_files = ignored_files[:-1]
                self._ignored_files = re.compile(r'%s' % re.sub(r';', r'|', ignored_files))
            self._filesize_cover = media.get('filesize_cover')
            movie_name_format = media.get('movie_name_format') or DEFAULT_MOVIE_FORMAT
            movie_formats = movie_name_format.rsplit('/', 1)
            if movie_formats:
                self._movie_dir_rmt_format = movie_formats[0]
                if len(movie_formats) > 1:
                    self._movie_file_rmt_format = movie_formats[-1]
            tv_name_format = media.get('tv_name_format') or DEFAULT_TV_FORMAT
            tv_formats = tv_name_format.rsplit('/', 2)
            if tv_formats:
                self._tv_dir_rmt_format = tv_formats[0]
                if len(tv_formats) > 2:
                    self._tv_season_rmt_format = tv_formats[-2]
                    self._tv_file_rmt_format = tv_formats[-1]
        self._default_rmt_mode = ModuleConf.RMT_MODES.get(Config().get_config('pt').get('rmt_mode', 'copy'),
                                                           RmtMode.COPY)

    def is_target_dir_path(self, path):
        """
        判断是否为目的路径下的路径
        :param path: 路径
        :return: True/False
        """
        if not path:
            return False
        for tv_path in self._tv_path:
            if PathUtils.is_path_in_path(tv_path, path):
                return True
        for movie_path in self._movie_path:
            if PathUtils.is_path_in_path(movie_path, path):
                return True
        for anime_path in self._anime_path:
            if PathUtils.is_path_in_path(anime_path, path):
                return True
        for unknown_path in self._unknown_path:
            if PathUtils.is_path_in_path(unknown_path, path):
                return True
        return False

    def _is_media_exists(self, media_dest, media):
        """
        判断媒体文件是否已存在
        :param media_dest: 媒体文件所在目录
        :param media: 已识别的媒体信息
        :return: 目录是否存在，目录路径，文件是否存在，文件路径
        """
        dir_exist_flag = False
        file_exist_flag = False
        ret_dir_path = None
        ret_file_path = None
        if media.type == MediaType.MOVIE:
            dir_name, file_name = self.get_moive_dest_path(media)
            file_path = os.path.join(media_dest, dir_name)
            if self._movie_category_flag:
                file_path = os.path.join(media_dest, media.category, dir_name)
                for m_type in [RMT_FAVTYPE, media.category]:
                    type_path = os.path.join(media_dest, m_type, dir_name)
                    if os.path.exists(type_path):
                        file_path = type_path
                        break
            ret_dir_path = file_path
            if os.path.exists(file_path):
                dir_exist_flag = True
            file_dest = os.path.join(file_path, file_name)
            ret_file_path = file_dest
            for ext in RMT_MEDIAEXT:
                ext_dest = "%s%s" % (file_dest, ext)
                if os.path.exists(ext_dest):
                    file_exist_flag = True
                    ret_file_path = ext_dest
                    break
        else:
            dir_name, season_name, file_name = self.get_tv_dest_path(media)
            if (media.type == MediaType.TV and self._tv_category_flag) or (
                    media.type == MediaType.ANIME and self._anime_category_flag):
                media_path = os.path.join(media_dest, media.category, dir_name)
            else:
                media_path = os.path.join(media_dest, dir_name)
            if media.get_season_list():
                season_dir = os.path.join(media_path, season_name)
                ret_dir_path = season_dir
                if os.path.exists(season_dir):
                    dir_exist_flag = True
                episodes = media.get_episode_list()
                if episodes:
                    file_path = os.path.join(season_dir, file_name)
                    ret_file_path = file_path
                    for ext in RMT_MEDIAEXT:
                        ext_dest = "%s%s" % (file_path, ext)
                        if os.path.exists(ext_dest):
                            file_exist_flag = True
                            ret_file_path = ext_dest
                            break
        return dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path

    def get_dest_path_by_info(self, dest, meta_info):
        """
        拼装转移重命名后的新文件地址
        :param dest: 目的目录
        :param meta_info: 媒体信息
        """
        if not dest or not meta_info:
            return None
        if meta_info.type == MediaType.MOVIE:
            dir_name, _ = self.get_moive_dest_path(meta_info)
            if self._movie_category_flag:
                return os.path.join(dest, meta_info.category, dir_name)
            else:
                return os.path.join(dest, dir_name)
        else:
            dir_name, season_name, _ = self.get_tv_dest_path(meta_info)
            if self._tv_category_flag:
                return os.path.join(dest, meta_info.category, dir_name, season_name)
            else:
                return os.path.join(dest, dir_name, season_name)

    def get_no_exists_medias(self, meta_info, season=None, total_num=None):
        """
        根据媒体库目录结构，判断媒体是否存在
        :param meta_info: 已识别的媒体信息
        :param season: 季号，数字，剧集时需要
        :param total_num: 该季总集数，剧集时需要
        :return: 如果是电影返回已存在的电影清单：title、year，如果是剧集，则返回不存在的集的清单
        """
        if meta_info.type == MediaType.MOVIE:
            dir_name, _ = self.get_moive_dest_path(meta_info)
            for dest_path in self._movie_path:
                fav_path = os.path.join(dest_path, RMT_FAVTYPE, dir_name)
                fav_files = PathUtils.get_dir_files(fav_path, RMT_MEDIAEXT)
                if self._movie_category_flag:
                    dest_path = os.path.join(dest_path, meta_info.category, dir_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name)
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                if len(files) > 0 or len(fav_files) > 0:
                    return [{'title': meta_info.title, 'year': meta_info.year}]
            return []
        else:
            dir_name, season_name, _ = self.get_tv_dest_path(meta_info)
            if not season or not total_num:
                return []
            if meta_info.type == MediaType.ANIME:
                dest_paths = self._anime_path
                category_flag = self._anime_category_flag
            else:
                dest_paths = self._tv_path
                category_flag = self._tv_category_flag
            total_episodes = [episode for episode in range(1, total_num + 1)]
            exists_episodes = []
            for dest_path in dest_paths:
                if category_flag:
                    dest_path = os.path.join(dest_path, meta_info.category, dir_name, season_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name, season_name)
                if not os.path.exists(dest_path):
                    continue
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                for file in files:
                    file_meta_info = MetaInfo(title=os.path.basename(file))
                    if not file_meta_info.get_season_list() or not file_meta_info.get_episode_list():
                        continue
                    if file_meta_info.get_name() != meta_info.title:
                        continue
                    if not file_meta_info.is_in_season(season):
                        continue
                    exists_episodes = list(set(exists_episodes).union(set(file_meta_info.get_episode_list())))
            return list(set(total_episodes).difference(set(exists_episodes)))

    def get_best_target_path(self, mtype, in_path=None, size=0):
        """
        查询一个最好的目录返回，有in_path时找与in_path同路径的，没有in_path时，顺序查找1个符合大小要求的，没有in_path和size时，返回第1个
        :param mtype: 媒体类型：电影、电视剧、动漫
        :param in_path: 源目录
        :param size: 文件大小
        """
        if not mtype:
            return None
        if mtype == MediaType.MOVIE:
            dest_paths = self._movie_path
        elif mtype == MediaType.TV:
            dest_paths = self._tv_path
        else:
            dest_paths = self._anime_path
        if not dest_paths:
            return None
        if not isinstance(dest_paths, list):
            return dest_paths
        if isinstance(dest_paths, list) and len(dest_paths) == 1:
            return dest_paths[0]
        if in_path:
            max_return_path = None
            max_path_len = 0
            for dest_path in dest_paths:
                try:
                    path_len = len(os.path.commonpath([in_path, dest_path]))
                    if path_len > max_path_len:
                        max_path_len = path_len
                        max_return_path = dest_path
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
            if max_return_path:
                return max_return_path
        if size:
            for path in dest_paths:
                if SystemUtils.get_free_space(path) > NumberUtils.get_size_gb(size):
                    return path
        return dest_paths[0]

    def _get_best_unknown_path(self, in_path):
        """
        查找最合适的unknown目录
        :param in_path: 源目录
        """
        if not self._unknown_path:
            return None
        for unknown_path in self._unknown_path:
            if os.path.commonpath([in_path, unknown_path]) not in ["/", "\\"]:
                return unknown_path
        return self._unknown_path[0]

    def link_sync_file(self, src_path, in_file, target_dir, sync_transfer_mode):
        """
        对文件做纯链接处理，不做识别重命名，则监控模块调用
        :param : 来源渠道
        :param src_path: 源目录
        :param in_file: 源文件
        :param target_dir: 目的目录
        :param sync_transfer_mode: 明确的转移方式
        """
        new_file = in_file.replace(src_path, target_dir)
        new_file_list, msg = self.check_ignore(file_list=[new_file])
        if not new_file_list:
            return 0, msg
        else:
            new_file = new_file_list[0]
        new_dir = os.path.dirname(new_file)
        if not os.path.exists(new_dir) and sync_transfer_mode not in ModuleConf.REMOTE_RMT_MODES:
            os.makedirs(new_dir)
        return self._engine.transfer_command(file_item=in_file,
                                               target_file=new_file,
                                               rmt_mode=sync_transfer_mode), ""

    def get_format_dict(self, media):
        """
        根据媒体信息，返回Format字典
        """
        if not media:
            return {}
        episode_title = self.media.get_episode_title(media)
        en_title = self.media.get_tmdb_en_title(media)
        media_format_dict = {
            "title": StringUtils.clear_file_name(media.title),
            "en_title": StringUtils.clear_file_name(en_title),
            "original_name": StringUtils.clear_file_name(os.path.splitext(media.org_string or "")[0]),
            "rev_name": StringUtils.clear_file_name(os.path.splitext(media.rev_string or "")[0]),
            "original_title": StringUtils.clear_file_name(media.original_title),
            "name": StringUtils.clear_file_name(media.get_name()),
            "year": media.year,
            "edition": media.get_edtion_string() or None,
            "videoFormat": media.resource_pix,
            "releaseGroup": media.resource_team,
            "customization": media.customization,
            "effect": media.resource_effect,
            "videoCodec": media.video_encode,
            "audioCodec": media.audio_encode,
            "tmdbid": media.tmdb_id,
            "imdbid": media.imdb_id,
            "season": media.get_season_seq(),
            "episode": media.get_episode_seqs(),
            "episode_title": StringUtils.clear_file_name(episode_title),
            "season_episode": "%s%s" % (media.get_season_item(), media.get_episode_items()),
            "part": media.part
        }
        for i in media_format_dict.keys():
            if not media_format_dict[i]:
                media_format_dict[i] = '\t'
        return media_format_dict

    def get_moive_dest_path(self, media_info):
        """
        计算电影文件路径
        :return: 电影目录、电影名称
        """
        format_dict = self.get_format_dict(media_info)
        dir_name = re.sub(r"[-_\s.]*\t", "", self._movie_dir_rmt_format.format(**format_dict))
        file_name = re.sub(r"[-_\s.]*\t", "", self._movie_file_rmt_format.format(**format_dict))
        return dir_name, file_name

    def get_tv_dest_path(self, media_info):
        """
        计算电视剧文件路径
        :return: 电视剧目录、季目录、集名称
        """
        format_dict = self.get_format_dict(media_info)
        dir_name = re.sub(r"[-_\s.]*\t", "", self._tv_dir_rmt_format.format(**format_dict))
        season_name = re.sub(r"[-_\s.]*\t", "", self._tv_season_rmt_format.format(**format_dict))
        file_name = re.sub(r"[-_\s.]*\t", "", self._tv_file_rmt_format.format(**format_dict))
        return dir_name, season_name, file_name

    def check_ignore(self, file_list):
        """
        检查过滤文件列表中忽略项目
        :param file_list: 文件路径列表
        """
        if not file_list:
            return [], ""
        ignored_paths = self._ignored_paths
        if ignored_paths:
            try:
                for file in file_list[:]:
                    if re.findall(ignored_paths, os.path.dirname(file)):
                        log.info(f"【Rmt】{file} 文件路径含转移忽略词，已忽略转移")
                        file_list.remove(file)
                if not file_list:
                    return [], "排除文件路径转移忽略词后，没有新文件需要处理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Rmt】文件路径转移忽略词设置有误：%s" % str(err))

        ignored_files = self._ignored_files
        if ignored_files:
            try:
                for file in file_list[:]:
                    if re.findall(ignored_files, os.path.basename(file)):
                        log.info(f"【Rmt】{file} 文件名包含转移忽略词，已忽略转移")
                        file_list.remove(file)
                if not file_list:
                    return [], "排除文件名转移忽略词后，没有新文件需要处理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Rmt】文件名转移忽略词设置有误：%s" % str(err))

        return file_list, ""

    def transfer_media(self,
                       in_from,
                       in_path,
                       rmt_mode=None,
                       files=None,
                       target_dir=None,
                       unknown_dir=None,
                       tmdb_info=None,
                       media_type=None,
                       season=None,
                       episode=None,
                       min_filesize=None,
                       udf_flag=False,
                       root_path=False):
        """
        识别并转移一个文件、多个文件或者目录
        :param in_from: 来源，即调用该功能的渠道
        :param in_path: 转移的路径，可能是一个文件也可以是一个目录
        :param files: 文件清单，非空时以该文件清单为准，为空时从in_path中按后缀和大小限制搜索需要处理的文件清单
        :param target_dir: 目的文件夹，非空的转移到该文件夹，为空时则按类型转移到配置文件中的媒体库文件夹
        :param unknown_dir: 未识别文件夹，非空时未识别的媒体文件转移到该文件夹，为空时则使用配置文件中的未识别文件夹
        :param rmt_mode: 文件转移方式
        :param tmdb_info: 手动识别转移时传入的TMDB信息对象，如未输入，则按名称笔TMDB实时查询
        :param media_type: 手动识别转移时传入的文件类型，如未输入，则自动识别
        :param season: 手动识别目录或文件时传入的的字号，如未输入，则自动识别
        :param episode: (EpisodeFormat，是否批处理匹配)
        :param min_filesize: 过滤小文件大小的上限值
        :param udf_flag: 自定义转移标志，为True时代表是自定义转移，此时很多处理不一样
        :param root_path: 是否根目录下的文件
        :return: 处理状态，错误信息
        """

        def __finish_transfer(status, message):
            if status:
                self.progress.update(ptype=ProgressKey.FileTransfer,
                                      value=100,
                                      text=f"{in_path} 转移成功！")
            else:
                self.progress.update(ptype=ProgressKey.FileTransfer,
                                      value=100,
                                      text=f"{in_path} 转移失败：{message}！")
            self.progress.end(ProgressKey.FileTransfer)
            return status, message

        if not in_path:
            log.error("【Rmt】输入路径错误!")
            return __finish_transfer(False, "输入路径错误")

        if not os.path.exists(in_path):
            log.error("【Rmt】文件转移失败，目录或文件不存在：%s" % in_path)
            return __finish_transfer(False, "目录或文件不存在")

        # 默认转移方式
        if not rmt_mode:
            rmt_mode = self._default_rmt_mode

        # 开始进度
        self.progress.start(ProgressKey.FileTransfer)
        assert rmt_mode is not None
        log.info("【Rmt】开始处理：%s，转移方式：%s" % (in_path, rmt_mode.value))

        # 集定位参数
        episode = (None, False) if not episode else episode

        # 检查下载记录，是否有已识别的信息
        if not tmdb_info:
            download_info = self.download_repo.get_download_history_by_path(in_path)
            if not download_info and os.path.isfile(in_path):
                download_info = self.download_repo.get_download_history_by_path(os.path.dirname(in_path))
            if download_info and download_info.TMDBID:
                log.info(f"【Rmt】{in_path} 找到下载记录，"
                         f"TMDBID：{download_info.TMDBID}，"
                         f"标题：{download_info.TITLE}，"
                         f"类型：{download_info.TYPE}")
                media_type = MediaType.MOVIE if download_info.TYPE in MovieTypes else MediaType.TV
                tmdb_info = self.media.get_tmdb_info(mtype=media_type, tmdbid=download_info.TMDBID)

        # 成功标识
        success_flag = True
        # 错误信息
        error_message = ""
        # 蓝光原盘标识
        bluray_disk_dir = None

        # 统一转化为列表
        if not files:
            # 如果传入的是个目录
            if os.path.isdir(in_path):
                # 回收站及隐藏的文件不处理
                if PathUtils.is_invalid_path(in_path):
                    return __finish_transfer(False, "回收站或者隐藏文件夹")
                # 判断是不是原盘文件夹
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info("【Rmt】当前为蓝光原盘文件夹：%s" % str(in_path))
                else:
                    if str(min_filesize) == "0":
                        # 不限制大小
                        now_filesize = 0
                    else:
                        # 未输入大小限制默认为配置大小限制
                        min_filesize_str = "" if min_filesize is None else str(min_filesize)
                        now_filesize = self._min_filesize if not min_filesize_str.isdigit() else int(
                            min_filesize_str) * 1024 * 1024
                    # 查找目录下的文件
                    file_list = PathUtils.get_dir_files(in_path=in_path,
                                                        episode_format=episode[0],
                                                        exts=RMT_MEDIAEXT,
                                                        filesize=now_filesize)
                    log.debug("【Rmt】文件清单：" + str(file_list))
                    if len(file_list) == 0:
                        log.warn("【Rmt】%s 目录下未找到媒体文件，当前最小文件大小限制为 %s"
                                 % (in_path, StringUtils.str_filesize(now_filesize)))
                        return __finish_transfer(False,
                                                 "目录下未找到媒体文件，当前最小文件大小限制为 %s"
                                                 % StringUtils.str_filesize(now_filesize))
            # 传入的是个文件
            else:
                if os.path.splitext(in_path)[-1].lower() not in RMT_MEDIAEXT:
                    log.warn("【Rmt】不支持的媒体文件格式，不处理：%s" % in_path)
                    return __finish_transfer(False, "不支持的媒体文件格式")
                # 判断是不是原盘文件夹
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info("【Rmt】当前为蓝光原盘文件夹：%s" % bluray_disk_dir)
                else:
                    file_list = [in_path]
        else:
            # 传入的是个文件列表，这些文失件是in_path下面的文件
            file_list = files

        #  过滤掉文件列表
        file_list, msg = self.check_ignore(file_list=file_list)
        if not file_list:
            return __finish_transfer(True, msg)

        # 目录同步模式下，过滤掉文件列表中已处理过的
        if in_from == SyncType.MON:
            file_list = list(filter(self.transfer_repo.is_transfer_notin_blacklist, file_list))
            if not file_list:
                log.info("【Rmt】所有文件均已成功转移过，没有需要处理的文件！如需重新处理，请清理缓存（服务->清理转移缓存）")
                return __finish_transfer(True, "没有新文件需要处理")

        # API搜索出媒体信息，传入一个文件列表，得出每一个文件的名称，这里是当前目录下所有的文件了
        Medias = self.media.get_media_info_on_files(file_list, tmdb_info, media_type, season, episode[0])
        if not Medias:
            log.error("【Rmt】搜索媒体信息出错！")
            return __finish_transfer(False, "搜索媒体信息出错")

        # 更新进度
        self.progress.update(ptype=ProgressKey.FileTransfer, text=f"共 {len(Medias)} 个文件需要处理...")

        # 统计总的文件数、失败文件数、需要提醒的失败数
        failed_count = 0
        alert_count = 0
        alert_messages = []
        total_count = 0

        # 电视剧可能有多集，如果在循环里发消息就太多了，要在外面发消息
        message_medias = {}

        # 处理识别后的每一个文件或单个文件夹
        for file_item, media in Medias.items():
            try:
                # 总数量
                total_count = total_count + 1

                if not udf_flag:
                    if re.search(r'[./\s\[]+Sample[/\.\s\]]+', file_item, re.IGNORECASE):
                        log.warn("【Rmt】%s 可能是预告片，跳过..." % file_item)
                        continue

                # 文件名
                file_name = os.path.basename(file_item)
                # 更新进度
                self.progress.update(ptype=ProgressKey.FileTransfer,
                                     value=round(total_count / len(Medias) * 100) - (0.5 / len(Medias) * 100),
                                     text="正在处理：%s ..." % file_name)

                # 数据库记录的路径
                if bluray_disk_dir:
                    reg_path = bluray_disk_dir
                else:
                    reg_path = file_item
                # 未识别
                if not media or not media.tmdb_info or not media.get_title_string():
                    log.warn("【Rmt】%s 无法识别媒体信息！" % file_name)
                    success_flag = False
                    error_message = "无法识别媒体信息"
                    self.progress.update(ptype=ProgressKey.FileTransfer, text=error_message)
                    if udf_flag:
                        return __finish_transfer(success_flag, error_message)
                    # 记录未识别
                    is_need_insert_unknown = self.transfer_repo.is_need_insert_transfer_unknown(reg_path)
                    if is_need_insert_unknown:
                        self.transfer_repo.insert_transfer_unknown(reg_path, target_dir, rmt_mode)
                        alert_count += 1
                    failed_count += 1
                    if error_message not in alert_messages and is_need_insert_unknown:
                        alert_messages.append(error_message)
                    # 原样转移过去
                    if unknown_dir:
                        log.warn("【Rmt】%s 按原文件名转移到未识别目录：%s" % (file_name, unknown_dir))
                        self._engine.transfer_origin_file(file_item=file_item, target_dir=unknown_dir, rmt_mode=rmt_mode)
                    elif self._unknown_path:
                        unknown_path = self._get_best_unknown_path(in_path)
                        if not unknown_path:
                            continue
                        log.warn("【Rmt】%s 按原文件名转移到未识别目录：%s" % (file_name, unknown_path))
                        self._engine.transfer_origin_file(file_item=file_item, target_dir=unknown_path, rmt_mode=rmt_mode)
                    else:
                        log.error("【Rmt】%s 无法识别媒体信息！" % file_name)
                    continue
                # 当前文件大小
                media.size = os.path.getsize(file_item)
                # 目的目录，有输入target_dir时，往这个目录放
                if target_dir:
                    dist_path = target_dir
                else:
                    dist_path = self.get_best_target_path(mtype=media.type, in_path=in_path, size=media.size)
                if not dist_path:
                    log.error("【Rmt】文件转移失败，目的路径不存在！")
                    success_flag = False
                    error_message = "目的路径不存在"
                    failed_count += 1
                    alert_count += 1
                    if error_message not in alert_messages:
                        alert_messages.append(error_message)
                    continue
                if dist_path and not os.path.exists(dist_path) and rmt_mode not in ModuleConf.REMOTE_RMT_MODES:
                    return __finish_transfer(False, "目录不存在：%s" % dist_path)

                # 判断文件是否已存在，返回：目录存在标志、目录名、文件存在标志、文件名
                dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path = self._is_media_exists(dist_path, media)
                # 新文件后缀
                file_ext = os.path.splitext(file_item)[-1]
                new_file = ret_file_path
                # 已存在的文件数量
                exist_filenum = 0
                handler_flag = False
                # 路径存在
                if dir_exist_flag:
                    # 蓝光原盘
                    if bluray_disk_dir:
                        log.warn("【Rmt】蓝光原盘目录已存在：%s" % ret_dir_path)
                        if udf_flag:
                            return __finish_transfer(False, "蓝光原盘目录已存在：%s" % ret_dir_path)
                        failed_count += 1
                        continue
                    # 文件存在
                    if file_exist_flag:
                        exist_filenum = exist_filenum + 1
                        if rmt_mode != RmtMode.SOFTLINK:
                            assert ret_file_path is not None
                            orgin_file_size = os.path.getsize(ret_file_path)
                            if media.size > orgin_file_size and self._filesize_cover or udf_flag:
                                # 原文件
                                old_file = ret_file_path
                                # 拆分后缀
                                ret_file_path, ret_file_ext = os.path.splitext(ret_file_path)
                                # 新文件
                                new_file = "%s%s" % (ret_file_path, file_ext)
                                # 覆盖
                                log.info(
                                    f"【Rmt】文件 {old_file} 已存在，原文件大小：{orgin_file_size}，新文件大小：{media.size}，覆盖为 {new_file} ...")
                                ret = self._engine.transfer_file(file_item=file_item,
                                                                   new_file=new_file,
                                                                   rmt_mode=rmt_mode,
                                                                   over_flag=True,
                                                                   old_file=old_file)
                                if ret != 0:
                                    success_flag = False
                                    error_message = "文件转移失败，错误码 %s" % ret
                                    self.progress.update(ptype=ProgressKey.FileTransfer, text=error_message)
                                    if udf_flag:
                                        return __finish_transfer(success_flag, error_message)
                                    failed_count += 1
                                    alert_count += 1
                                    if error_message not in alert_messages:
                                        alert_messages.append(error_message)
                                    continue
                                handler_flag = True
                            else:
                                log.warn("【Rmt】文件 %s 已存在" % ret_file_path)
                                failed_count += 1
                                continue
                        else:
                            log.warn("【Rmt】文件 %s 已存在" % ret_file_path)
                            failed_count += 1
                            continue
                # 路径不存在
                else:
                    if not ret_dir_path:
                        log.error("【Rmt】拼装目录路径错误，无法从文件名中识别出季集信息：%s" % file_item)
                        success_flag = False
                        error_message = "识别失败，无法从文件名中识别出季集信息"
                        self.progress.update(ptype=ProgressKey.FileTransfer, text=error_message)
                        if udf_flag:
                            return __finish_transfer(success_flag, error_message)
                        # 记录未识别
                        is_need_insert_unknown = self.transfer_repo.is_need_insert_transfer_unknown(reg_path)
                        if is_need_insert_unknown:
                            self.transfer_repo.insert_transfer_unknown(reg_path, target_dir, rmt_mode)
                            alert_count += 1
                        failed_count += 1
                        if error_message not in alert_messages and is_need_insert_unknown:
                            alert_messages.append(error_message)
                        continue
                    elif rmt_mode not in ModuleConf.REMOTE_RMT_MODES:
                        # 创建目录
                        log.debug("【Rmt】正在创建目录：%s" % ret_dir_path)
                        os.makedirs(ret_dir_path)
                # 转移蓝光原盘
                if bluray_disk_dir:
                    ret = self._engine.transfer_bluray_dir(file_item, ret_dir_path, rmt_mode)
                    if ret != 0:
                        success_flag = False
                        error_message = "蓝光目录转移失败，错误码：%s" % ret
                        self.progress.update(ptype=ProgressKey.FileTransfer, text=error_message)
                        if udf_flag:
                            return __finish_transfer(success_flag, error_message)
                        failed_count += 1
                        alert_count += 1
                        if error_message not in alert_messages:
                            alert_messages.append(error_message)
                        continue
                else:
                    # 开始转移文件
                    if not handler_flag:
                        if not ret_file_path:
                            log.error("【Rmt】拼装文件路径错误，无法从文件名中识别出集数：%s" % file_item)
                            success_flag = False
                            error_message = "识别失败，无法从文件名中识别出集数"
                            self.progress.update(ptype=ProgressKey.FileTransfer, text=error_message)
                            if udf_flag:
                                return __finish_transfer(success_flag, error_message)
                            # 记录未识别
                            is_need_insert_unknown = self.transfer_repo.is_need_insert_transfer_unknown(reg_path)
                            if is_need_insert_unknown:
                                self.transfer_repo.insert_transfer_unknown(reg_path, target_dir, rmt_mode)
                                alert_count += 1
                            failed_count += 1
                            if error_message not in alert_messages and is_need_insert_unknown:
                                alert_messages.append(error_message)
                            continue
                        new_file = "%s%s" % (ret_file_path, file_ext)
                        ret = self._engine.transfer_file(file_item=file_item,
                                                           new_file=new_file,
                                                           rmt_mode=rmt_mode,
                                                           over_flag=False)
                        if ret != 0:
                            success_flag = False
                            error_message = "文件转移失败，错误码 %s" % ret
                            self.progress.update(ptype=ProgressKey.FileTransfer, text=error_message)
                            if udf_flag:
                                return __finish_transfer(success_flag, error_message)
                            failed_count += 1
                            alert_count += 1
                            if error_message not in alert_messages:
                                alert_messages.append(error_message)
                            continue
                # 查询TMDB详情，需要全部数据
                media.set_tmdb_info(self.media.get_tmdb_info(mtype=media.type,
                                                             tmdbid=media.tmdb_id,
                                                             append_to_response="all"))
                # 输出路径
                out_path = new_file if not bluray_disk_dir else ret_dir_path
                assert out_path is not None
                # 转移历史记录
                self.transfer_repo.insert_transfer_history(
                    in_from=in_from,
                    rmt_mode=rmt_mode,
                    in_path=reg_path,
                    out_path=out_path,
                    dest=dist_path,
                    media_info=media)
                # 未识别手动识别或历史记录重新识别的批处理模式
                if isinstance(episode[1], bool) and episode[1]:
                    # 未识别手动识别，更改未识别记录为已处理
                    self.update_transfer_unknown_state(file_item)
                # 电影立即发送消息
                if media.type == MediaType.MOVIE:
                    self.message.send_transfer_movie_message(in_from,
                                                              media,
                                                              exist_filenum,
                                                              self._movie_category_flag)
                # 否则登记汇总发消息
                else:
                    # 按季汇总
                    message_key = "%s-%s" % (media.get_title_string(), media.get_season_string())
                    if not message_medias.get(message_key):
                        message_medias[message_key] = media
                    # 汇总集数、大小
                    if not message_medias[message_key].is_in_episode(media.get_episode_list()):
                        message_medias[message_key].total_episodes += media.total_episodes
                        message_medias[message_key].size += media.size
                # 生成nfo及poster
                if bluray_disk_dir and media.type == MediaType.MOVIE:
                    # 原盘文件的情况下 使用目录名称.nfo 生成
                    assert ret_dir_path is not None
                    self.scraper.gen_scraper_files(media=media,
                                                    dir_path=ret_dir_path,
                                                    file_name=os.path.basename(ret_dir_path),
                                                    file_ext=file_ext,
                                                    rmt_mode=rmt_mode)
                else:
                    assert ret_file_path is not None
                    assert ret_dir_path is not None
                    self.scraper.gen_scraper_files(media=media,
                                                    dir_path=ret_dir_path,
                                                    file_name=os.path.basename(ret_file_path),
                                                    file_ext=file_ext,
                                                    rmt_mode=rmt_mode)
                # 更新进度
                self.progress.update(ptype=ProgressKey.FileTransfer,
                                     value=round(total_count / len(Medias) * 100),
                                     text="%s 转移完成" % file_name)

                # 移动模式随机休眠（兼容一些网盘挂载目录）
                if rmt_mode == RmtMode.MOVE:
                    sleep(round(random.uniform(0, 1), 1))

                # 解发字幕下载事件
                self.eventmanager.send_event(EventType.SubtitleDownload, {
                    "media_info": media.to_dict(),
                    "file": ret_file_path,
                    "file_ext": os.path.splitext(file_item)[-1],
                    "bluray": True if bluray_disk_dir else False
                })
                # 解发转移完成事件
                self.eventmanager.send_event(EventType.TransferFinished, {
                    "in_path": in_path,
                    "file": file_item,
                    "target_path": out_path,
                    "dest": dist_path,
                    "media_info": media.to_dict()
                })

            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Rmt】文件转移时发生错误：%s - %s" % (str(err), traceback.format_exc()))
        # 循环结束
        # 统计完成情况，发送通知
        if message_medias:
            self.message.send_transfer_tv_message(message_medias, in_from)
        # 总结
        log.info("【Rmt】%s 处理完成，总数：%s，失败：%s" % (in_path, total_count, failed_count))
        if alert_count > 0:
            reason = "、".join(alert_messages)
            # 解发事件
            self.eventmanager.send_event(EventType.TransferFail, {
                "path": in_path,
                "count": alert_count,
                "reason": reason
            })
            # 发送消息
            self.message.send_transfer_fail_message(in_path, alert_count, reason)
        elif failed_count == 0:
            # 删除空目录
            if rmt_mode == RmtMode.MOVE \
                    and os.path.exists(in_path) \
                    and os.path.isdir(in_path) \
                    and not root_path \
                    and not PathUtils.get_dir_files(in_path=in_path, exts=RMT_MEDIAEXT) \
                    and not PathUtils.get_dir_files(in_path=in_path, exts=['.!qb', '.part']):
                log.info("【Rmt】目录下已无媒体文件及正在下载的文件，移动模式下删除目录：%s" % in_path)
                shutil.rmtree(in_path)
        return __finish_transfer(success_flag, error_message)

    def transfer_manually(self, s_path, t_path, mode):
        """
        全量转移，用于使用命令调用
        :param s_path: 源目录
        :param t_path: 目的目录
        :param mode: 转移方式
        """
        if not s_path:
            return
        if not os.path.exists(s_path):
            print("【Rmt】源目录不存在：%s" % s_path)
            return
        if t_path:
            if not os.path.exists(t_path) and mode not in ModuleConf.REMOTE_RMT_MODES:
                print("【Rmt】目的目录不存在：%s" % t_path)
                return
        rmt_mode = ModuleConf.RMT_MODES.get(mode)
        if not rmt_mode:
            print("【Rmt】转移模式错误！")
            return
        print("【Rmt】转移模式为：%s" % rmt_mode.value)
        print("【Rmt】正在转移以下目录中的全量文件：%s" % s_path)
        for path in PathUtils.get_dir_level1_medias(s_path, RMT_MEDIAEXT):
            if PathUtils.is_invalid_path(path):
                continue
            ret, ret_msg = self.transfer_media(in_from=SyncType.MAN,
                                               in_path=path,
                                               target_dir=t_path,
                                               rmt_mode=rmt_mode)
            if not ret:
                print("【Rmt】%s 处理失败：%s" % (path, ret_msg))

    def get_transfer_info_by(self, tmdbid, season=None, season_episode=None):
        """
        查询转移历史记录
        """
        return self.transfer_repo.get_transfer_info_by(tmdbid=tmdbid,
                                                       season=season,
                                                       season_episode=season_episode)

    def get_transfer_info_by_id(self, logid):
        """
        根据LogID查询转移历史记录
        """
        return self.transfer_repo.get_transfer_info_by_id(logid=logid)

    def get_transfer_history(self, search, page, rownum):
        """
        查询转移历史记录
        """
        return self.transfer_repo.get_transfer_history(search=search, page=page, rownum=rownum)

    def delete_transfer_log_by_id(self, logid):
        """
        删除转移历史记录
        """
        return self.transfer_repo.delete_transfer_log_by_id(logid=logid)

    def delete_history(self, logids, flag=None):
        """
        删除识别记录及文件
        """
        for logid in logids:
            transinfo = self.get_transfer_info_by_id(logid)
            if transinfo:
                self.delete_transfer_log_by_id(logid)
                source_path = transinfo.SOURCE_PATH
                source_filename = transinfo.SOURCE_FILENAME
                media_info = {
                    "type": transinfo.TYPE,
                    "category": transinfo.CATEGORY,
                    "title": transinfo.TITLE,
                    "year": transinfo.YEAR,
                    "tmdbid": transinfo.TMDBID,
                    "season_episode": transinfo.SEASON_EPISODE
                }
                self.delete_transfer_blacklist(
                    "%s/%s" % (source_path, source_filename))
                dest = transinfo.DEST
                dest_path = transinfo.DEST_PATH
                dest_filename = transinfo.DEST_FILENAME
                if flag in ["del_source", "del_all"]:
                    del_flag, del_msg = self.delete_media_file(
                        source_path, source_filename)
                    if not del_flag:
                        log.error(del_msg)
                    else:
                        log.info(del_msg)
                        from app.plugins import EventManager
                        EventManager().send_event(EventType.SourceFileDeleted, {
                            "media_info": media_info,
                            "path": source_path,
                            "filename": source_filename
                        })
                if flag in ["del_dest", "del_all"]:
                    if dest_path and dest_filename:
                        del_flag, del_msg = self.delete_media_file(
                            dest_path, dest_filename)
                        if not del_flag:
                            log.error(del_msg)
                        else:
                            log.info(del_msg)
                            from app.plugins import EventManager
                            EventManager().send_event(EventType.LibraryFileDeleted, {
                                "media_info": media_info,
                                "path": dest_path,
                                "filename": dest_filename
                            })
                    else:
                        meta_info = MetaInfo(title=source_filename)
                        meta_info.title = transinfo.TITLE
                        meta_info.category = transinfo.CATEGORY
                        meta_info.year = transinfo.YEAR
                        if transinfo.SEASON_EPISODE:
                            meta_info.begin_season = int(
                                str(transinfo.SEASON_EPISODE).replace("S", ""))
                        if transinfo.TYPE == MediaType.MOVIE.value:
                            meta_info.type = MediaType.MOVIE
                        else:
                            meta_info.type = MediaType.TV
                        dest_path = self.get_dest_path_by_info(
                            dest=dest, meta_info=meta_info)
                        if dest_path and dest_path.find(meta_info.title) != -1:
                            rm_parent_dir = False
                            if not meta_info.get_season_list():
                                try:
                                    import shutil
                                    shutil.rmtree(dest_path)
                                    from app.plugins import EventManager
                                    EventManager().send_event(EventType.LibraryFileDeleted, {
                                        "media_info": media_info,
                                        "path": dest_path
                                    })
                                except Exception as e:
                                    from app.utils import ExceptionUtils
                                    ExceptionUtils.exception_traceback(e)
                            elif not meta_info.get_episode_string():
                                try:
                                    import shutil
                                    shutil.rmtree(dest_path)
                                    from app.plugins import EventManager
                                    EventManager().send_event(EventType.LibraryFileDeleted, {
                                        "media_info": media_info,
                                        "path": dest_path
                                    })
                                except Exception as e:
                                    from app.utils import ExceptionUtils
                                    ExceptionUtils.exception_traceback(e)
                                rm_parent_dir = True
                            else:
                                for dest_file in PathUtils.get_dir_files(dest_path):
                                    file_meta_info = MetaInfo(
                                        os.path.basename(dest_file))
                                    if file_meta_info.get_episode_list() and set(
                                            file_meta_info.get_episode_list()
                                    ).issubset(set(meta_info.get_episode_list())):
                                        try:
                                            os.remove(dest_file)
                                            from app.plugins import EventManager
                                            EventManager().send_event(EventType.LibraryFileDeleted, {
                                                "media_info": media_info,
                                                "path": os.path.dirname(dest_file),
                                                "filename": os.path.basename(dest_file)
                                            })
                                        except Exception as e:
                                            from app.utils import ExceptionUtils
                                            ExceptionUtils.exception_traceback(
                                                e)
                                rm_parent_dir = True
                            if rm_parent_dir \
                                    and not PathUtils.get_dir_files(os.path.dirname(dest_path), exts=RMT_MEDIAEXT):
                                try:
                                    import shutil
                                    shutil.rmtree(os.path.dirname(dest_path))
                                except Exception as e:
                                    from app.utils import ExceptionUtils
                                    ExceptionUtils.exception_traceback(e)

    @staticmethod
    def delete_media_file(filedir, filename):
        """
        删除媒体文件
        """
        try:
            file = os.path.join(filedir, filename)
            if os.path.exists(file):
                os.remove(file)
                if not os.listdir(filedir):
                    shutil.rmtree(filedir)
                return True, "删除成功"
            else:
                return False, "文件不存在"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False, str(e)

    def delete_transfer(self):
        """
        删除转移历史记录
        """
        return self.transfer_repo.delete_transfer()

    def delete_transfer_unknown(self, tid):
        """
        删除未知转移记录
        """
        return self.transfer_repo.delete_transfer_unknown(tid=tid)

    def get_unknown_info_by_id(self, tid):
        """
        根据ID查询未知转移记录
        """
        return self.transfer_repo.get_unknown_info_by_id(tid=tid)

    def update_transfer_unknown_state(self, path):
        """
        更新未知转移记录状态
        """
        return self.transfer_repo.update_transfer_unknown_state(path=path)

    def delete_transfer_blacklist(self, path):
        """
        删除黑名单记录
        """
        return self.transfer_repo.delete_transfer_blacklist(path=path)

    def truncate_transfer_blacklist(self):
        """
        清空黑名单记录
        """
        return self.transfer_repo.truncate_transfer_blacklist()

    def get_transfer_statistics(self, days=30):
        """
        查询转移统计
        """
        return self.transfer_repo.get_transfer_statistics(days=days)

    def get_transfer_unknown_paths(self):
        """
        查询未知转移记录
        """
        return self.transfer_repo.get_transfer_unknown_paths()

    def get_transfer_unknown_paths_by_page(self, search, page, rownum):
        """
        查询未知转移记录
        """
        return self.transfer_repo.get_transfer_unknown_paths_by_page(search=search, page=page, rownum=rownum)


if __name__ == "__main__":
    """
    手工转移时，使用命名行调用
    """
    Config().init_syspath()

    parser = argparse.ArgumentParser(description='文件转移工具')
    parser.add_argument('-m', '--mode', dest='mode', required=True,
                        help='转移模式：link copy softlink move rclone rclonecopy minio miniocopy')
    parser.add_argument('-s', '--source', dest='s_path', required=True, help='硬链接源目录路径')
    parser.add_argument('-d', '--target', dest='t_path', required=False, help='硬链接目的目录路径')
    args = parser.parse_args()
    if os.environ.get('NASTOOL_CONFIG'):
        print("【Rmt】配置文件地址：%s" % os.environ.get('NASTOOL_CONFIG'))
        print("【Rmt】源目录路径：%s" % args.s_path)
        if args.t_path:
            print("【Rmt】目的目录路径：%s" % args.t_path)
        else:
            print("【Rmt】目的目录为配置文件中的电影、电视剧媒体库目录")
        FileTransferService().transfer_manually(args.s_path, args.t_path, args.mode)
    else:
        print("【Rmt】未设置环境变量，请先设置 NASTOOL_CONFIG 环境变量为配置文件地址")
