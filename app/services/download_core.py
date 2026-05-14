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

import os

import log
from app.core.constants import PT_TAG, RMT_MEDIAEXT
from app.core.system_config import SystemConfig
from app.db.repositories.download_repo_adapter import (
    DownloadHistoryRepositoryAdapter,
    DownloadSettingRepositoryAdapter,
)
from app.domain.interfaces.download_repo import IDownloadHistoryRepository
from app.downloader.client_factory import DownloadClientFactory
from app.downloader.pipeline import DownloadPipeline
from app.media import MetaInfo
from app.mediaserver import MediaServer
from app.message import Message
from app.plugin_framework.event_compat import EventManager
from app.schemas.download import Torrent
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.sites import SiteConf, Sites, SiteSubtitle
from app.utils import ExceptionUtils, Torrent
from app.utils.types import DownloaderType


class DownloadCore:
    """
    下载核心业务服务
    """

    def __init__(
        self,
        client_factory: DownloadClientFactory | None = None,
        message: Message | None = None,
        mediaserver: MediaServer | None = None,
        filetransfer: FileTransfer | None = None,
        sites: Sites | None = None,
        siteconf: SiteConf | None = None,
        sitesubtitle: SiteSubtitle | None = None,
        eventmanager: EventManager | None = None,
        download_repo: IDownloadHistoryRepository | None = None,
        download_setting_repo=None,
        systemconfig: SystemConfig | None = None,
    ):
        self._client_factory = client_factory or DownloadClientFactory()
        self._message = message or Message()
        self._mediaserver = mediaserver or MediaServer()
        self._filetransfer = filetransfer or FileTransfer()
        self._sites = sites or Sites()
        self._siteconf = siteconf or SiteConf()
        self._sitesubtitle = sitesubtitle or SiteSubtitle()
        self._eventmanager = eventmanager or EventManager()
        self._download_repo = download_repo or DownloadHistoryRepositoryAdapter()
        self._download_setting_repo = download_setting_repo or DownloadSettingRepositoryAdapter()
        self._systemconfig = systemconfig or SystemConfig()
        self._pipeline = DownloadPipeline(
            client_factory=self._client_factory,
            message=self._message,
            mediaserver=self._mediaserver,
            filetransfer=self._filetransfer,
            sites=self._sites,
            siteconf=self._siteconf,
            sitesubtitle=self._sitesubtitle,
            eventmanager=self._eventmanager,
        )

    # ---------- 核心下载方法 ----------

    def download(
        self,
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
        proxy=None,
    ):
        """
        添加下载任务，委托给 DownloadPipeline 执行

        :return: 下载器类型, 种子ID，错误信息
        """
        return self._pipeline.execute(
            media_info=media_info,
            is_paused=is_paused,
            tag=tag,
            download_dir=download_dir,
            download_setting=download_setting,
            downloader_id=downloader_id,
            upload_limit=upload_limit,
            download_limit=download_limit,
            torrent_file=torrent_file,
            in_from=in_from,
            user_name=user_name,
            proxy=proxy,
        )

    # ---------- 历史记录 / 配置 CRUD 代理 ----------

    def get_torrents(self, downloader_id=None, ids=None, tag=None) -> list[Torrent]:
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
        if config.get("onlynastool"):
            config["filter_tags"] = config["tags"] + [PT_TAG]
        else:
            config["filter_tags"] = config["tags"]
        torrents = _client.get_remove_torrents(config=config)
        torrents.sort(key=lambda x: x.get("name"))
        return torrents

    def get_downloading_torrents(self, downloader_id=None, ids=None, tag=None) -> list[Torrent]:
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return []
        try:
            return _client.get_downloading_torrents(tag=tag, ids=ids) or []
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return []

    def get_downloading_progress(self, downloader_id=None, ids=None):
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        downloader_conf = self._client_factory.get_downloader_conf(downloader_id)
        only_nastool = downloader_conf.get("only_nastool") if downloader_conf else None
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return []
        tag = [PT_TAG] if only_nastool else None
        try:
            return _client.get_downloading_progress(tag=tag, ids=ids) or []
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return []

    def get_completed_torrents(self, downloader_id=None, ids=None, tag=None) -> list[Torrent]:
        if not downloader_id:
            downloader_id = self._client_factory.default_downloader_id
        _client = self._client_factory.get_client(downloader_id)
        if not _client:
            return []
        try:
            return _client.get_completed_torrents(ids=ids, tag=tag) or []
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return []

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
        _client = (
            self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        )
        if not _client:
            return False
        return _client.start_torrents(ids)

    def stop_torrents(self, downloader_id=None, ids=None):
        if not ids:
            return False
        _client = (
            self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        )
        if not _client:
            return False
        return _client.stop_torrents(ids)

    def delete_torrents(self, downloader_id=None, ids=None, delete_file=False):
        if not ids:
            return False
        _client = (
            self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        )
        if not _client:
            return False
        return _client.delete_torrents(delete_file=delete_file, ids=ids)

    def get_files(self, tid, downloader_id=None):
        _client = (
            self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        )
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
                    files_info[tid] = {file_id: {"priority": "normal", "selected": selected}}
                else:
                    files_info[tid][file_id] = {"priority": "normal", "selected": selected}
            if sucess_epidised and files_info:
                _client.set_files(file_info=files_info)
        elif downloader_conf.get("type") == "qbittorrent":
            file_ids = []
            for torrent_file in torrent_files:
                file_id = torrent_file.get("id")
                file_name = torrent_file.get("name")
                meta_info = MetaInfo(file_name)
                if not meta_info.get_episode_list() or not set(meta_info.get_episode_list()).issubset(
                    set(need_episodes)
                ):
                    file_ids.append(file_id)
                else:
                    sucess_epidised = list(set(sucess_epidised).union(set(meta_info.get_episode_list())))
            if sucess_epidised and file_ids:
                _client.set_files(torrent_hash=tid, file_ids=file_ids, priority=0)
        return sucess_epidised

    def recheck_torrents(self, downloader_id=None, ids=None):
        if not ids:
            return False
        _client = (
            self._client_factory.get_client(downloader_id) if downloader_id else self._client_factory.default_client
        )
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
            proxy=site_info.get("proxy"),
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

    def update_downloader(
        self, did, name, enabled, dtype, transfer, only_nastool, match_path, rmt_mode, config, download_dir
    ):
        from app.db.repositories import ConfigRepository

        ret = ConfigRepository().update_downloader(
            did=did,
            name=name,
            enabled=enabled,
            dtype=dtype,
            transfer=transfer,
            only_nastool=only_nastool,
            match_path=match_path,
            rmt_mode=rmt_mode,
            config=config,
            download_dir=download_dir,
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
            did=did, transfer=transfer, only_nastool=only_nastool, enabled=enabled, match_path=match_path
        )
        self._client_factory.init_config()
        return ret

    def delete_download_setting(self, sid):
        ret = self._download_setting_repo.delete_download_setting(sid=sid)
        self._client_factory.init_config()
        return ret

    def update_download_setting(
        self,
        sid,
        name,
        category,
        tags,
        is_paused,
        upload_limit,
        download_limit,
        ratio_limit,
        seeding_time_limit,
        downloader,
    ):
        ret = self._download_setting_repo.update_download_setting(
            sid=sid,
            name=name,
            category=category,
            tags=tags,
            is_paused=is_paused,
            upload_limit=upload_limit,
            download_limit=download_limit,
            ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit,
            downloader=downloader,
        )
        self._client_factory.init_config()
        return ret

    # ---------- 静态工具 ----------

    @staticmethod
    def get_download_url(page_url):
        from app.sites.engine import SiteEngine

        site_info = Sites().get_sites(siteurl=page_url)
        return SiteEngine.get_instance().resolve_download_url(
            page_url=page_url,
            user_config={
                "cookie": site_info.get("cookie", ""),
                "ua": site_info.get("ua", ""),
                "headers": site_info.get("headers", {}),
                "proxy": site_info.get("proxy"),
            },
        )
