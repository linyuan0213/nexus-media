# -*- coding: utf-8 -*-
"""
TransferCoordinator - 文件转移协调器

职责：
- 下载器监控调度（启动/停止定时转移任务）
- 下载完成文件的转移执行

将调度逻辑与下载核心逻辑分离，生命周期由外部（如 SystemLifecycleService）控制。
"""
from threading import Lock
from typing import Optional

import log
from app.conf import ModuleConf
from app.services.downloader_client_factory import DownloadClientFactory
from app.services.scheduler_core import SchedulerCore
from app.utils.types import RmtMode
from config import PT_TAG, PT_TRANSFER_INTERVAL

lock = Lock()


class TransferCoordinator:
    """
    文件转移协调器
    """

    def __init__(self,
                 client_factory: Optional[DownloadClientFactory] = None,
                 filetransfer=None,
                 scheduler: Optional[SchedulerCore] = None):
        from app.services.filetransfer_service import FileTransferService as FileTransfer
        self._client_factory = client_factory or DownloadClientFactory()
        self._filetransfer = filetransfer or FileTransfer()
        self._scheduler = scheduler or SchedulerCore()

    # ---------- 调度管理 ----------

    def start_service(self):
        """
        启动转移任务调度
        """
        self.stop_service()
        monitor_ids = self._client_factory.monitor_downloader_ids
        if not monitor_ids:
            return
        job_id = "Downloader.transfer"
        self._scheduler.start_job({
            "func": self.transfer,
            "name": "下载文件转移",
            "job_id": job_id,
            "trigger": "interval",
            "seconds": PT_TRANSFER_INTERVAL,
            "jobstore": self._client_factory.jobstore
        })
        log.info("下载文件转移服务启动，目的目录：媒体库")

    def stop_service(self):
        """
        停止转移任务调度
        """
        try:
            self._scheduler.remove_all_jobs(jobstore=self._client_factory.jobstore)
        except Exception as e:
            print(str(e))

    # ---------- 文件转移 ----------

    def transfer(self, downloader_id=None):
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
                # 获取下载器实例
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
