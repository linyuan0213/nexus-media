# -*- coding: utf-8 -*-
"""
DownloaderCore - 下载器 Facade（兼容旧 Downloader 接口）

职责：
- 聚合 DownloadClientFactory、DownloadCore、TransferCoordinator
- 保留 Downloader 类名作为 Facade，兼容旧调用
- 内部委托给新服务，所有调用方无需修改

参考：app/services/search_service.py 中 Searcher 的做法
"""
from typing import Optional

import log
from app.core.module_config import ModuleConf
from app.downloader.client_factory import DownloadClientFactory
from app.services.download_core import DownloadCore
from app.services.filetransfer_service import FileTransferService
from threading import Lock

from app.services.transfer_coordinator import TransferCoordinator
from app.utils.types import RmtMode
from app.core.constants import PT_TAG


lock = Lock()


class DownloaderCore:
    """
    下载器核心 Facade

    聚合工厂、核心下载逻辑、转移协调三个子服务，
    对外暴露与原始 Downloader 完全一致的公共方法签名。
    """

    def __init__(self,
                 client_factory: Optional[DownloadClientFactory] = None,
                 download_core: Optional[DownloadCore] = None,
                 transfer_coordinator: Optional[TransferCoordinator] = None,
                 filetransfer: Optional[FileTransferService] = None):
        self._client_factory = client_factory or DownloadClientFactory()
        self._download_core = download_core or DownloadCore(client_factory=self._client_factory)
        self._filetransfer = filetransfer or FileTransferService()
        self._transfer_coordinator = transfer_coordinator or TransferCoordinator()

    # ---------- 生命周期（由外部 SystemLifecycleService 控制） ----------

    def init_config(self):
        """重新加载配置并启动转移调度"""
        self._client_factory.init_config()
        self._transfer_coordinator.start_service(self.transfer)

    def start_service(self):
        """启动转移任务调度"""
        self._transfer_coordinator.start_service(self.transfer)

    def stop_service(self):
        """停止转移任务调度"""
        self._transfer_coordinator.stop_service()

    # ---------- 属性代理 ----------

    @property
    def default_downloader_id(self):
        return self._client_factory.default_downloader_id

    def set_default_downloader_id(self, did: str) -> bool:
        return self._client_factory.set_default_downloader(did)

    @property
    def default_download_setting_id(self):
        return self._client_factory.default_download_setting_id

    def set_default_download_setting_id(self, sid: str) -> bool:
        return self._client_factory.set_default_download_setting(sid)

    @property
    def default_client(self):
        return self._client_factory.default_client

    @property
    def monitor_downloader_ids(self):
        return self._client_factory.monitor_downloader_ids

    # ---------- 核心下载 ----------

    def download(self, media_info, is_paused=None, tag=None, download_dir=None,
                 download_setting=None, downloader_id=None, upload_limit=None,
                 download_limit=None, torrent_file=None, in_from=None,
                 user_name=None, proxy=None):
        return self._download_core.download(
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
            proxy=proxy
        )

    def batch_download(self, in_from, media_list, need_tvs=None, user_name=None):
        return self._download_core.batch_download(
            in_from=in_from,
            media_list=media_list,
            need_tvs=need_tvs,
            user_name=user_name
        )

    # ---------- 转移 ----------

    def transfer(self, downloader_id: Optional[str] = None):
        """
        转移下载完成的文件，进行文件识别重命名到媒体库目录
        """
        downloader_ids = [downloader_id] if downloader_id else self._client_factory.monitor_downloader_ids
        downloader_enum = self._client_factory.downloader_enum
        for did in downloader_ids:
            with lock:
                downloader_conf = self._client_factory.get_downloader_conf(did)
                if not downloader_conf:
                    continue
                name = downloader_conf.get("name")
                only_nastool = downloader_conf.get("only_nastool")
                match_path = downloader_conf.get("match_path")
                rmt_mode = ModuleConf.RMT_MODES.get(downloader_conf.get("rmt_mode"))
                _client = self._client_factory.get_client(did)
            if not _client:
                continue
            trans_tasks = _client.get_transfer_task(tag=PT_TAG if only_nastool else None, match_path=match_path)
            if trans_tasks:
                log.info(f"【Downloader】下载器 {name} 开始转移下载文件...")
            else:
                continue
            for task in trans_tasks:
                done_flag, done_msg = self._filetransfer.transfer_media(
                    in_from=downloader_enum[str(did)],
                    in_path=task.get("path"),
                    rmt_mode=rmt_mode)
                if not done_flag:
                    log.warn(f"【Downloader】下载器 {name} 任务%s 转移失败：%s" % (task.get("path"), done_msg))
                    _client.set_torrents_status(ids=task.get("id"),
                                                tags=task.get("tags"))
                else:
                    if rmt_mode in [RmtMode.MOVE, RmtMode.RCLONE, RmtMode.MINIO]:
                        log.warn(f"【Downloader】下载器 {name} 移动模式下删除种子文件：%s" % task.get("id"))
                        _client.delete_torrents(delete_file=True, ids=task.get("id"))
                    else:
                        _client.set_torrents_status(ids=task.get("id"),
                                                    tags=task.get("tags"))
            log.info(f"【Downloader】下载器 {name} 下载文件转移结束")

    # ---------- 种子查询/操作 ----------

    def get_torrents(self, downloader_id=None, ids=None, tag=None):
        return self._download_core.get_torrents(downloader_id=downloader_id, ids=ids, tag=tag)

    def get_remove_torrents(self, downloader_id=None, config=None):
        return self._download_core.get_remove_torrents(downloader_id=downloader_id, config=config)

    def get_downloading_torrents(self, downloader_id=None, ids=None, tag=None):
        return self._download_core.get_downloading_torrents(downloader_id=downloader_id, ids=ids, tag=tag)

    def get_downloading_progress(self, downloader_id=None, ids=None):
        return self._download_core.get_downloading_progress(downloader_id=downloader_id, ids=ids)

    def get_completed_torrents(self, downloader_id=None, ids=None, tag=None):
        return self._download_core.get_completed_torrents(downloader_id=downloader_id, ids=ids, tag=tag)

    def set_torrents_tag(self, downloader_id=None, ids=None, tags=None):
        return self._download_core.set_torrents_tag(downloader_id=downloader_id, ids=ids, tags=tags)

    def start_torrents(self, downloader_id=None, ids=None):
        return self._download_core.start_torrents(downloader_id=downloader_id, ids=ids)

    def stop_torrents(self, downloader_id=None, ids=None):
        return self._download_core.stop_torrents(downloader_id=downloader_id, ids=ids)

    def delete_torrents(self, downloader_id=None, ids=None, delete_file=False):
        return self._download_core.delete_torrents(downloader_id=downloader_id, ids=ids, delete_file=delete_file)

    def get_files(self, tid, downloader_id=None):
        return self._download_core.get_files(tid=tid, downloader_id=downloader_id)

    def set_files_status(self, tid, need_episodes, downloader_id=None):
        return self._download_core.set_files_status(tid=tid, need_episodes=need_episodes, downloader_id=downloader_id)

    def recheck_torrents(self, downloader_id=None, ids=None):
        return self._download_core.recheck_torrents(downloader_id=downloader_id, ids=ids)

    def set_speed_limit(self, downloader_id=None, download_limit=None, upload_limit=None):
        return self._download_core.set_speed_limit(
            downloader_id=downloader_id, download_limit=download_limit, upload_limit=upload_limit
        )

    # ---------- 存在性检查 ----------

    def check_exists_medias(self, meta_info, no_exists=None, total_ep=None):
        return self._download_core.check_exists_medias(meta_info=meta_info, no_exists=no_exists, total_ep=total_ep)

    # ---------- 目录/设置查询 ----------

    def get_download_dirs(self, setting=None):
        return self._client_factory.get_download_dirs(setting=setting)

    def get_download_visit_dirs(self):
        return self._client_factory.get_download_visit_dirs()

    def get_download_visit_dir(self, download_dir, downloader_id=None):
        return self._client_factory.get_download_visit_dir(download_dir=download_dir, downloader_id=downloader_id)

    def get_download_setting(self, sid=None):
        return self._client_factory.get_download_setting(sid=sid)

    def get_downloader_conf(self, did=None):
        return self._client_factory.get_downloader_conf(did=did)

    def get_downloader_conf_simple(self):
        return self._client_factory.get_downloader_conf_simple()

    def get_downloader(self, downloader_id=None):
        return self._client_factory.get_client(downloader_id=downloader_id)

    def get_downloader_type(self, downloader_id=None):
        return self._client_factory.get_client_type(downloader_id=downloader_id)

    def get_status(self, dtype=None, config=None):
        return self._client_factory.get_status(dtype=dtype, config=config)

    def get_free_space(self, downloader_id, path: str):
        return self._client_factory.get_free_space(downloader_id=downloader_id, path=path)

    # ---------- 种子解析 ----------

    def get_torrent_episodes(self, url, page_url=None):
        return self._download_core.get_torrent_episodes(url=url, page_url=page_url)

    @staticmethod
    def get_download_url(page_url):
        return DownloadCore.get_download_url(page_url)

    # ---------- 历史记录 ----------

    def get_download_history(self, date=None, hid=None, num=30, page=1):
        return self._download_core.get_download_history(date=date, hid=hid, num=num, page=page)

    def get_download_history_by_title(self, title):
        return self._download_core.get_download_history_by_title(title=title)

    def get_download_history_by_downloader(self, downloader, download_id):
        return self._download_core.get_download_history_by_downloader(downloader=downloader, download_id=download_id)

    # ---------- 下载器 CRUD ----------

    def update_downloader(self, did, name, enabled, dtype, transfer,
                          only_nastool, match_path, rmt_mode, config, download_dir):
        return self._download_core.update_downloader(
            did=did, name=name, enabled=enabled, dtype=dtype, transfer=transfer,
            only_nastool=only_nastool, match_path=match_path, rmt_mode=rmt_mode,
            config=config, download_dir=download_dir
        )

    def delete_downloader(self, did):
        return self._download_core.delete_downloader(did=did)

    def check_downloader(self, did=None, transfer=None, only_nastool=None, enabled=None, match_path=None):
        return self._download_core.check_downloader(
            did=did, transfer=transfer, only_nastool=only_nastool,
            enabled=enabled, match_path=match_path
        )

    def delete_download_setting(self, sid):
        return self._download_core.delete_download_setting(sid=sid)

    def update_download_setting(self, sid, name, category, tags, is_paused,
                                upload_limit, download_limit, ratio_limit,
                                seeding_time_limit, downloader):
        return self._download_core.update_download_setting(
            sid=sid, name=name, category=category, tags=tags,
            is_paused=is_paused, upload_limit=upload_limit,
            download_limit=download_limit, ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit, downloader=downloader
        )
