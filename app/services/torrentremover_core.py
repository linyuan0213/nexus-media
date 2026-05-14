"""
TorrentRemover 重构核心
拆分为 Repository + ActionEngine + Service，移除 SingletonMeta。
"""

import json

import log
from app.core.module_config import ModuleConf
from app.db.repositories.config_repo_adapter import TorrentRemoveTaskRepositoryAdapter
from app.message import Message
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.scheduler_core import SchedulerCore
from app.utils import ExceptionUtils


class TorrentRemoverRepository:
    """删种任务数据仓库"""

    def __init__(self, config_repo=None):
        self._config_repo = config_repo or TorrentRemoveTaskRepositoryAdapter()

    def get_tasks(self):
        return self._config_repo.get_torrent_remove_tasks()

    def delete_task(self, tid):
        self._config_repo.delete_torrent_remove_task(tid=tid)

    def insert_task(self, **kwargs):
        self._config_repo.insert_torrent_remove_task(**kwargs)


class TorrentRemoverActionEngine:
    """删种动作执行引擎：暂停 / 删除种子 / 删除种子及文件"""

    @staticmethod
    def execute(task: dict, downloader) -> tuple[int, str]:
        """
        执行单个删种任务
        :return: (处理数量, 处理文本)
        """
        downloader_id = task.get("downloader")
        task.get("config")["samedata"] = task.get("samedata")
        task.get("config")["onlynastool"] = task.get("onlynastool")
        torrents = downloader.get_remove_torrents(downloader_id=downloader_id, config=task.get("config"))
        log.info(f"【TorrentRemover】自动删种任务：{task.get('name')} 获取符合处理条件种子数 {len(torrents)}")

        action = task.get("action")
        text_items = []
        for torrent in torrents:
            name = torrent.get("name")
            site = torrent.get("site")
            size = round(torrent.get("size") / 1021 / 1024 / 1024, 3)
            text_item = f"{name} 来自站点：{site} 大小：{size} GB"
            text_items.append(text_item)

        if action == 1:
            for torrent in torrents:
                log.info(f"【TorrentRemover】暂停种子：{torrent.get('name')}")
                downloader.stop_torrents(downloader_id=downloader_id, ids=[torrent.get("id")])
            return len(torrents), "共暂停%s个种子\n" % len(torrents) + "\n".join(text_items)
        elif action == 2:
            for torrent in torrents:
                log.info(f"【TorrentRemover】删除种子：{torrent.get('name')}")
                downloader.delete_torrents(downloader_id=downloader_id, delete_file=False, ids=[torrent.get("id")])
            return len(torrents), "共删除%s个种子\n" % len(torrents) + "\n".join(text_items)
        elif action == 3:
            for torrent in torrents:
                log.info(f"【TorrentRemover】删除种子及文件：{torrent.get('name')}")
                downloader.delete_torrents(downloader_id=downloader_id, delete_file=True, ids=[torrent.get("id")])
            return len(torrents), "共删除%s个种子（及文件）\n" % len(torrents) + "\n".join(text_items)
        return len(torrents), ""


class TorrentRemoverService:
    """删种业务服务（替代原 TorrentRemover）"""

    _jobstore = "torrent_remove"

    def __init__(
        self,
        repository: TorrentRemoverRepository | None = None,
        downloader=None,
        message: Message | None = None,
        scheduler=None,
    ):
        self._repo = repository or TorrentRemoverRepository()
        self._downloader = downloader or Downloader()
        self._message = message or Message()
        self._scheduler = scheduler or SchedulerCore()
        self._tasks: dict[str, dict] = {}

    def init_config(self):
        """兼容接口：重新加载任务并启动调度任务"""
        self._load_tasks()
        self._start_scheduler_jobs()

    # ---------- 内部任务加载与调度 ----------

    def _load_tasks(self) -> None:
        self._tasks = {}
        for task in self._repo.get_tasks():
            config = task.CONFIG
            downloader_id = task.DOWNLOADER
            download_conf = self._downloader.get_downloader_conf(str(downloader_id))
            if download_conf:
                downloader_name = download_conf.get("name", "")
                downloader_type = download_conf.get("type", "")
            else:
                downloader_name = ""
                downloader_type = ""
                downloader_id = ""
            self._tasks[str(task.ID)] = {
                "id": task.ID,
                "name": task.NAME,
                "downloader": downloader_id,
                "downloader_name": downloader_name,
                "downloader_type": downloader_type,
                "onlynastool": task.ONLYNASTOOL,
                "samedata": task.SAMEDATA,
                "action": task.ACTION,
                "config": json.loads(config) if config else {},
                "interval": task.INTERVAL,
                "enabled": task.ENABLED,
            }

    def _start_scheduler_jobs(self) -> None:
        self.stop_service()
        if not self._tasks:
            return
        remove_flag = False
        for task in self._tasks.values():
            if task.get("enabled") and task.get("interval") and task.get("config"):
                remove_flag = True
                job_id = f"TorrentRemover.auto_remove_torrents_{task.get('id')}"
                self._scheduler.start_job(
                    {
                        "func": self.auto_remove_torrents,
                        "name": f"自动删种任务 {task.get('name')}",
                        "args": (task.get("id"),),
                        "job_id": job_id,
                        "trigger": "interval",
                        "seconds": int(task.get("interval")) * 60,
                        "jobstore": self._jobstore,
                    }
                )
        if remove_flag:
            log.info("自动删种服务启动")

    # ---------- 公共 API ----------

    def get_torrent_remove_tasks(self, taskid=None):
        if taskid:
            task = self._tasks.get(str(taskid))
            return task if task else {}
        return self._tasks

    def auto_remove_torrents(self, taskids=None):
        tasks = []
        if not taskids:
            for task in self._tasks.values():
                if task.get("enabled") and task.get("interval") and task.get("config"):
                    tasks.append(task)
        elif isinstance(taskids, list):
            for tid in taskids:
                task = self._tasks.get(str(tid))
                if task:
                    tasks.append(task)
        else:
            task = self._tasks.get(str(taskids))
            tasks = [task] if task else []
        if not tasks:
            return
        for task in tasks:
            try:
                count, text = TorrentRemoverActionEngine.execute(task, self._downloader)
                if count and text:
                    self._message.send_auto_remove_torrents_message(
                        title=f"自动删种任务：{task.get('name')}", text=text
                    )
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【TorrentRemover】自动删种任务：{task.get('name')}异常：{str(e)}")

    def _validate_task_params(self, data: dict) -> tuple[bool, str]:
        name = data.get("name")
        if not name:
            return False, "名称参数不合法"
        action = data.get("action")
        if not str(action).isdigit() or int(action) not in [1, 2, 3]:
            return False, "动作参数不合法"
        interval = data.get("interval")
        if not str(interval).isdigit():
            return False, "运行间隔参数不合法"
        enabled = data.get("enabled")
        if not str(enabled).isdigit() or int(enabled) not in [0, 1]:
            return False, "状态参数不合法"
        samedata = data.get("samedata")
        if not str(samedata).isdigit() or int(samedata) not in [0, 1]:
            return False, "处理辅种参数不合法"
        onlynastool = data.get("onlynastool")
        if not str(onlynastool).isdigit() or int(onlynastool) not in [0, 1]:
            return False, "仅处理NASTOOL添加种子参数不合法"
        ratio = data.get("ratio") or 0
        if not str(ratio).replace(".", "").isdigit():
            return False, "分享率参数不合法"
        seeding_time = data.get("seeding_time") or 0
        if not str(seeding_time).isdigit():
            return False, "做种时间参数不合法"
        upload_avs = data.get("upload_avs") or 0
        if not str(upload_avs).isdigit():
            return False, "平均上传速度参数不合法"
        size = data.get("size")
        size = str(size).split("-") if size else []
        if size and (len(size) != 2 or not str(size[0]).isdigit() or not str(size[-1]).isdigit()):
            return False, "种子大小参数不合法"
        return True, ""

    def update_torrent_remove_task(self, data: dict) -> tuple[bool, str]:
        ok, msg = self._validate_task_params(data)
        if not ok:
            return False, msg

        tid = data.get("tid")
        name = data.get("name")
        action = int(data.get("action"))
        interval = int(data.get("interval"))
        enabled = int(data.get("enabled"))
        samedata = int(data.get("samedata"))
        onlynastool = int(data.get("onlynastool"))
        ratio = round(float(data.get("ratio") or 0), 2)
        seeding_time = int(data.get("seeding_time") or 0)
        upload_avs = int(data.get("upload_avs") or 0)
        size = str(data.get("size")).split("-") if data.get("size") else []
        size = [int(size[0]), int(size[-1])] if size else []
        tags = data.get("tags")
        tags = [tag for tag in str(tags).split(";") if tag] if tags else []
        savepath_key = data.get("savepath_key")
        tracker_key = data.get("tracker_key")
        downloader_id = data.get("downloader")
        downloader_type = self._downloader.get_downloader_conf(str(downloader_id)).get("type")

        qb_state = []
        qb_category = []
        tr_state = []
        tr_error_key = ""
        if downloader_type == "qbittorrent":
            qb_state = [s for s in str(data.get("qb_state", "")).split(";") if s]
            if qb_state:
                valid_states = ModuleConf.TORRENTREMOVER_DICT.get(downloader_type, {}).get("torrent_state", {}).keys()
                for item in qb_state:
                    if item not in valid_states:
                        return False, "种子状态参数不合法"
            qb_category = [c for c in str(data.get("qb_category", "")).split(";") if c]
        elif downloader_type == "transmission":
            tr_state = [s for s in str(data.get("tr_state", "")).split(";") if s]
            if tr_state:
                valid_states = ModuleConf.TORRENTREMOVER_DICT.get(downloader_type, {}).get("torrent_state", {}).keys()
                for item in tr_state:
                    if item not in valid_states:
                        return False, "种子状态参数不合法"
            tr_error_key = data.get("tr_error_key", "")

        config = {
            "ratio": ratio,
            "seeding_time": seeding_time,
            "upload_avs": upload_avs,
            "size": size,
            "tags": tags,
            "savepath_key": savepath_key,
            "tracker_key": tracker_key,
            "qb_state": qb_state,
            "qb_category": qb_category,
            "tr_state": tr_state,
            "tr_error_key": tr_error_key,
        }
        if tid:
            self._repo.delete_task(tid=tid)
        self._repo.insert_task(
            name=name,
            action=action,
            interval=interval,
            enabled=enabled,
            samedata=samedata,
            onlynastool=onlynastool,
            downloader=downloader_id,
            config=config,
        )
        self._load_tasks()
        self._start_scheduler_jobs()
        return True, "更新成功"

    def delete_torrent_remove_task(self, taskid=None) -> bool:
        if not taskid:
            return False
        self._repo.delete_task(tid=taskid)
        self._load_tasks()
        self._start_scheduler_jobs()
        return True

    def get_remove_torrents(self, taskid):
        task = self._tasks.get(str(taskid))
        if not task:
            return False, []
        task.get("config")["samedata"] = task.get("samedata")
        task.get("config")["onlynastool"] = task.get("onlynastool")
        torrents = self._downloader.get_remove_torrents(downloader_id=task.get("downloader"), config=task.get("config"))
        return True, torrents

    def stop_service(self):
        try:
            self._scheduler.remove_all_jobs(jobstore=self._jobstore)
        except Exception as e:
            log.error(f"【TorrentRemover】停止服务异常: {str(e)}")
