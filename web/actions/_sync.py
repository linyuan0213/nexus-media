import importlib
import os.path
import re
import shutil
from urllib.parse import unquote


import log
from app.conf import ModuleConf
from app.filetransfer import FileTransfer
from app.helper import ThreadHelper
from app.media import Media
from app.media.meta import MetaInfo
from app.plugins import EventManager
from app.sync import Sync
from app.utils import StringUtils, EpisodeFormat, PathUtils, SystemUtils, ExceptionUtils
from app.utils.types import RmtMode, OsType, SyncType, MediaType, MovieTypes, TvTypes, EventType
from config import RMT_MEDIAEXT, RMT_SUBEXT, RMT_AUDIO_TRACK_EXT, Config
from web.actions._base import WebActionBase


class WebActionSyncMixin:
    @staticmethod
    def _add_or_edit_sync_path(data):
        """
        维护同步目录
        """
        sid = data.get("sid")
        source = data.get("from")
        dest = data.get("to")
        unknown = data.get("unknown")
        mode = data.get("syncmod")
        compatibility = data.get("compatibility")
        rename = data.get("rename")
        enabled = data.get("enabled")

        _sync = Sync()

        # 源目录检查
        if not source:
            return WebActionBase._fail(msg=f'源目录不能为空')
        if not os.path.exists(source):
            return WebActionBase._fail(msg=f'{source}目录不存在')
        # windows目录用\，linux目录用/
        source = os.path.normpath(source)
        # 目的目录检查，目的目录可为空
        if dest:
            dest = os.path.normpath(dest)
            if PathUtils.is_path_in_path(source, dest):
                return WebActionBase._fail(msg="目的目录不可包含在源目录中")
        if unknown:
            unknown = os.path.normpath(unknown)

        # 硬链接不能跨盘
        if mode == "link" and dest:
            common_path = os.path.commonprefix([source, dest])
            if not common_path or common_path == "/":
                return WebActionBase._fail(msg="硬链接不能跨盘")

        # 编辑先删再增
        if sid:
            _sync.delete_sync_path(sid)
        # 若启用，则关闭其他相同源目录的同步目录
        if enabled == 1:
            _sync.check_source(source=source)
        # 插入数据库
        _sync.insert_sync_path(source=source,
                               dest=dest,
                               unknown=unknown,
                               mode=mode,
                               compatibility=compatibility,
                               rename=rename,
                               enabled=enabled)
        return WebActionBase._success(msg="")

    @staticmethod
    def get_sync_path(data=None):
        """
        查询同步目录
        """
        if data:
            sync_path = Sync().get_sync_path_conf(sid=data.get("sid"))
        else:
            sync_path = Sync().get_sync_path_conf()
        return WebActionBase._success(result=sync_path)

    @staticmethod
    def _delete_sync_path(data):
        """
        移出同步目录
        """
        sid = data.get("sid")
        Sync().delete_sync_path(sid)
        return WebActionBase._success()

    @staticmethod
    def _check_sync_path(data):
        """
        维护同步目录
        """
        flag = data.get("flag")
        sid = data.get("sid")
        checked = data.get("checked")

        _sync = Sync()

        if flag == "compatibility":
            _sync.check_sync_paths(sid=sid, compatibility=1 if checked else 0)
            return WebActionBase._success()
        elif flag == "rename":
            _sync.check_sync_paths(sid=sid, rename=1 if checked else 0)
            return WebActionBase._success()
        elif flag == "enable":
            # 若启用，则关闭其他相同源目录的同步目录
            if checked:
                _sync.check_source(sid=sid)
            _sync.check_sync_paths(sid=sid, enabled=1 if checked else 0)
            return WebActionBase._success()
        else:
            return WebActionBase._fail()

    @staticmethod
    def _run_directory_sync(data):
        """
        执行单个目录的目录同步
        """
        ThreadHelper().start_thread(Sync().transfer_sync, (data.get("sid"),))
        return WebActionBase._success(msg="执行成功")

    def _update_directory(self, data):
        """
        维护媒体库目录
        """
        cfg = self.set_config_directory(Config().get_config(),
                                        data.get("oper"),
                                        data.get("key"),
                                        data.get("value"),
                                        data.get("replace_value"))
        # 保存配置
        Config().save_config(cfg)
        return self._success()

    def _rename(self, data):
        """
        手工转移
        """
        path = dest_dir = None
        syncmod = ModuleConf.RMT_MODES.get(data.get("syncmod"))
        logid = data.get("logid")
        if logid:
            transinfo = FileTransfer().get_transfer_info_by_id(logid)
            if transinfo:
                path = os.path.join(
                    transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
                dest_dir = transinfo.DEST
            else:
                return self._fail(code=-1, msg="未查询到转移日志记录")
        else:
            unknown_id = data.get("unknown_id")
            if unknown_id:
                inknowninfo = FileTransfer().get_unknown_info_by_id(unknown_id)
                if inknowninfo:
                    path = inknowninfo.PATH
                    dest_dir = inknowninfo.DEST
                else:
                    return self._fail(code=-1, msg="未查询到未识别记录")
        if not dest_dir:
            dest_dir = ""
        if not path:
            return self._fail(code=-1, msg="输入路径有误")
        tmdbid = data.get("tmdb")
        mtype = data.get("type")
        season = data.get("season")
        episode_format = data.get("episode_format")
        episode_details = data.get("episode_details")
        episode_part = data.get("episode_part")
        episode_offset = data.get("episode_offset")
        min_filesize = data.get("min_filesize")
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        elif mtype in TvTypes:
            media_type = MediaType.TV
        else:
            media_type = MediaType.ANIME
        # 如果改次手动修复时一个单文件，自动修复改目录下同名文件，需要配合episode_format生效
        need_fix_all = False
        if os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT and episode_format:
            path = os.path.dirname(path)
            need_fix_all = True
        # 开始转移
        succ_flag, ret_msg = self._manual_transfer(inpath=path,
                                                   syncmod=syncmod,
                                                   outpath=dest_dir,
                                                   media_type=media_type,
                                                   episode_format=episode_format,
                                                   episode_details=episode_details,
                                                   episode_part=episode_part,
                                                   episode_offset=episode_offset,
                                                   need_fix_all=need_fix_all,
                                                   min_filesize=min_filesize,
                                                   tmdbid=tmdbid,
                                                   season=season)
        if succ_flag:
            if not need_fix_all and not logid:
                # 更新记录状态
                FileTransfer().update_transfer_unknown_state(path)
            return self._success(msg="转移成功")
        else:
            return self._fail(code=2, msg=ret_msg)

    def _rename_udf(self, data):
        """
        自定义识别
        """
        inpath = data.get("inpath")
        if not os.path.exists(inpath):
            return self._fail(code=-1, msg="输入路径不存在")
        outpath = data.get("outpath")
        syncmod = ModuleConf.RMT_MODES.get(data.get("syncmod"))
        tmdbid = data.get("tmdb")
        mtype = data.get("type")
        season = data.get("season")
        episode_format = data.get("episode_format")
        episode_details = data.get("episode_details")
        episode_part = data.get("episode_part")
        episode_offset = data.get("episode_offset")
        min_filesize = data.get("min_filesize")
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        elif mtype in TvTypes:
            media_type = MediaType.TV
        else:
            media_type = MediaType.ANIME
        # 开始转移
        succ_flag, ret_msg = self._manual_transfer(inpath=inpath,
                                                   syncmod=syncmod,
                                                   outpath=outpath,
                                                   media_type=media_type,
                                                   episode_format=episode_format,
                                                   episode_details=episode_details,
                                                   episode_part=episode_part,
                                                   episode_offset=episode_offset,
                                                   min_filesize=min_filesize,
                                                   tmdbid=tmdbid,
                                                   season=season)
        if succ_flag:
            return self._success(msg="转移成功")
        else:
            return self._fail(code=2, msg=ret_msg)

    @staticmethod
    def _manual_transfer(inpath,
                         syncmod,
                         outpath=None,
                         media_type=None,
                         episode_format=None,
                         episode_details=None,
                         episode_part=None,
                         episode_offset=None,
                         min_filesize=None,
                         tmdbid=None,
                         season=None,
                         need_fix_all=False
                         ):
        """
        开始手工转移文件
        """
        inpath = os.path.normpath(inpath)
        if outpath:
            outpath = os.path.normpath(outpath)
        if not os.path.exists(inpath):
            return False, "输入路径不存在"
        if tmdbid:
            # 有输入TMDBID
            tmdb_info = Media().get_tmdb_info(mtype=media_type, tmdbid=tmdbid)
            if not tmdb_info:
                return False, "识别失败，无法查询到TMDB信息"
            # 按识别的信息转移
            succ_flag, ret_msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                               in_path=inpath,
                                                               rmt_mode=syncmod,
                                                               target_dir=outpath,
                                                               tmdb_info=tmdb_info,
                                                               media_type=media_type,
                                                               season=season,
                                                               episode=(
                                                                   EpisodeFormat(episode_format,
                                                                                 episode_details,
                                                                                 episode_part,
                                                                                 episode_offset),
                                                                   need_fix_all),
                                                               min_filesize=min_filesize,
                                                               udf_flag=True)
        else:
            # 按识别的信息转移
            succ_flag, ret_msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                               in_path=inpath,
                                                               rmt_mode=syncmod,
                                                               target_dir=outpath,
                                                               media_type=media_type,
                                                               episode=(
                                                                   EpisodeFormat(episode_format,
                                                                                 episode_details,
                                                                                 episode_part,
                                                                                 episode_offset),
                                                                   need_fix_all),
                                                               min_filesize=min_filesize,
                                                               udf_flag=True)
        return succ_flag, ret_msg

    @staticmethod
    def re_identification(data):
        """
        未识别的重新识别
        """
        flag = data.get("flag")
        ids = data.get("ids")
        ret_flag = True
        ret_msg = []
        _filetransfer = FileTransfer()
        if flag == "unidentification":
            for wid in ids:
                unknowninfo = _filetransfer.get_unknown_info_by_id(wid)
                if unknowninfo:
                    path = unknowninfo.PATH
                    dest_dir = unknowninfo.DEST
                    rmt_mode = ModuleConf.get_enum_item(
                        RmtMode, unknowninfo.MODE) if unknowninfo.MODE else None
                else:
                    return WebActionBase._fail(code=-1, msg="未查询到未识别记录")
                if not dest_dir:
                    dest_dir = ""
                if not path:
                    return WebActionBase._fail(code=-1, msg="未识别路径有误")
                succ_flag, msg = _filetransfer.transfer_media(in_from=SyncType.MAN,
                                                              rmt_mode=rmt_mode,
                                                              in_path=path,
                                                              target_dir=dest_dir)
                if succ_flag:
                    _filetransfer.update_transfer_unknown_state(path)
                else:
                    ret_flag = False
                    if msg not in ret_msg:
                        ret_msg.append(msg)
        elif flag == "history":
            for wid in ids:
                transinfo = _filetransfer.get_transfer_info_by_id(wid)
                if transinfo:
                    path = os.path.join(
                        transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
                    dest_dir = transinfo.DEST
                    rmt_mode = ModuleConf.get_enum_item(
                        RmtMode, transinfo.MODE) if transinfo.MODE else None
                else:
                    return WebActionBase._fail(code=-1, msg="未查询到转移日志记录")
                if not dest_dir:
                    dest_dir = ""
                if not path:
                    return WebActionBase._fail(code=-1, msg="未识别路径有误")
                succ_flag, msg = _filetransfer.transfer_media(in_from=SyncType.MAN,
                                                              rmt_mode=rmt_mode,
                                                              in_path=path,
                                                              target_dir=dest_dir)
                if not succ_flag:
                    ret_flag = False
                    if msg not in ret_msg:
                        ret_msg.append(msg)
        if ret_flag:
            return WebActionBase._success(msg="转移成功")
        else:
            return WebActionBase._fail(code=2, msg="、".join(ret_msg))

    def delete_history(self, data):
        """
        删除识别记录及文件
        """
        logids = data.get('logids') or []
        flag = data.get('flag')
        _filetransfer = FileTransfer()
        for logid in logids:
            # 读取历史记录
            transinfo = _filetransfer.get_transfer_info_by_id(logid)
            if transinfo:
                # 删除记录
                _filetransfer.delete_transfer_log_by_id(logid)
                # 根据flag删除文件
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
                # 删除该识别记录对应的转移记录
                _filetransfer.delete_transfer_blacklist(
                    "%s/%s" % (source_path, source_filename))
                dest = transinfo.DEST
                dest_path = transinfo.DEST_PATH
                dest_filename = transinfo.DEST_FILENAME
                if flag in ["del_source", "del_all"]:
                    # 删除源文件
                    del_flag, del_msg = self.delete_media_file(
                        source_path, source_filename)
                    if not del_flag:
                        log.error(del_msg)
                    else:
                        log.info(del_msg)
                        # 触发源文件删除事件
                        EventManager().send_event(EventType.SourceFileDeleted, {
                            "media_info": media_info,
                            "path": source_path,
                            "filename": source_filename
                        })
                if flag in ["del_dest", "del_all"]:
                    # 删除媒体库文件
                    if dest_path and dest_filename:
                        del_flag, del_msg = self.delete_media_file(
                            dest_path, dest_filename)
                        if not del_flag:
                            log.error(del_msg)
                        else:
                            log.info(del_msg)
                            # 触发媒体库文件删除事件
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
                        # 删除文件
                        dest_path = _filetransfer.get_dest_path_by_info(
                            dest=dest, meta_info=meta_info)
                        if dest_path and dest_path.find(meta_info.title) != -1:
                            rm_parent_dir = False
                            if not meta_info.get_season_list():
                                # 电影，删除整个目录
                                try:
                                    shutil.rmtree(dest_path)
                                    # 触发媒体库文件删除事件
                                    EventManager().send_event(EventType.LibraryFileDeleted, {
                                        "media_info": media_info,
                                        "path": dest_path
                                    })
                                except Exception as e:
                                    ExceptionUtils.exception_traceback(e)
                            elif not meta_info.get_episode_string():
                                # 电视剧但没有集数，删除季目录
                                try:
                                    shutil.rmtree(dest_path)
                                    # 触发媒体库文件删除事件
                                    EventManager().send_event(EventType.LibraryFileDeleted, {
                                        "media_info": media_info,
                                        "path": dest_path
                                    })
                                except Exception as e:
                                    ExceptionUtils.exception_traceback(e)
                                rm_parent_dir = True
                            else:
                                # 有集数的电视剧，删除对应的集数文件
                                for dest_file in PathUtils.get_dir_files(dest_path):
                                    file_meta_info = MetaInfo(
                                        os.path.basename(dest_file))
                                    if file_meta_info.get_episode_list() and set(
                                            file_meta_info.get_episode_list()
                                    ).issubset(set(meta_info.get_episode_list())):
                                        try:
                                            os.remove(dest_file)
                                            # 触发媒体库文件删除事件
                                            EventManager().send_event(EventType.LibraryFileDeleted, {
                                                "media_info": media_info,
                                                "path": os.path.dirname(dest_file),
                                                "filename": os.path.basename(dest_file)
                                            })
                                        except Exception as e:
                                            ExceptionUtils.exception_traceback(
                                                e)
                                rm_parent_dir = True
                            if rm_parent_dir \
                                    and not PathUtils.get_dir_files(os.path.dirname(dest_path), exts=RMT_MEDIAEXT):
                                # 没有媒体文件时，删除整个目录
                                try:
                                    shutil.rmtree(os.path.dirname(dest_path))
                                except Exception as e:
                                    ExceptionUtils.exception_traceback(e)
        return self._success()

    @staticmethod
    def _del_unknown_path(data):
        """
        删除路径
        """
        tids = data.get("id")
        if isinstance(tids, list):
            for tid in tids:
                if not tid:
                    continue
                FileTransfer().delete_transfer_unknown(tid)
            return WebActionBase._success()
        else:
            retcode = FileTransfer().delete_transfer_unknown(tids)
            return WebActionBase._fail(code=retcode)

    @staticmethod
    def _get_sub_path(data):
        """
        查询下级子目录
        """
        r = []
        try:
            ft = data.get("filter") or "ALL"
            d = data.get("dir")
            if not d or d == "/":
                if SystemUtils.get_system() == OsType.WINDOWS:
                    partitions = SystemUtils.get_windows_drives()
                    if partitions:
                        dirs = [os.path.join(partition, "/")
                                for partition in partitions]
                    else:
                        dirs = [os.path.join("C:/", f)
                                for f in os.listdir("C:/")]
                else:
                    dirs = [os.path.join("/", f) for f in os.listdir("/")]
            else:
                d = os.path.normpath(unquote(d))
                if not os.path.isdir(d):
                    d = os.path.dirname(d)
                dirs = [os.path.join(d, f) for f in os.listdir(d)]
            dirs.sort()
            for ff in dirs:
                if os.path.isdir(ff):
                    if 'ONLYDIR' in ft or 'ALL' in ft:
                        r.append({
                            "path": ff.replace("\\", "/"),
                            "name": os.path.basename(ff),
                            "type": "dir",
                            "rel": os.path.dirname(ff).replace("\\", "/")
                        })
                else:
                    ext = os.path.splitext(ff)[-1][1:]
                    flag = False
                    if 'ONLYFILE' in ft or 'ALL' in ft:
                        flag = True
                    elif "MEDIAFILE" in ft and f".{str(ext).lower()}" in RMT_MEDIAEXT:
                        flag = True
                    elif "SUBFILE" in ft and f".{str(ext).lower()}" in RMT_SUBEXT:
                        flag = True
                    elif "AUDIOTRACKFILE" in ft and f".{str(ext).lower()}" in RMT_AUDIO_TRACK_EXT:
                        flag = True
                    if flag:
                        r.append({
                            "path": ff.replace("\\", "/"),
                            "name": os.path.basename(ff),
                            "type": "file",
                            "rel": os.path.dirname(ff).replace("\\", "/"),
                            "ext": ext,
                            "size": StringUtils.str_filesize(os.path.getsize(ff))
                        })

        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return WebActionBase._fail(code=-1, message='加载路径失败: %s' % str(e))
        return WebActionBase._success(count=len(r), data=r)

    @staticmethod
    def _rename_file(data):
        """
        文件重命名
        """
        path = data.get("path")
        name = data.get("name")
        if path and name:
            try:
                shutil.move(path, os.path.join(os.path.dirname(path), name))
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return WebActionBase._fail(code=-1, msg=str(e))
        return WebActionBase._success()

    def _delete_files(self, data):
        """
        删除文件
        """
        files = data.get("files")
        if files:
            # 删除文件
            for file in files:
                del_flag, del_msg = self.delete_media_file(filedir=os.path.dirname(file),
                                                           filename=os.path.basename(file))
                if not del_flag:
                    log.error(del_msg)
                else:
                    log.info(del_msg)
        return self._success()

    @staticmethod
    def _test_connection(data):
        """
        测试连通性（已移除 eval，使用安全反射）
        """
        # 支持两种传入方式：命令数组或单个命令，单个命令时xx|xx模式解析为模块和类，进行动态引入
        command = data.get("command")
        ret = None
        module_obj = None
        if command:
            try:
                if isinstance(command, list):
                    for cmd_str in command:
                        ret = WebActionSyncMixin._exec_test_command(cmd_str)
                        if not ret:
                            break
                else:
                    if command.find("|") != -1:
                        module = command.split("|")[0]
                        class_name = command.split("|")[1]
                        module_obj = getattr(
                            importlib.import_module(module), class_name)()
                        if hasattr(module_obj, "init_config"):
                            module_obj.init_config()
                        ret = module_obj.get_status()
                    else:
                        ret = WebActionSyncMixin._exec_test_command(command)
                # 重载配置
                Config().init_config()
                if module_obj:
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
            except Exception as e:
                ret = None
                ExceptionUtils.exception_traceback(e)
            return WebActionBase._fail(code=0 if ret else 1)
        return WebActionBase._success()

    @staticmethod
    def _exec_test_command(command: str):
        """
        安全执行测试命令（替换 eval）
        仅允许白名单内的无参调用：ClassName().method_name()
        """
        m = re.match(r"^(\w+)\(\)\.(\w+)\(\)$", command.strip())
        if not m:
            return None
        obj_name, method_name = m.groups()
        safe_mapping = {
            "Config": ("config", "Config"),
            "Message": ("app.message", "Message"),
            "MessageCenter": ("app.message", "MessageCenter"),
            "Downloader": ("app.downloader", "Downloader"),
            "MediaServer": ("app.mediaserver", "MediaServer"),
            "Indexer": ("app.indexer", "Indexer"),
            "Sites": ("app.sites", "Sites"),
            "Sync": ("app.sync", "Sync"),
            "BrushTask": ("app.brushtask", "BrushTask"),
            "RssChecker": ("app.rsschecker", "RssChecker"),
            "TorrentRemover": ("app.torrentremover", "TorrentRemover"),
            "Rss": ("app.rss", "Rss"),
            "Subscribe": ("app.subscribe", "Subscribe"),
            "Scheduler": ("app.scheduler", "Scheduler"),
            "PluginManager": ("app.plugins", "PluginManager"),
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
