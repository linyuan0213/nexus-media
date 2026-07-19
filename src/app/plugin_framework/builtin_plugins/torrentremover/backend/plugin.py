"""
TorrentRemover Plugin v2
历史记录中源文件被删除时，同步删除下载器中的下载任务
"""

import os

from app.plugin_framework.context import PluginContext
from app.services.downloader_core import DownloaderCore
from app.utils.json_utils import JsonUtils


class TorrentRemoverPlugin:
    """下载任务联动删除插件"""

    def __init__(self, ctx: PluginContext, downloader: DownloaderCore):
        self.ctx = ctx
        self._downloader = downloader

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("下载任务联动删除插件已启用")

    def on_disable(self):
        self.ctx.info("下载任务联动删除插件已禁用")

    def on_hook(self, event, data):
        if event == "media.source_deleted":
            self._delete_torrent(data or {})

    def _load_json(self, plugin_id: str, filename: str) -> dict:
        content = self.ctx.read_plugin_data(plugin_id, filename) or "{}"
        try:
            return JsonUtils.loads(content)
        except Exception:
            return {}

    def _delete_torrent(self, event_info):
        config = self._get_config()
        if not config.get("enable"):
            return

        source_path = event_info.get("path")
        source_filename = event_info.get("filename")
        media_title = event_info.get("media_info", {}).get("title")
        source_file = os.path.join(source_path, source_filename)

        downloadinfos = self._downloader.get_download_history_by_title(title=media_title)
        for info in downloadinfos:
            if not info.DOWNLOADER or not info.DOWNLOAD_ID:
                continue
            self._del_torrent(source_file=source_file, from_download=info.DOWNLOADER, from_download_id=info.DOWNLOAD_ID)

    def _del_torrent(self, source_file, from_download, from_download_id):
        download = from_download
        download_id = from_download_id

        # 查询转种记录（torrenttransfer 插件数据）
        history_key = f"{download}-{download_id}"
        transfer_data = self._load_json("torrenttransfer", "history.json")
        transfer_record = transfer_data.get(history_key)
        del_history = False

        if transfer_record and isinstance(transfer_record, dict):
            download = transfer_record.get("to_download")
            download_id = transfer_record.get("to_download_id")
            delete_source = transfer_record.get("delete_source")
            del_history = True

            if not delete_source:
                self.ctx.info(f"{history_key} 转种时未删除源下载任务，开始删除源下载任务")
                try:
                    dl_files = self._downloader.get_files(tid=from_download_id, downloader_id=from_download)
                    if dl_files:
                        for dl_file in dl_files:
                            if os.path.normpath(source_file).endswith(os.path.normpath(dl_file.get("name"))):
                                self.ctx.info(f"删除下载任务：{from_download} - {from_download_id}")
                                self._downloader.delete_torrents(downloader_id=from_download, ids=from_download_id)
                                break
                except Exception as e:
                    self.ctx.error(f"删除源下载任务 {history_key} 失败: {e}")

        # 删除目标（或源）下载器中的对应文件
        try:
            dl_files = self._downloader.get_files(tid=download_id, downloader_id=download)
            if not dl_files:
                return
            for dl_file in dl_files:
                if os.path.normpath(source_file).endswith(os.path.normpath(dl_file.get("name"))):
                    self.ctx.info(f"删除下载任务：{download} - {download_id}")
                    self._downloader.delete_torrents(downloader_id=download, ids=download_id)

                    if del_history:
                        self._remove_transfer_history(history_key)
                    self._del_seed(download, download_id)
                    break
        except Exception as e:
            self.ctx.error(f"删除下载任务 {download}-{download_id} 失败: {e}")

    def _del_seed(self, download, download_id):
        """清理关联的辅种种子（IYUU 插件 seed_history.json）"""
        seed_data = self._load_json("iyuuautoseed", "seed_history.json")
        if not seed_data:
            return
        modified = False
        for history_key, torrents in list(seed_data.items()):
            if not isinstance(torrents, list):
                continue
            for torrent_hash in torrents:
                self.ctx.info(f"删除辅种：{download} - {torrent_hash}")
                self._downloader.delete_torrents(downloader_id=download, ids=torrent_hash)
            del seed_data[history_key]
            modified = True
        if modified:
            self.ctx.write_data("_seed_history_cleanup.json", JsonUtils.dumps(seed_data))

    def _remove_transfer_history(self, history_key):
        """删除转种记录（torrenttransfer 插件数据）——通过事件通知或直接写回"""
        data = self._load_json("torrenttransfer", "history.json")
        if history_key in data:
            del data[history_key]
            self.ctx.write_data("_transfer_history_cleanup.json", JsonUtils.dumps(data))
