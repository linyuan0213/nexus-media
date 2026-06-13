"""
DiskSpaceSaver Plugin v2
计算文件SHA1，同磁盘下相同SHA1的文件只保留一个，其他的用硬链接替换
"""

import datetime
import hashlib
import os

from app.plugin_framework.context import PluginContext
from app.utils.json_utils import JsonUtils


class DiskSpaceSaverPlugin:
    """磁盘空间释放插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("磁盘空间释放插件已启用")

    def on_disable(self):
        self.ctx.info("磁盘空间释放插件已禁用")

    def run(self):
        """立即运行"""
        self.ctx.info("手动触发磁盘空间释放")
        self._do_dedup()

    def _do_dedup(self):
        config = self._get_config()
        path_list = config.get("path_list", "")
        file_size = config.get("file_size", 100)
        ext_list = config.get("ext_list", "")
        dry_run = config.get("dry_run", False)
        fast = config.get("fast", False)

        if isinstance(path_list, str):
            path_list = list(set(path_list.split("\n")))
        if isinstance(ext_list, str):
            ext_list = list(set(ext_list.split(",")))

        if not path_list or not file_size or not ext_list:
            self.ctx.info("磁盘空间释放配置信息不完整，不进行处理")
            return

        result_path = os.path.join(self.ctx.data_dir, "sha1.json")

        for path in path_list:
            if not path or not os.path.exists(path) or not os.path.isdir(path) or not os.path.isabs(path):
                continue

            last_result = self._load_last_result(result_path)
            self.ctx.info(f"磁盘空间释放 开始处理目录：{path}")
            self.ctx.info(f"加载上次处理结果，共有 {len(last_result['file_info'])} 个文件")
            duplicates = self._find_duplicates(path, ext_list, int(file_size), last_result, fast)
            self.ctx.info(f"找到 {len(duplicates)} 个重复文件")
            self._process_duplicates(duplicates, dry_run)
            self._save_last_result(result_path, last_result)
            self.ctx.info("磁盘空间释放 处理完毕")

    @staticmethod
    def _get_sha1(file_path, buffer_size=128 * 1024, fast=False):
        h = hashlib.sha1(usedforsecurity=False)
        buffer = bytearray(buffer_size)
        buffer_view = memoryview(buffer)
        with open(file_path, "rb", buffering=0) as f:
            if fast:
                file_size = os.path.getsize(file_path)
                n = f.readinto(buffer)
                h.update(buffer_view[:n])
                if file_size > buffer_size * 2:
                    f.seek(file_size // 2)
                    n = f.readinto(buffer)
                    h.update(buffer_view[:n])
                    f.seek(-buffer_size, os.SEEK_END)
                    n = f.readinto(buffer)
                    h.update(buffer_view[:n])
            else:
                for n in iter(lambda: f.readinto(buffer), 0):
                    h.update(buffer_view[:n])
        return h.hexdigest()

    def _find_duplicates(self, folder_path, _ext_list, _file_size, last_result, fast=False):
        duplicates = {}
        file_group_by_size = {}

        for dirpath, _dirnames, filenames in os.walk(folder_path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                file_ext = os.path.splitext(file_path)[1]
                file_size = os.path.getsize(file_path)
                if file_ext.lower() not in _ext_list:
                    continue
                if file_size < _file_size * 1024 * 1024:
                    continue
                file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_group_by_size.get(file_size) is None:
                    file_group_by_size[file_size] = []
                file_group_by_size[file_size].append(
                    {
                        "filePath": file_path,
                        "fileExt": file_ext,
                        "fileSize": file_size,
                        "fileModifyTime": str(file_mtime),
                    }
                )

        for file_size, file_list in file_group_by_size.items():
            if len(file_list) <= 1:
                continue
            for file_info in file_list:
                file_path = file_info["filePath"]
                file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                file_size = os.path.getsize(file_path)
                sha1 = None

                for info in last_result["file_info"]:
                    if file_path == info["filePath"]:
                        if file_size == info["fileSize"] and str(file_mtime) == info["fileModifyTime"]:
                            sha1 = info["fileSha1"]
                        break

                if sha1 is None:
                    sha1 = self._get_sha1(file_path, fast=fast)
                    last_result["file_info"].append(
                        {
                            "filePath": file_path,
                            "fileSize": file_size,
                            "fileModifyTime": str(file_mtime),
                            "fileSha1": sha1,
                        }
                    )

                if sha1 in duplicates:
                    duplicates[sha1].append(file_path)
                else:
                    duplicates[sha1] = [file_path]

        return duplicates

    def _process_duplicates(self, duplicates, dry_run=False):
        for _sha1, files in duplicates.items():
            if len(files) > 1:
                for file_path in files[1:]:
                    stat_first = os.stat(files[0])
                    stat_compare = os.stat(file_path)
                    if stat_first.st_dev == stat_compare.st_dev:
                        if stat_first.st_ino == stat_compare.st_ino:
                            self.ctx.info(f"文件 {files[0]} 和 {file_path} 是同一个文件，无需处理")
                        else:
                            if dry_run:
                                self.ctx.info(f"文件 {files[0]} 和 {file_path} 是重复文件，dry_run中，不做处理")
                                continue
                            try:
                                os.rename(file_path, file_path + ".bak")
                                os.link(files[0], file_path)
                                os.remove(file_path + ".bak")
                                self.ctx.info(f"文件 {files[0]} 和 {file_path} 是重复文件，已用硬链接替换")
                            except Exception:
                                os.rename(file_path + ".bak", file_path)
                                self.ctx.info(f"文件 {files[0]} 和 {file_path} 硬链接替换失败，已恢复原文件")
                    else:
                        self.ctx.info(f"文件 {files[0]} 和 {file_path} 不在同一个磁盘，无法用硬链接替换")

    @staticmethod
    def _load_last_result(last_result_path):
        if os.path.exists(last_result_path):
            with open(last_result_path) as f:
                return JsonUtils.load(f)
        return {"file_info": [], "inode_info": []}

    @staticmethod
    def _save_last_result(last_result_path, last_result):
        with open(last_result_path, "w") as f:
            JsonUtils.dump(last_result, f)
