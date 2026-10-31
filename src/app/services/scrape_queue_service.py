"""刮削队列服务 — 转移完成前同步落盘，目录/整库刮削后台限并发执行."""

import log
from app.infrastructure.thread import ThreadExecutor
from app.media.scraper import Scraper
from app.utils import ExceptionUtils


class ScrapeQueueService:
    """刮削执行服务.

    - scrape_file_now：转移发布完成事件前同步生成 NFO/图片，避免媒体库先扫描到空元数据
    - submit_folder_scrape：目录/整库刮削仍异步限并发
    - 图片下载另有全局信号量限速
    """

    def __init__(self, scraper: Scraper, max_workers: int = 3):
        self._scraper = scraper
        self._executor = ThreadExecutor.named("scrape", max_workers=max_workers)

    def submit_file_scrape(self, media, dir_path: str, file_name: str, file_ext: str, dst_backend=None) -> None:
        """提交单文件刮削任务（非阻塞）."""
        # 深拷贝隔离 media，避免异步刮削与转移线程消息聚合并发修改同一对象
        self._executor.submit(
            self._scrape_file, media.model_copy(deep=True), dir_path, file_name, file_ext, dst_backend
        )

    def submit_folder_scrape(self, path: str, dst_backend=None, mode: str = "force_all") -> None:
        """提交目录刮削任务（非阻塞）."""
        self._executor.submit(self._scrape_folder, path, dst_backend, mode)

    def scrape_file_now(
        self, media, dir_path: str, file_name: str, file_ext: str, dst_backend=None, force: bool = False
    ) -> bool:
        """同步生成 NFO/图片，供转移在发布完成事件前确保元数据落盘."""
        return self._scrape_file(media.model_copy(deep=True), dir_path, file_name, file_ext, dst_backend, force=force)

    def _scrape_file(self, media, dir_path: str, file_name: str, file_ext: str, dst_backend, *, force=False) -> bool:
        try:
            result = self._scraper.gen_scraper_files(
                media=media,
                dir_path=dir_path,
                file_name=file_name,
                file_ext=file_ext,
                force=force,
                dst_backend=dst_backend,
            )
            return bool(result)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"[ScrapeQueue]单文件刮削失败 {dir_path}/{file_name}: {e}")
            return False

    def _scrape_folder(self, path: str, dst_backend, mode: str) -> None:
        try:
            self._scraper.folder_scraper(path=path, mode=mode, dst_backend=dst_backend)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"[ScrapeQueue]目录刮削失败 {path}: {e}")
