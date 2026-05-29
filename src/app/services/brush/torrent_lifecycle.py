"""Brush torrent lifecycle - 删种与停种逻辑."""

import time
from typing import Any

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.domain.engine.brush_rule_engine import BrushRuleEngine
from app.message import Message
from app.schemas.download import TorrentStatus
from app.sites import Sites
from app.utils import ExceptionUtils, StringUtils


class BrushTorrentLifecycle:
    """
    刷流种子生命周期管理器
    职责：删种、停种规则执行与消息通知。
    """

    def __init__(self, helper, repo, downloader, sites: Sites | None = None, message=None):
        self._helper = helper
        self._repo: Any = repo
        self._downloader: Any = downloader
        self._sites = sites or Sites()
        self._message: Message = message or Message()

    def remove_task_torrents(self, taskid: int | None, taskinfo: dict) -> None:
        try:
            total_uploaded = 0
            total_downloaded = 0
            delete_ids = []
            update_torrents = []
            remove_torrent_ids = set()

            site_id = taskinfo.get("site_id")
            task_name = taskinfo.get("name")
            downloader_id = taskinfo.get("downloader")
            remove_rule = taskinfo.get("remove_rule")
            taskinfo.get("sendmessage")
            taskinfo.get("savepath")
            downloader_cfg = self._downloader.get_downloader_conf(downloader_id)
            site_info = self._sites.get_sites(siteid=site_id)

            if not downloader_cfg:
                log.warn(f"【Brush】任务 {task_name} 下载器不存在")
                return

            task_torrents = self._repo.get_brushtask_torrents(taskid)
            torrent_id_maps = {item.DOWNLOAD_ID: item.ENCLOSURE for item in task_torrents if item.DOWNLOAD_ID}
            torrent_ids = list(torrent_id_maps.keys())
            if not torrent_ids:
                return

            completed_torrents = self._downloader.get_completed_torrents(downloader_id, torrent_ids)
            if completed_torrents is None:
                log.warn(f"【Brush】任务 {task_name} 获取下载完成种子失败")
                return
            remove_torrent_ids = set(torrent_ids) - {torrent.id for torrent in completed_torrents}
            total_uploaded, total_downloaded, delete_ids, update_torrents = self._process_torrents(
                completed_torrents,
                taskinfo,
                downloader_cfg,
                site_info,
                remove_rule,
                total_uploaded,
                total_downloaded,
                delete_ids,
                update_torrents,
                torrent_id_maps,
            )

            downloading_torrents = self._downloader.get_downloading_torrents(downloader_id, torrent_ids)
            if downloading_torrents is None:
                log.warn(f"【Brush】任务 {task_name} 获取下载中种子失败")
                return
            remove_torrent_ids -= {torrent.id for torrent in downloading_torrents}
            total_uploaded, total_downloaded, delete_ids, update_torrents = self._process_torrents(
                downloading_torrents,
                taskinfo,
                downloader_cfg,
                site_info,
                remove_rule,
                total_uploaded,
                total_downloaded,
                delete_ids,
                update_torrents,
                torrent_id_maps,
                is_downloading=True,
            )

            if remove_torrent_ids:
                log.info(f"【Brush】任务 {task_name} 删除不存在的下载任务：{remove_torrent_ids}")
                for rid in remove_torrent_ids:
                    self._repo.delete_brushtask_torrent(taskid or 0, rid)

            if delete_ids:
                self._downloader.delete_torrents(downloader_id, delete_ids, delete_file=True)
                time.sleep(5)
                torrents = self._downloader.get_torrents(downloader_id, delete_ids)
                if torrents is None:
                    delete_ids = []
                    update_torrents = []
                else:
                    for torrent in torrents:
                        if torrent.id in delete_ids:
                            delete_ids.remove(torrent.id)

                if delete_ids:
                    self._repo.update_brushtask_torrent_state(update_torrents)
                    log.info(f"【Brush】任务 {task_name} 共删除 {len(delete_ids)} 个刷流下载任务")
                else:
                    log.info(f"【Brush】任务 {task_name} 本次检查未删除下载任务")

            self._repo.add_brushtask_upload_count(
                taskid or 0, total_uploaded, total_downloaded, len(delete_ids) + len(remove_torrent_ids)
            )
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def _process_torrents(
        self,
        torrents,
        taskinfo,
        downloader_cfg,
        site_info,
        remove_rule,
        total_uploaded,
        total_downloaded,
        delete_ids,
        update_torrents,
        torrent_id_maps,
        is_downloading=False,
    ):
        task_name = taskinfo.get("name")
        sendmessage = taskinfo.get("sendmessage")
        downloader_id = taskinfo.get("downloader")
        download_dir = taskinfo.get("savepath")

        for torrent in torrents:
            torrent_id = torrent.id
            total_uploaded += torrent.uploaded
            total_downloaded += torrent.downloaded

            enclosure = torrent_id_maps.get(torrent_id)
            torrent_url, torrent_attr = (None, {})
            if enclosure:
                torrent_url, torrent_attr = self._helper.get_torrent_attr(
                    site_info if isinstance(site_info, dict) else {}, enclosure
                )

            torrent_params = {
                "seeding_time": torrent.seeding_time,
                "ratio": round(torrent.ratio or 0, 2),
                "uploaded": torrent.uploaded,
                "iatime": torrent.iatime,
                "avg_upspeed": torrent.avg_upload_speed,
                "freespace": self._downloader.get_free_space(downloader_id, download_dir),
                "torrent_attr": torrent_attr,
            }
            if is_downloading:
                torrent_params.update(
                    {
                        "dltime": torrent.download_time,
                        "pending_time": torrent.iatime if torrent.status == TorrentStatus.Pending else None,
                    }
                )

            need_delete, delete_type = BrushRuleEngine.check_remove_rule(remove_rule, torrent_params)
            if need_delete:
                delete_type_str = (
                    ",".join([d.value for d in delete_type]) if isinstance(delete_type, list) else delete_type.value
                )
                log.info(f"【Brush】{torrent.name} 达到删种条件：{delete_type_str}，删除任务...")
                if sendmessage:
                    self._send_remove_message(task_name, delete_type_str, torrent, downloader_cfg, torrent_params)
                if torrent_id not in delete_ids:
                    delete_ids.append(torrent_id)
                    update_torrents.append((f"{torrent.uploaded},{torrent.downloaded}", taskinfo.get("id"), torrent_id))

        return total_uploaded, total_downloaded, delete_ids, update_torrents

    def _send_remove_message(self, task_name, delete_type, torrent, downloader_cfg, torrent_params):
        _msg_title = f"【刷流任务 {task_name} 删除做种】"
        _msg_text = (
            f"下载器名：{downloader_cfg.get('name')}\n"
            f"种子名称：{torrent.name}\n"
            f"种子大小：{StringUtils.str_filesize(torrent.size)}\n"
            f"已下载量：{StringUtils.str_filesize(torrent.downloaded)}\n"
            f"已上传量：{StringUtils.str_filesize(torrent.uploaded)}\n"
            f"分享比率：{torrent_params['ratio']}\n"
            f"添加时间：{torrent.add_time}\n"
            f"删除时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n"
            f"删除规则：{delete_type}"
        )
        self._message.send_brushtask_remove_message(title=_msg_title, text=_msg_text)

    def stop_task_torrents(self, taskid: int | None, taskinfo: dict) -> None:
        task_name = taskinfo.get("name")
        stop_rule = taskinfo.get("stop_rule")
        downloader_id = taskinfo.get("downloader")
        sendmessage = taskinfo.get("sendmessage")
        site_id = taskinfo.get("site_id")

        site_info = self._sites.get_sites(siteid=site_id)
        if not site_info:
            log.error(f"【Brush】刷流任务 {task_name} 的站点已不存在，无法刷流！")
            return

        log.info(f"【Brush】开始非免费种子暂停任务：{task_name}...")
        task_torrents = self._repo.get_brushtask_torrents(taskid)
        torrent_id_maps = {item.DOWNLOAD_ID: item.ENCLOSURE for item in task_torrents if item.DOWNLOAD_ID}
        torrent_ids = list(torrent_id_maps.keys())
        if not torrent_id_maps:
            return

        downloader_cfg = self._downloader.get_downloader_conf(downloader_id)
        if not downloader_cfg:
            log.warn(f"【Brush】任务 {task_name} 下载器不存在")
            return

        downlaod_name = downloader_cfg.get("name")
        torrents = self._downloader.get_downloading_torrents(downloader_id=downloader_id, ids=torrent_ids)
        if torrents is None:
            log.warn(f"【Brush】任务 {task_name} 获取正在下载种子失败")
            return

        stopfree_enabled = stop_rule and stop_rule.get("stopfree") == "Y"
        for torrent in torrents:
            torrent_id = torrent.id
            torrent_name = torrent.name
            add_time = torrent.add_time
            enclosure = torrent_id_maps.get(torrent_id)
            if not enclosure:
                continue
            torrent_attr = {}
            if stopfree_enabled:
                torrent_url, torrent_attr = self._helper.get_torrent_attr(
                    site_info if isinstance(site_info, dict) else {}, enclosure
                )
                log.debug(f"【Brush】{torrent_url} 解析详情 {torrent_attr}")

            need_stop, stop_type = BrushRuleEngine.check_stop_rule(stop_rule, params=torrent_attr)
            if need_stop:
                if isinstance(stop_type, list):
                    stop_type_str = ", ".join(t.value for t in stop_type)
                else:
                    stop_type_str = stop_type.value
                log.info(f"【Brush】{torrent_name} 触发停种条件：{stop_type_str}，暂停任务...")
                self._downloader.stop_torrents(downloader_id, [torrent_id])
                if sendmessage:
                    self._send_stop_message(task_name, torrent_name, downlaod_name, add_time)

    def _send_stop_message(self, task_name, torrent_name, download_name, add_time):
        _msg_title = f"【刷流任务 {task_name} 暂停做种】"
        _msg_text = (
            f"下载器名：{download_name}\n"
            f"种子名称：{torrent_name}\n"
            f"添加时间：{add_time}\n"
            f"暂停时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n"
            "暂停原因: free 时间到期"
        )
        self._message.send_brushtask_pause_message(title=_msg_title, text=_msg_text)
