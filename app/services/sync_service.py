# -*- coding: utf-8 -*-
"""
SyncService - 同步/转移业务层
将 web/controllers/sync.py 中的业务逻辑下沉到可独立测试的 Service。
"""
import os
from typing import List, Optional, Tuple

import log
from app.conf import ModuleConf
from app.filetransfer import FileTransfer
from app.media import Media
from app.media.meta import MetaInfo
from app.schemas.sync import (
    ManualTransferResultDTO,
    ReIdentifyResultDTO,
)
from app.sync import Sync
from app.utils import EpisodeFormat, PathUtils, ExceptionUtils
from app.utils.types import MediaType, MovieTypes, TvTypes, RmtMode, SyncType


class SyncService:
    """
    同步/转移业务服务
    负责：
    - 同步目录的校验与增删改查业务编排
    - 手工转移/自定义识别/重新识别的业务编排
    """

    def __init__(self,
                 sync: Optional[Sync] = None,
                 filetransfer: Optional[FileTransfer] = None,
                 media: Optional[Media] = None):
        self._sync = sync or Sync()
        self._filetransfer = filetransfer or FileTransfer()
        self._media = media or Media()

    # ---------- 同步目录校验 ----------

    def validate_sync_path(self, source: str, dest: str, mode: str) -> Tuple[bool, str]:
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

    def add_or_edit_sync_path(self, sid: int, source: str, dest: str,
                              unknown: str, mode: str, compatibility: int,
                              rename: int, enabled: int) -> Tuple[bool, str]:
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
            source=source, dest=dest, unknown=unknown,
            mode=mode, compatibility=compatibility,
            rename=rename, enabled=enabled
        )
        return True, ""

    def check_sync_path(self, sid: int, flag: str, checked: bool) -> Tuple[bool, str]:
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

    def manual_transfer(self,
                        inpath: str,
                        syncmod,
                        outpath: Optional[str] = None,
                        media_type: Optional[MediaType] = None,
                        episode_format: Optional[str] = None,
                        episode_details: Optional[str] = None,
                        episode_part: Optional[str] = None,
                        episode_offset: Optional[str] = None,
                        min_filesize: Optional[int] = None,
                        tmdbid: Optional[int] = None,
                        season: Optional[int] = None,
                        need_fix_all: bool = False) -> ManualTransferResultDTO:
        """
        手工转移文件
        """
        inpath = os.path.normpath(inpath)
        if outpath:
            outpath = os.path.normpath(outpath)
        if not os.path.exists(inpath):
            return ManualTransferResultDTO(success=False, message="输入路径不存在")

        episode = None
        if episode_format:
            episode = (EpisodeFormat(
                episode_format,
                episode_details or "",
                episode_part or "",
                episode_offset or ""
            ), need_fix_all)

        if tmdbid:
            tmdb_info = self._media.get_tmdb_info(mtype=media_type, tmdbid=tmdbid)
            if not tmdb_info:
                return ManualTransferResultDTO(success=False, message="识别失败，无法查询到TMDB信息")
            succ_flag, ret_msg = self._filetransfer.transfer_media(
                in_from=SyncType.MAN, in_path=inpath, rmt_mode=syncmod,
                target_dir=outpath, tmdb_info=tmdb_info, media_type=media_type,
                season=season, episode=episode, min_filesize=min_filesize, udf_flag=True
            )
        else:
            succ_flag, ret_msg = self._filetransfer.transfer_media(
                in_from=SyncType.MAN, in_path=inpath, rmt_mode=syncmod,
                target_dir=outpath, media_type=media_type,
                episode=episode, min_filesize=min_filesize, udf_flag=True
            )

        return ManualTransferResultDTO(success=succ_flag, message=ret_msg)

    # ---------- 重新识别 ----------

    def re_identify_items(self, flag: str, ids: list) -> ReIdentifyResultDTO:
        """
        批量重新识别（unidentification / history）
        :param flag: "unidentification" 或 "history"
        :param ids: ID 列表
        """
        ret_flag = True
        ret_msg = []

        for wid in ids:
            if flag == "unidentification":
                unknowninfo = self._filetransfer.get_unknown_info_by_id(wid)
                if not unknowninfo:
                    return ReIdentifyResultDTO(success=False, message="未查询到未识别记录")
                path = unknowninfo.PATH
                dest_dir = unknowninfo.DEST
                rmt_mode = ModuleConf.get_enum_item(
                    RmtMode, unknowninfo.MODE) if unknowninfo.MODE else None
            elif flag == "history":
                transinfo = self._filetransfer.get_transfer_info_by_id(wid)
                if not transinfo:
                    return ReIdentifyResultDTO(success=False, message="未查询到转移日志记录")
                path = os.path.join(transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
                dest_dir = transinfo.DEST
                rmt_mode = ModuleConf.get_enum_item(
                    RmtMode, transinfo.MODE) if transinfo.MODE else None
            else:
                return ReIdentifyResultDTO(success=False, message="不支持的识别类型")

            if not dest_dir:
                dest_dir = ""
            if not path:
                return ReIdentifyResultDTO(success=False, message="未识别路径有误")

            succ_flag, msg = self._filetransfer.transfer_media(
                in_from=SyncType.MAN, rmt_mode=rmt_mode,
                in_path=path, target_dir=dest_dir
            )
            if succ_flag:
                if flag == "unidentification":
                    self._filetransfer.update_transfer_unknown_state(path)
            else:
                ret_flag = False
                if msg not in ret_msg:
                    ret_msg.append(msg)

        if ret_flag:
            return ReIdentifyResultDTO(success=True, message="转移成功")
        return ReIdentifyResultDTO(success=False, message="、".join(ret_msg))

    # ---------- 查询 ----------

    def get_sync_paths(self, sid: Optional[int] = None):
        return self._sync.get_sync_path_conf(sid=sid)

    def get_transfer_info_by_id(self, logid: int):
        return self._filetransfer.get_transfer_info_by_id(logid)

    def get_unknown_info_by_id(self, tid: int):
        return self._filetransfer.get_unknown_info_by_id(tid)

    def get_sub_path(self, directory: str, ft: str = "ALL") -> List[dict]:
        """
        查询下级子目录/文件
        """
        from config import RMT_MEDIAEXT, RMT_SUBEXT, RMT_AUDIO_TRACK_EXT
        from app.utils import StringUtils
        from app.utils.types import OsType
        import os
        from urllib.parse import unquote

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
        return r
