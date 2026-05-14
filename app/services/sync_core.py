"""
Sync 核心服务重构
拆分为 SyncService（业务） + SyncRepository（数据，已存在）
移除 SingletonMeta，依赖注入。
FileMonitorHandler 保留在此模块。
"""
import os
import threading
import traceback

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

import log
from app.core.constants import RMT_MEDIAEXT
from app.core.module_config import ModuleConf
from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
from app.db.repositories.transfer_repo_adapter import TransferHistoryRepositoryAdapter
from app.domain.interfaces.sync_repo import ISyncPathRepository
from app.domain.interfaces.transfer_repo import ITransferHistoryRepository
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.utils import ExceptionUtils, PathUtils
from app.utils.types import SyncType

_synced_files_lock = threading.Lock()
_need_sync_paths_lock = threading.Lock()
_observers_lock = threading.Lock()


class FileMonitorHandler(FileSystemEventHandler):
    """目录监控响应类"""

    def __init__(self, monpath, sync_core, **kwargs):
        super().__init__(**kwargs)
        self._watch_path = monpath
        self._sync = sync_core

    def on_created(self, event):
        self._sync.file_change_handler(event, "创建", event.src_path)

    def on_moved(self, event):
        self._sync.file_change_handler(event, "移动", event.dest_path)


class SyncCore:
    """同步核心服务（替代原 app.sync.Sync）"""

    def __init__(self,
                 filetransfer: FileTransfer | None = None,
                 sync_repo: ISyncPathRepository | None = None,
                 transfer_repo: ITransferHistoryRepository | None = None):
        self._filetransfer = filetransfer or FileTransfer()
        self._sync_repo = sync_repo or SyncPathRepositoryAdapter()
        self._transfer_repo = transfer_repo or TransferHistoryRepositoryAdapter()
        self._sync_path_confs: dict[str, dict] = {}
        self._monitor_sync_path_ids: list[int] = []
        self._observer: list[Observer] = []
        self._synced_files: list[str] = []
        self._need_sync_paths: dict[str, dict] = {}
        # 自动加载配置（不启动监控，避免 API 请求时重复创建 Observer）
        self._reload_config()

    def init_config(self):
        """兼容接口：重新加载配置并启动监控"""
        self._reload_config()
        self._start_monitoring()

    # ---------- 配置加载 ----------

    def _reload_config(self) -> None:
        self._sync_path_confs = {}
        self._monitor_sync_path_ids = []
        for sync_conf in self._sync_repo.get_config_sync_paths():
            if not sync_conf:
                continue
            sid = sync_conf.ID
            enabled = bool(sync_conf.ENABLED)
            rename = bool(sync_conf.RENAME)
            compatibility = bool(sync_conf.COMPATIBILITY)
            syncmode = sync_conf.MODE
            syncmode_enum = ModuleConf.RMT_MODES.get(syncmode)
            monpath = sync_conf.SOURCE
            target_path = sync_conf.DEST
            unknown_path = sync_conf.UNKNOWN

            log_parts = []
            if target_path:
                log_parts.append(f"目的目录：{target_path}")
            if unknown_path:
                log_parts.append(f"未识别目录：{unknown_path}")
            log_suffix = ""
            if rename:
                log_suffix += "，启用识别和重命名"
            if compatibility:
                log_suffix += "，启用兼容模式"
            log.info(f"【Sync】读取到监控目录：{monpath}，"
                     f"{'，'.join(log_parts)}转移方式：{syncmode_enum.value}{log_suffix}")
            if not enabled:
                log.info(f"【Sync】{monpath} 不进行监控和同步：手动关闭")
            if target_path and not os.path.exists(target_path) and syncmode_enum not in ModuleConf.REMOTE_RMT_MODES:
                log.info(f"【Sync】目的目录不存在，正在创建：{target_path}")
                os.makedirs(target_path)
            if unknown_path and not os.path.exists(unknown_path):
                log.info(f"【Sync】未识别目录不存在，正在创建：{unknown_path}")
                os.makedirs(unknown_path)

            self._sync_path_confs[str(sid)] = {
                'id': sid, 'from': monpath,
                'to': target_path or "", 'unknown': unknown_path or "",
                'syncmod': syncmode, 'syncmod_name': syncmode_enum.value,
                "compatibility": compatibility, 'rename': rename,
                'enabled': enabled
            }
            if monpath and os.path.exists(monpath) and enabled:
                self._monitor_sync_path_ids.append(sid)
            elif monpath and not os.path.exists(monpath):
                log.error(f"【Sync】{monpath} 目录不存在！")

    @property
    def monitor_sync_path_ids(self):
        return self._monitor_sync_path_ids

    def get_sync_path_conf(self, sid=None):
        if sid:
            return self._sync_path_confs.get(str(sid)) or {}
        return self._sync_path_confs

    # ---------- 监控服务 ----------

    def _start_monitoring(self):
        self.stop_service()
        for sid in self._monitor_sync_path_ids:
            sync_path_conf = self.get_sync_path_conf(sid)
            if not sync_path_conf:
                continue
            mon_path = sync_path_conf.get("from")
            try:
                if sync_path_conf.get("compatibility"):
                    observer = PollingObserver(timeout=10)
                else:
                    observer = Observer(timeout=10)
                with _observers_lock:
                    self._observer.append(observer)
                observer.schedule(FileMonitorHandler(mon_path, self), path=mon_path, recursive=True)
                observer.daemon = True
                observer.start()
                log.info(f"{mon_path} 的监控服务启动")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                err_msg = str(e)
                if "inotify" in err_msg and "reached" in err_msg:
                    log.warn(f"目录监控服务启动出现异常：{err_msg}，请在宿主机上执行 sysctl 调整 inotify 限制")
                else:
                    log.error(f"{mon_path} 启动目录监控失败：{err_msg}")

    def stop_service(self):
        with _observers_lock:
            if self._observer:
                for observer in self._observer:
                    try:
                        observer.stop()
                        observer.join()
                    except Exception as e:
                        log.error(f"【Sync】停止监控异常: {str(e)}")
                self._observer = []

    # ---------- 文件变化处理 ----------

    def file_change_handler(self, event, text, event_path):
        if event.is_directory:
            return
        try:
            if not os.path.exists(event_path):
                return
            log.debug("【Sync】文件%s：%s" % (text, event_path))
            need_handler_flag = False
            with _synced_files_lock:
                if event_path not in self._synced_files:
                    self._synced_files.append(event_path)
                    need_handler_flag = True
            if not need_handler_flag:
                log.debug("【Sync】文件已处理过：%s" % event_path)
                return

            from_dir = os.path.dirname(event_path)
            sync_id = None
            is_root_path = False
            for sid in self._monitor_sync_path_ids:
                sync_path_conf = self.get_sync_path_conf(sid)
                mon_path = sync_path_conf.get('from')
                target_path = sync_path_conf.get('to')
                unknown_path = sync_path_conf.get('unknown')
                if PathUtils.is_path_in_path(mon_path, event_path):
                    if os.path.normpath(mon_path) == os.path.normpath(from_dir):
                        is_root_path = True
                    sync_id = sid
                if PathUtils.is_path_in_path(target_path, event_path):
                    log.error(f"【Sync】{event_path} -> {target_path} 目的目录存在嵌套，无法同步！")
                    return
                if PathUtils.is_path_in_path(unknown_path, event_path):
                    log.error(f"【Sync】{event_path} -> {unknown_path} 未识别目录存在嵌套，无法同步！")
                    return
            if not sync_id:
                log.debug(f"【Sync】{event_path} 不在监控目录下，不处理 ...")
                return
            if self._filetransfer.is_target_dir_path(event_path):
                log.error(f"【Sync】{event_path} 是媒体库子目录，无法同步！")
                return
            if PathUtils.is_invalid_path(event_path):
                log.debug(f"【Sync】{event_path} 是回收站或隐藏的文件，不处理 ...")
                return

            sync_path_conf = self.get_sync_path_conf(sync_id)
            mon_path = sync_path_conf.get('from')
            target_path = sync_path_conf.get('to')
            unknown_path = sync_path_conf.get('unknown')
            rename = sync_path_conf.get('rename')
            sync_mode = ModuleConf.RMT_MODES.get(sync_path_conf.get('syncmod'))

            if not rename:
                self.__link(event_path, mon_path, target_path, sync_mode)
            else:
                name = os.path.basename(event_path)
                if not name:
                    return
                if name.lower() != "index.bdmv":
                    ext = os.path.splitext(name)[-1]
                    if ext.lower() not in RMT_MEDIAEXT:
                        return
                if is_root_path:
                    ret, ret_msg = self._filetransfer.transfer_media(
                        in_from=SyncType.MON, in_path=event_path,
                        target_dir=target_path, unknown_dir=unknown_path,
                        rmt_mode=sync_mode)
                    if not ret:
                        log.warn("【Sync】%s 转移失败：%s" % (event_path, ret_msg))
                else:
                    with _need_sync_paths_lock:
                        if self._need_sync_paths.get(from_dir):
                            files = self._need_sync_paths[from_dir].get('files') or []
                            if event_path not in files:
                                files.append(event_path)
                            self._need_sync_paths[from_dir].update({'files': files})
                        else:
                            self._need_sync_paths[from_dir] = {
                                'target': target_path, 'unknown': unknown_path,
                                'syncmod': sync_mode, 'files': [event_path]
                            }
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("【Sync】发生错误：%s - %s" % (str(e), traceback.format_exc()))

    def transfer_mon_files(self):
        with _need_sync_paths_lock:
            finished_paths = []
            for path in list(self._need_sync_paths):
                if not PathUtils.is_invalid_path(path) and os.path.exists(path):
                    log.info("【Sync】开始转移监控目录文件...")
                    target_info = self._need_sync_paths.get(path)
                    bluray_dir = PathUtils.get_bluray_dir(path)
                    if not bluray_dir:
                        src_path = path
                        files = target_info.get('files')
                    else:
                        src_path = bluray_dir
                        files = []
                    if src_path in finished_paths:
                        continue
                    finished_paths.append(src_path)
                    target_path = target_info.get('target')
                    unknown_path = target_info.get('unknown')
                    sync_mode = target_info.get('syncmod')
                    is_root_path = any(
                        os.path.normpath(self.get_sync_path_conf(sid).get("from")) == os.path.normpath(src_path)
                        for sid in self._monitor_sync_path_ids
                    )
                    ret, ret_msg = self._filetransfer.transfer_media(
                        in_from=SyncType.MON, in_path=src_path, files=files,
                        target_dir=target_path, unknown_dir=unknown_path,
                        rmt_mode=sync_mode, root_path=is_root_path)
                    if not ret:
                        log.warn("【Sync】%s转移失败：%s" % (path, ret_msg))
                self._need_sync_paths.pop(path)

    def transfer_sync(self, sid=None):
        if not sid:
            sids = self._monitor_sync_path_ids
        elif isinstance(sid, list):
            sids = sid
        else:
            sids = [sid]
        for sid in sids:
            sync_path_conf = self.get_sync_path_conf(sid)
            mon_path = sync_path_conf.get("from")
            target_path = sync_path_conf.get("to")
            unknown_path = sync_path_conf.get("unknown")
            rename = sync_path_conf.get("rename")
            sync_mode = ModuleConf.RMT_MODES.get(sync_path_conf.get("syncmod"))
            if not rename:
                for link_file in PathUtils.get_dir_files(mon_path):
                    self.__link(link_file, mon_path, target_path, sync_mode)
            else:
                for path in PathUtils.get_dir_level1_medias(mon_path, RMT_MEDIAEXT):
                    if PathUtils.is_invalid_path(path):
                        continue
                    ret, ret_msg = self._filetransfer.transfer_media(
                        in_from=SyncType.MON, in_path=path,
                        target_dir=target_path, unknown_dir=unknown_path,
                        rmt_mode=sync_mode)
                    if not ret:
                        log.error("【Sync】%s 处理失败：%s" % (mon_path, ret_msg))

    def __link(self, event_path, mon_path, target_path, sync_mode):
        if self._transfer_repo.is_sync_in_history(event_path, target_path):
            return
        log.info("【Sync】开始同步 %s" % event_path)
        try:
            ret, msg = self._filetransfer.link_sync_file(
                src_path=mon_path, in_file=event_path,
                target_dir=target_path, sync_transfer_mode=sync_mode)
            if ret != 0:
                log.warn("【Sync】%s 同步失败，错误码：%s" % (event_path, ret))
            elif not msg:
                self._transfer_repo.insert_sync_history(event_path, mon_path, target_path)
                log.info("【Sync】%s 同步完成" % event_path)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            log.error("【Sync】%s 同步失败：%s" % (event_path, str(err)))

    def check_source(self, source=None, sid=None):
        if source:
            check_monpath = source
        elif sid:
            check_monpath = self.get_sync_path_conf(sid).get("from")
        else:
            return
        check_monpath = os.path.normpath(check_monpath)
        for sid, config in self._sync_path_confs.items():
            monpath = os.path.normpath(config.get("from"))
            if (PathUtils.is_path_in_path(monpath, check_monpath)
                    or PathUtils.is_path_in_path(check_monpath, monpath)) and config.get("enabled"):
                self._sync_repo.check_config_sync_paths(sid=sid, enabled=0)

    # ---------- 数据操作 ----------

    def delete_sync_path(self, sid):
        ret = self._sync_repo.delete_config_sync_path(sid=sid)
        self._reload_config()
        self._start_monitoring()
        return ret

    def insert_sync_path(self, source, dest, unknown, mode, compatibility, rename, enabled, note=None):
        ret = self._sync_repo.insert_config_sync_path(
            source=source, dest=dest, unknown=unknown,
            mode=mode, compatibility=compatibility,
            rename=rename, enabled=enabled, note=note)
        self._reload_config()
        self._start_monitoring()
        return ret

    def check_sync_paths(self, sid=None, compatibility=None, rename=None, enabled=None):
        ret = self._sync_repo.check_config_sync_paths(
            sid=sid, compatibility=compatibility,
            rename=rename, enabled=enabled)
        self._reload_config()
        self._start_monitoring()
        return ret
