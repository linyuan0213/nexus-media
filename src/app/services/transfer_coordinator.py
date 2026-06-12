"""
TransferCoordinator - 文件转移协调器

职责：
- 下载器监控调度（启动/停止定时转移任务）

将调度逻辑与下载核心逻辑分离，生命周期由外部（如 SystemLifecycleService）控制。
"""

from collections.abc import Callable

import log
from app.core.constants import PT_TRANSFER_INTERVAL_FALLBACK
from app.downloader.client_factory import DownloadClientFactory
from app.services.scheduler_core import SchedulerCore


class TransferCoordinator:
    """
    文件转移协调器
    """

    def __init__(
        self,
        scheduler: SchedulerCore,
        client_factory: DownloadClientFactory | None = None,
    ):
        self._scheduler = scheduler
        self._client_factory = client_factory or DownloadClientFactory()

    # ---------- 调度管理 ----------

    def start_service(self, transfer_func: Callable[[str | None], None]):
        """
        启动转移任务调度
        :param transfer_func: 定时执行的转移函数，签名 transfer_func(downloader_id=None)
        """
        self.stop_service()
        monitor_ids = self._client_factory.monitor_downloader_ids
        if not monitor_ids:
            return
        job_id = "Downloader.transfer"
        self._scheduler.start_job(
            {
                "func": transfer_func,
                "name": "下载文件转移兜底",
                "job_id": job_id,
                "trigger": "interval",
                "seconds": PT_TRANSFER_INTERVAL_FALLBACK,
                "jobstore": self._client_factory.jobstore,
            }
        )
        log.info("下载文件转移兜底服务启动，目的目录：媒体库")

    def stop_service(self):
        """
        停止转移任务调度
        """
        try:
            self._scheduler.remove_all_jobs(jobstore=self._client_factory.jobstore)
        except Exception as e:
            log.error(str(e))
