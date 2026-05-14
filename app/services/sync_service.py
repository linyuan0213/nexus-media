"""
SyncService - 同步/转移业务层
将 web/controllers/sync.py 中的业务逻辑下沉到可独立测试的 Service。
"""

import os

from app.core.module_config import ModuleConf
from app.helper.thread_helper import ThreadHelper
from app.media import MediaCache
from app.schemas.sync import (
    ManualTransferResultDTO,
    ReIdentifyResultDTO,
    SimpleResultDTO,
)
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.sync_core import SyncCore as Sync
from app.utils import EpisodeFormat, ExceptionUtils, PathUtils
from app.utils.types import MediaType, MovieTypes, RmtMode, SyncType, TvTypes


class SyncService:
    """
    同步/转移业务服务
    负责：
    - 同步目录的校验与增删改查业务编排
    - 手工转移/自定义识别/重新识别的业务编排
    """

    def __init__(
        self,
        sync: Sync | None = None,
        filetransfer: FileTransfer | None = None,
        media_cache: MediaCache | None = None,
        threadhelper: ThreadHelper | None = None,
    ):
        self._sync = sync or Sync()
        self._filetransfer = filetransfer or FileTransfer()
        self._media_cache = media_cache or MediaCache()
        self._threadhelper = threadhelper or ThreadHelper()

    # ---------- 同步目录校验 ----------

    def validate_sync_path(self, source: str, dest: str, mode: str) -> tuple[bool, str]:
        """
        校验同步目录参数
        :return: (是否通过, 错误信息)
        """
        if not source:
            return False, "源目录不能为空"
        if not os.path.exists(source):
            return False, f"{source}目录不存在"
        source = os.path.normpath(source)
        if dest:
            dest = os.path.normpath(dest)
            if PathUtils.is_path_in_path(source, dest):
                return False, "目的目录不可包含在源目录中"
        if mode == "link" and dest:
            common_path = os.path.commonprefix([source, dest])
            if not common_path or common_path == "/":
                return False, "硬链接不能跨盘"
        return True, ""

    def add_or_edit_sync_path(
        self, sid: int, source: str, dest: str, unknown: str, mode: str, compatibility: int, rename: int, enabled: int
    ) -> tuple[bool, str]:
        """
        添加或编辑同步目录
        :return: (是否成功, 消息)
        """
        ok, msg = self.validate_sync_path(source, dest, mode)
        if not ok:
            return False, msg

        # windows目录用\，linux目录用/
        source = os.path.normpath(source)
        if dest:
            dest = os.path.normpath(dest)
        if unknown:
            unknown = os.path.normpath(unknown)

        # 编辑先删再增
        if sid:
            self._sync.delete_sync_path(sid)
        # 若启用，则关闭其他相同源目录的同步目录
        if enabled == 1:
            self._sync.check_source(source=source)
        # 插入数据库
        self._sync.insert_sync_path(
            source=source,
            dest=dest,
            unknown=unknown,
            mode=mode,
            compatibility=compatibility,
            rename=rename,
            enabled=enabled,
        )
        return True, ""

    def check_sync_path(self, sid: int, flag: str, checked: bool) -> tuple[bool, str]:
        """
        切换同步目录配置项
        :param flag: compatibility / rename / enable
        :return: (是否成功, 消息)
        """
        if flag == "compatibility":
            self._sync.check_sync_paths(sid=sid, compatibility=1 if checked else 0)
            return True, ""
        elif flag == "rename":
            self._sync.check_sync_paths(sid=sid, rename=1 if checked else 0)
            return True, ""
        elif flag == "enable":
            if checked:
                self._sync.check_source(sid=sid)
            self._sync.check_sync_paths(sid=sid, enabled=1 if checked else 0)
            return True, ""
        return False, ""

    # ---------- 手工转移 ----------

    def delete_sync_path(self, sid: int) -> SimpleResultDTO:
        """删除同步目录"""
        self._sync.delete_sync_path(sid)
        return SimpleResultDTO(success=True)

    @staticmethod
    def resolve_rmt_mode(syncmod_raw):
        """解析同步模式为 RmtMode 枚举"""
        return ModuleConf.RMT_MODES.get(syncmod_raw)

    @staticmethod
    def build_media_type(mtype: str) -> MediaType:
        """根据前端类型字符串解析为 MediaType 枚举"""
        if mtype in MovieTypes:
            return MediaType.MOVIE
        elif mtype in TvTypes:
            return MediaType.TV
        return MediaType.ANIME

    def manual_transfer(
        self,
        inpath: str,
        syncmod,
        outpath: str | None = None,
        media_type: MediaType | None = None,
        episode_format: str | None = None,
        episode_details: str | None = None,
        episode_part: str | None = None,
        episode_offset: str | None = None,
        min_filesize: int | None = None,
        tmdbid: int | None = None,
        season: int | None = None,
        need_fix_all: bool = False,
    ) -> ManualTransferResultDTO:
        """
        手工转移文件
        验证参数后提交后台线程执行，避免 API 超时
        """
        inpath = os.path.normpath(inpath)
        if outpath:
            outpath = os.path.normpath(outpath)
        if not os.path.exists(inpath):
            return ManualTransferResultDTO(success=False, message="输入路径不存在")

        episode = None
        if episode_format:
            episode = (
                EpisodeFormat(episode_format, episode_details or "", episode_part or "", episode_offset or ""),
                need_fix_all,
            )

        tmdb_info = None
        if tmdbid:
            tmdb_info = self._media_cache.get_tmdb_info(mtype=media_type, tmdbid=tmdbid)
            if not tmdb_info:
                return ManualTransferResultDTO(success=False, message="识别失败，无法查询到TMDB信息")

        # 提交后台线程执行转移，避免 API 超时
        self._threadhelper.start_thread(
            self._filetransfer.transfer_media,
            (
                SyncType.MAN,
                inpath,
                syncmod,
                None,
                outpath,
                None,
                tmdb_info,
                media_type,
                season,
                episode,
                min_filesize,
                True,
            ),
        )

        return ManualTransferResultDTO(success=True, message="转移任务已提交，正在后台执行")

    # ---------- 重新识别 ----------

    def re_identify_items(self, flag: str, ids: list) -> ReIdentifyResultDTO:
        """
        批量重新识别（unidentification / history）
        :param flag: "unidentification" 或 "history"
        :param ids: ID 列表
        提交后台线程执行，避免 API 超时
        """

        def _do_re_identify():
            for wid in ids:
                try:
                    if flag == "unidentification":
                        unknowninfo = self._filetransfer.get_unknown_info_by_id(wid)
                        if not unknowninfo:
                            continue
                        path = unknowninfo.PATH
                        dest_dir = unknowninfo.DEST
                        rmt_mode = ModuleConf.get_enum_item(RmtMode, unknowninfo.MODE) if unknowninfo.MODE else None
                    elif flag == "history":
                        transinfo = self._filetransfer.get_transfer_info_by_id(wid)
                        if not transinfo:
                            continue
                        path = os.path.join(transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
                        dest_dir = transinfo.DEST
                        rmt_mode = ModuleConf.get_enum_item(RmtMode, transinfo.MODE) if transinfo.MODE else None
                    else:
                        continue

                    if not dest_dir:
                        dest_dir = ""
                    if not path:
                        continue

                    succ_flag, msg = self._filetransfer.transfer_media(
                        in_from=SyncType.MAN, rmt_mode=rmt_mode, in_path=path, target_dir=dest_dir
                    )
                    if succ_flag and flag == "unidentification":
                        self._filetransfer.update_transfer_unknown_state(path)
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)

        self._threadhelper.start_thread(_do_re_identify, ())
        return ReIdentifyResultDTO(success=True, message="重新识别任务已提交，正在后台执行")

    # ---------- 查询 ----------

    def get_sync_paths(self, sid: int | None = None):
        return self._sync.get_sync_path_conf(sid=sid)

    def transfer_sync(self, sid: int | None = None):
        """触发指定同步目录的同步转移"""
        return self._sync.transfer_sync(sid=sid)

    def get_sync_path_conf(self, sid=None):
        """获取同步目录配置列表"""
        return self._sync.get_sync_path_conf(sid=sid)

    def get_transfer_info_by_id(self, logid: int):
        return self._filetransfer.get_transfer_info_by_id(logid)

    def get_unknown_info_by_id(self, tid: int):
        return self._filetransfer.get_unknown_info_by_id(tid)

    def get_sub_path(self, directory: str, ft: str = "ALL") -> list[dict]:
        """
        查询下级子目录/文件
        """
        import os
        from urllib.parse import unquote

        from app.core.constants import RMT_AUDIO_TRACK_EXT, RMT_MEDIAEXT, RMT_SUBEXT
        from app.utils import StringUtils
        from app.utils.types import OsType

        r = []
        if not directory or directory == "/":
            if os.name == "nt" or (hasattr(OsType, "WINDOWS") and False):
                # 简化处理，只处理 Linux 场景（项目主要运行在 Linux）
                dirs = [os.path.join("/", f) for f in os.listdir("/")]
            else:
                dirs = [os.path.join("/", f) for f in os.listdir("/")]
        else:
            d = os.path.normpath(unquote(directory))
            if not os.path.isdir(d):
                d = os.path.dirname(d)
            dirs = [os.path.join(d, f) for f in os.listdir(d)]
        dirs.sort()
        for ff in dirs:
            if os.path.isdir(ff):
                if "ONLYDIR" in ft or "ALL" in ft:
                    r.append(
                        {
                            "path": ff.replace("\\", "/"),
                            "name": os.path.basename(ff),
                            "type": "dir",
                            "rel": os.path.dirname(ff).replace("\\", "/"),
                        }
                    )
            else:
                ext = os.path.splitext(ff)[-1][1:]
                flag = False
                if (
                    "ONLYFILE" in ft
                    or "ALL" in ft
                    or "MEDIAFILE" in ft
                    and f".{str(ext).lower()}" in RMT_MEDIAEXT
                    or "SUBFILE" in ft
                    and f".{str(ext).lower()}" in RMT_SUBEXT
                    or "AUDIOTRACKFILE" in ft
                    and f".{str(ext).lower()}" in RMT_AUDIO_TRACK_EXT
                ):
                    flag = True
                if flag:
                    r.append(
                        {
                            "path": ff.replace("\\", "/"),
                            "name": os.path.basename(ff),
                            "type": "file",
                            "rel": os.path.dirname(ff).replace("\\", "/"),
                            "ext": ext,
                            "size": StringUtils.str_filesize(os.path.getsize(ff)),
                        }
                    )
        return r

    # ---------- 文件重命名 ----------

    @staticmethod
    def rename_file(path: str, name: str) -> SimpleResultDTO:
        """重命名文件/目录"""
        if not path or not name:
            return SimpleResultDTO(success=True)
        try:
            import shutil

            shutil.move(path, os.path.join(os.path.dirname(path), name))
            return SimpleResultDTO(success=True)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return SimpleResultDTO(success=False, message=str(e))

    # ---------- 测试命令执行 ----------

    @staticmethod
    def exec_test_command(cmd: str):
        """
        执行安全映射内的测试命令，返回调用结果或 None
        """
        import importlib
        import re

        m = re.match(r"^(\w+)\(\)\.(\w+)\(\)$", cmd.strip())
        if not m:
            return None
        obj_name, method_name = m.groups()
        safe_mapping = {
            "Config": ("config", "Config"),
            "Message": ("app.message", "Message"),
            "MessageCenter": ("app.message", "MessageCenter"),
            "Downloader": ("app.services.downloader_core", "DownloaderCore"),
            "MediaServer": ("app.mediaserver", "MediaServer"),
            "Indexer": ("app.indexer", "Indexer"),
            "Sites": ("app.sites", "Sites"),
            "Sync": ("app.sync", "Sync"),
            "BrushTask": ("app.brushtask", "BrushTask"),
            "RssChecker": ("app.services.rss_service", "RssTaskService"),
            "TorrentRemover": ("app.torrentremover", "TorrentRemover"),
            "Rss": ("app.rss", "Rss"),
            "Subscribe": ("app.subscribe", "Subscribe"),
            "SchedulerCore": ("app.services.scheduler_core", "SchedulerCore"),
            "Scraper": ("app.media", "Scraper"),
        }
        module_path, class_name = safe_mapping.get(obj_name, (None, None))
        if not module_path:
            return None
        try:
            cls = getattr(importlib.import_module(module_path), class_name)
            obj = cls()
            if hasattr(obj, method_name):
                return getattr(obj, method_name)()
        except Exception:
            pass
        return None

    @classmethod
    def test_connection(cls, command) -> SimpleResultDTO:
        """
        测试模块连接状态
        """
        import importlib

        ret = None
        module_obj = None
        if not command:
            return SimpleResultDTO(success=True)
        try:
            if isinstance(command, list):
                for cmd_str in command:
                    ret = cls.exec_test_command(cmd_str)
                    if not ret:
                        break
            else:
                if command.find("|") != -1:
                    module = command.split("|")[0]
                    class_name = command.split("|")[1]
                    module_obj = getattr(importlib.import_module(module), class_name)()
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
                    ret = module_obj.get_status()
                else:
                    ret = cls.exec_test_command(command)
            from config import Config

            Config().init_config()
            if module_obj:
                if hasattr(module_obj, "init_config"):
                    module_obj.init_config()
        except Exception as e:
            ret = None
            ExceptionUtils.exception_traceback(e)
        return SimpleResultDTO(success=bool(ret))

    # ---------- 目录配置更新 ----------

    @staticmethod
    def update_directory(oper: str, key: str, value: str, replace_value: str | None = None) -> SimpleResultDTO:
        """更新配置中的目录路径"""
        from app.utils.web_utils import set_config_directory
        from config import Config

        cfg = set_config_directory(Config().get_config(), oper, key, value, replace_value)
        Config().save_config(cfg)
        return SimpleResultDTO(success=True)
