"""
TransferActionEngine - 底层文件操作引擎
负责执行具体的文件系统操作（复制、移动、链接、字幕/音轨转移等）
"""

import os
import re
import shutil
from threading import Lock

import log
from app.core.constants import RMT_AUDIO_TRACK_EXT, RMT_SUBEXT
from app.core.module_config import ModuleConf
from app.db.repositories.transfer_repo_adapter import TransferBlacklistRepositoryAdapter
from app.domain.interfaces.transfer_repo import ITransferBlacklistRepository
from app.media import MetaInfo
from app.utils import ExceptionUtils, PathUtils, SystemUtils
from app.utils.types import RmtMode

lock = Lock()


class TransferActionEngine:
    """
    底层文件操作引擎
    负责执行具体的文件系统操作（复制、移动、链接、字幕/音轨转移等）
    """

    def __init__(self, blacklist_repo: ITransferBlacklistRepository | None = None):
        self._blacklist_repo = blacklist_repo or TransferBlacklistRepositoryAdapter()

    @staticmethod
    def transfer_command(file_item, target_file, rmt_mode):
        """
        使用系统命令处理单个文件
        :param file_item: 文件路径
        :param target_file: 目标文件路径
        :param rmt_mode: RmtMode转移方式
        """
        with lock:
            if rmt_mode == RmtMode.LINK:
                retcode, retmsg = SystemUtils.link(file_item, target_file)
            elif rmt_mode == RmtMode.SOFTLINK:
                retcode, retmsg = SystemUtils.softlink(file_item, target_file)
            elif rmt_mode == RmtMode.MOVE:
                retcode, retmsg = SystemUtils.move(file_item, target_file)
            elif rmt_mode == RmtMode.RCLONE:
                retcode, retmsg = SystemUtils.rclone_move(file_item, target_file)
            elif rmt_mode == RmtMode.RCLONECOPY:
                retcode, retmsg = SystemUtils.rclone_copy(file_item, target_file)
            elif rmt_mode == RmtMode.MINIO:
                retcode, retmsg = SystemUtils.minio_move(file_item, target_file)
            elif rmt_mode == RmtMode.MINIOCOPY:
                retcode, retmsg = SystemUtils.minio_copy(file_item, target_file)
            else:
                retcode, retmsg = SystemUtils.copy(file_item, target_file)
        if retcode != 0:
            log.error(f"【Rmt】{retmsg}")
        return retcode

    def transfer_other_files(self, org_name, new_name, rmt_mode, over_flag):
        """
        根据文件名转移其他相关文件
        :param org_name: 原文件名
        :param new_name: 新文件名
        :param rmt_mode: RmtMode转移方式
        :param over_flag: 是否覆盖，为True时会先删除再转移
        """
        retcode = self.transfer_subtitles(org_name, new_name, rmt_mode)
        if retcode != 0:
            return retcode
        retcode = self.transfer_audio_track_files(org_name, new_name, rmt_mode, over_flag)
        if retcode != 0:
            return retcode
        return 0

    def transfer_subtitles(self, org_name, new_name, rmt_mode):
        """
        根据文件名转移对应字幕文件
        :param org_name: 原文件名
        :param new_name: 新文件名
        :param rmt_mode: RmtMode转移方式
        """
        _zhcn_sub_re = (
            r"([.\[(](((zh[-_])?(cn|ch[si]|sg|sc))|zho?"
            r"|chinese|(cn|ch[si]|sg|zho?|eng)[-_&](cn|ch[si]|sg|zho?|eng)"
            r"|简[体中]?|JPSC)[.\])])"
            r"|([\u4e00-\u9fa5]{0,3}[中双][\u4e00-\u9fa5]{0,2}[字文语][\u4e00-\u9fa5]{0,3})"
            r"|简体|简中"
            r"|(?<![a-z0-9])gb(?![a-z0-9])"
        )
        _zhtw_sub_re = (
            r"([.\[(](((zh[-_])?(hk|tw|cht|tc))"
            r"|繁[体中]?|JPTC)[.\])])"
            r"|繁体中[文字]|中[文字]繁体|繁体"
            r"|(?<![a-z0-9])big5(?![a-z0-9])"
        )
        _eng_sub_re = r"[.\[(]eng[.\])]"

        dir_name = os.path.dirname(org_name)
        file_name = os.path.basename(org_name)
        file_list = PathUtils.get_dir_level1_files(dir_name, RMT_SUBEXT)
        if len(file_list) == 0:
            log.debug(f"【Rmt】{dir_name} 目录下没有找到字幕文件...")
        else:
            log.debug("【Rmt】字幕文件清单：" + str(file_list))
            metainfo = MetaInfo(title=file_name)
            for file_item in file_list:
                sub_file_name = re.sub(
                    _zhtw_sub_re, ".", re.sub(_zhcn_sub_re, ".", os.path.basename(file_item), flags=re.I), flags=re.I
                )
                sub_file_name = re.sub(_eng_sub_re, ".", sub_file_name, flags=re.I)
                sub_metainfo = MetaInfo(title=os.path.basename(file_item))
                if (
                    (os.path.splitext(file_name)[0] == os.path.splitext(sub_file_name)[0])
                    or (sub_metainfo.cn_name and sub_metainfo.cn_name == metainfo.cn_name)
                    or (sub_metainfo.en_name and sub_metainfo.en_name == metainfo.en_name)
                ):
                    if (
                        metainfo.get_season_string()
                        and metainfo.get_season_string() != sub_metainfo.get_season_string()
                    ):
                        continue
                    if (
                        metainfo.get_episode_string()
                        and metainfo.get_episode_string() != sub_metainfo.get_episode_string()
                    ):
                        continue
                    new_file_type = ""
                    if re.search(_zhcn_sub_re, file_item, re.I):
                        new_file_type = ".chi.zh-cn"
                    elif re.search(_zhtw_sub_re, file_item, re.I):
                        new_file_type = ".zh-tw"
                    elif re.search(_eng_sub_re, file_item, re.I):
                        new_file_type = ".eng"
                    file_ext = os.path.splitext(file_item)[-1]
                    if not new_file_type:
                        new_file_type = ".und"
                    new_sub_tag_list = [new_file_type if t == 0 else f"{new_file_type}.{t}" for t in range(6)]
                    for new_sub_tag in new_sub_tag_list:
                        new_file = os.path.splitext(new_name)[0] + new_sub_tag + file_ext
                        try:
                            if not os.path.exists(new_file):
                                log.debug(f"【Rmt】正在处理字幕：{os.path.basename(file_item)}")
                                retcode = self.transfer_command(
                                    file_item=file_item, target_file=new_file, rmt_mode=rmt_mode
                                )
                                if retcode == 0:
                                    log.info(f"【Rmt】字幕 {os.path.basename(file_item)} {rmt_mode.value}完成")
                                    break
                                else:
                                    log.error(
                                        f"【Rmt】字幕 {file_name} {rmt_mode.value}失败，错误码 {str(retcode)}"
                                    )
                                    return retcode
                            elif os.path.getsize(new_file) == os.path.getsize(file_item):
                                log.info(f"【Rmt】字幕 {new_file} 已存在")
                                break
                        except OSError as reason:
                            log.info(f"【Rmt】字幕 {new_file} 出错了,原因: {str(reason)}")
        return 0

    def transfer_audio_track_files(self, org_name, new_name, rmt_mode, over_flag):
        """
        根据文件名转移对应音轨文件
        :param org_name: 原文件名
        :param new_name: 新文件名
        :param rmt_mode: RmtMode转移方式
        :param over_flag: 是否覆盖，为True时会先删除再转移
        """
        dir_name = os.path.dirname(org_name)
        file_name = os.path.basename(org_name)
        file_pre_name = os.path.splitext(file_name)[0]
        file_list = PathUtils.get_dir_level1_files(dir_name, RMT_AUDIO_TRACK_EXT)
        pending_file_list = [file for file in file_list if file_pre_name == os.path.splitext(os.path.basename(file))[0]]
        if len(pending_file_list) == 0:
            log.debug(f"【Rmt】{dir_name} 目录下没有找到匹配的音轨文件...")
        else:
            log.debug("【Rmt】音轨文件清单：" + str(pending_file_list))
            for track_file in pending_file_list:
                track_ext = os.path.splitext(track_file)[1].lower()
                new_track_file = os.path.splitext(new_name)[0] + track_ext
                if os.path.exists(new_track_file):
                    if not over_flag:
                        log.warn(f"【Rmt】音轨文件已存在：{new_track_file}")
                        continue
                    else:
                        log.info(f"【Rmt】正在删除已存在的音轨文件：{new_track_file}")
                        os.remove(new_track_file)
                try:
                    log.info(f"【Rmt】正在转移音轨文件：{track_file} 到 {new_track_file}")
                    retcode = self.transfer_command(file_item=track_file, target_file=new_track_file, rmt_mode=rmt_mode)
                    if retcode == 0:
                        log.info(f"【Rmt】音轨文件 {file_name} {rmt_mode.value}完成")
                    else:
                        log.error(f"【Rmt】音轨文件 {file_name} {rmt_mode.value}失败，错误码 {str(retcode)}")
                except OSError as reason:
                    log.error(f"【Rmt】音轨文件 {file_name} {rmt_mode.value}失败：{str(reason)}")
        return 0

    def transfer_bluray_dir(self, file_path, new_path, rmt_mode):
        """
        转移蓝光文件夹
        :param file_path: 原路径
        :param new_path: 新路径
        :param rmt_mode: RmtMode转移方式
        """
        log.info(f"【Rmt】正在{rmt_mode.value}目录：{file_path} 到 {new_path}")
        retcode = self.transfer_dir_files(src_dir=file_path, target_dir=new_path, rmt_mode=rmt_mode, bludir=True)
        if retcode == 0:
            log.info(f"【Rmt】文件 {file_path} {rmt_mode.value}完成")
        else:
            log.error(f"【Rmt】文件{file_path} {rmt_mode.value}失败，错误码 {str(retcode)}")
        return retcode

    def transfer_dir_files(self, src_dir, target_dir, rmt_mode, bludir=False):
        """
        按目录结构转移所有文件
        :param src_dir: 原路径
        :param target_dir: 新路径
        :param rmt_mode: RmtMode转移方式
        :param bludir: 是否蓝光目录
        """
        file_list = PathUtils.get_dir_files(src_dir)
        retcode = 0
        for file in file_list:
            new_file = file.replace(src_dir, target_dir)
            if os.path.exists(new_file):
                log.warn(f"【Rmt】{new_file} 文件已存在")
                continue
            new_dir = os.path.dirname(new_file)
            if not os.path.exists(new_dir) and rmt_mode not in ModuleConf.REMOTE_RMT_MODES:
                os.makedirs(new_dir)
            retcode = self.transfer_command(file_item=file, target_file=new_file, rmt_mode=rmt_mode)
            if retcode != 0:
                break
            else:
                if not bludir:
                    self._blacklist_repo.insert(file)
        if retcode == 0 and bludir:
            self._blacklist_repo.insert(src_dir)
        return retcode

    def transfer_origin_file(self, file_item, target_dir, rmt_mode):
        """
        按原文件名link文件到目的目录
        :param file_item: 原文件路径
        :param target_dir: 目的目录
        :param rmt_mode: RmtMode转移方式
        """
        if not file_item or not target_dir:
            return -1
        if not os.path.exists(file_item):
            log.warn(f"【Rmt】{file_item} 不存在")
            return -1
        parent_name = os.path.basename(os.path.dirname(file_item))
        target_dir = os.path.join(target_dir, parent_name)
        if not os.path.exists(target_dir) and rmt_mode not in ModuleConf.REMOTE_RMT_MODES:
            log.debug(f"【Rmt】正在创建目录：{target_dir}")
            os.makedirs(target_dir)
        if os.path.isdir(file_item):
            log.info(f"【Rmt】正在{rmt_mode.value}目录：{file_item} 到 {target_dir}")
            retcode = self.transfer_dir_files(src_dir=file_item, target_dir=target_dir, rmt_mode=rmt_mode)
        else:
            target_file = os.path.join(target_dir, os.path.basename(file_item))
            if os.path.exists(target_file):
                log.warn(f"【Rmt】{target_file} 文件已存在")
                return 0
            retcode = self.transfer_command(file_item=file_item, target_file=target_file, rmt_mode=rmt_mode)
            if retcode == 0:
                self._blacklist_repo.insert(file_item)
        if retcode == 0:
            log.info(f"【Rmt】{file_item} {rmt_mode.value}到unknown完成")
        else:
            log.error(f"【Rmt】{file_item} {rmt_mode.value}到unknown失败，错误码 {retcode}")
        return retcode

    def transfer_file(self, file_item, new_file, rmt_mode, over_flag=False, old_file=None):
        """
        转移一个文件，同时处理其他相关文件
        :param file_item: 原文件路径
        :param new_file: 新文件路径
        :param rmt_mode: RmtMode转移方式
        :param over_flag: 是否覆盖，为True时会先删除再转移
        """
        file_name = os.path.basename(file_item)
        if not over_flag and os.path.exists(new_file):
            log.warn(f"【Rmt】文件已存在：{new_file}")
            return 0
        if over_flag and old_file and os.path.isfile(old_file):
            log.info(f"【Rmt】正在删除已存在的文件：{old_file}")
            os.remove(old_file)
        log.info(f"【Rmt】正在转移文件：{file_name} 到 {new_file}")
        retcode = self.transfer_command(file_item=file_item, target_file=new_file, rmt_mode=rmt_mode)
        if retcode == 0:
            log.info(f"【Rmt】文件 {file_name} {rmt_mode.value}完成")
            self._blacklist_repo.insert(file_item)
        else:
            log.error(f"【Rmt】文件 {file_name} {rmt_mode.value}失败，错误码 {str(retcode)}")
            return retcode
        return self.transfer_other_files(org_name=file_item, new_name=new_file, rmt_mode=rmt_mode, over_flag=over_flag)

    @staticmethod
    def delete_media_file(filedir, filename):
        """
        删除媒体文件
        """
        try:
            file = os.path.join(filedir, filename)
            if os.path.exists(file):
                os.remove(file)
                if not os.listdir(filedir):
                    shutil.rmtree(filedir)
                return True, "删除成功"
            else:
                return False, "文件不存在"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False, str(e)
