"""
Plugin Context - 插件运行时上下文
提供给插件访问系统能力的接口
"""

import contextlib
import json
import os
from typing import Any

import log
from app.db.repositories.plugin_framework_repo_adapter import PluginConfigRepositoryAdapter, PluginLogRepositoryAdapter
from app.domain.entities.plugin import PluginConfigEntity
from app.message import Message
from app.plugin_framework.hook_system import HookSystem
from app.services.scheduler_core import SchedulerCore
from app.core.settings import settings


class PluginContext:
    """插件上下文，每个插件实例拥有独立的上下文"""

    def __init__(self, plugin_id: str, plugin_name: str = ""):
        self._plugin_id = plugin_id
        self._plugin_name = plugin_name or plugin_id
        self._data_dir = os.path.join(settings.config_path, "plugins_data", plugin_id)
        if not os.path.exists(self._data_dir):
            os.makedirs(self._data_dir)
        self._config_repo = PluginConfigRepositoryAdapter()
        self._log_repo = PluginLogRepositoryAdapter()

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def data_dir(self) -> str:
        return self._data_dir

    def get_config(self, key: str | None = None, default: Any = None) -> Any:
        """获取配置"""
        entity = self._config_repo.get(self._plugin_id)
        if not entity:
            return default if key else {}

        try:
            config = entity.config if isinstance(entity.config, dict) else json.loads(entity.config or "{}")
        except Exception:
            return default if key else {}

        if key is None:
            return config
        return config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """设置配置项"""
        config = self.get_config() or {}
        config[key] = value
        self.set_all_config(config)

    def set_all_config(self, config: dict) -> None:
        """设置全部配置"""
        entity = PluginConfigEntity(plugin_id=self._plugin_id, config=config)
        self._config_repo.save(entity)

    def read_data(self, filename: str) -> str | None:
        """读取插件数据文件"""
        filepath = os.path.join(self._data_dir, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, encoding="utf-8") as f:
            return f.read()

    def write_data(self, filename: str, content: str) -> None:
        """写入插件数据文件"""
        filepath = os.path.join(self._data_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_db_log(self, level: str, msg: str) -> None:
        """同时写入数据库日志"""
        with contextlib.suppress(Exception):
            self._log_repo.insert(self._plugin_id, level, msg)

    def log_info(self, msg: str) -> None:
        log.info(f"[Plugin:{self._plugin_id}] {msg}")
        self._write_db_log("info", msg)

    info = log_info

    def log_warn(self, msg: str) -> None:
        log.warn(f"[Plugin:{self._plugin_id}] {msg}")
        self._write_db_log("warn", msg)

    warn = log_warn

    def log_error(self, msg: str) -> None:
        log.error(f"[Plugin:{self._plugin_id}] {msg}")
        self._write_db_log("error", msg)

    error = log_error

    def log_debug(self, msg: str) -> None:
        log.debug(f"[Plugin:{self._plugin_id}] {msg}")
        self._write_db_log("debug", msg)

    debug = log_debug

    def notify(self, title: str, text: str | None = None, image: str | None = None) -> None:
        """发送消息通知"""
        Message().send_plugin_message(title=title, text=text, image=image)

    def schedule_cron(self, job_id: str, func, cron: str, **kwargs) -> bool:
        """注册 cron 定时任务，返回是否成功"""
        job = SchedulerCore().register_smart_cron(
            job_id=f"plugin_{self._plugin_id}_{job_id}",
            func=func,
            name=self._plugin_name,
            cron=cron,
            jobstore="plugin",
            **kwargs,
        )
        if job:
            self.info(f"定时任务已注册: {job_id} (cron={cron})")
            return True
        self.error(f"定时任务注册失败: {job_id} (cron={cron})")
        return False

    def schedule_interval(self, job_id: str, func, **kwargs) -> bool:
        """注册 interval 定时任务，返回是否成功"""
        job = SchedulerCore().register_interval(
            job_id=f"plugin_{self._plugin_id}_{job_id}", func=func, name=self._plugin_name, jobstore="plugin", **kwargs
        )
        if job:
            self.info(f"interval 任务已注册: {job_id}")
            return True
        self.error(f"interval 任务注册失败: {job_id}")
        return False

    def schedule_date(self, job_id: str, func, run_date) -> bool:
        """注册一次性日期任务，返回是否成功"""
        job = SchedulerCore().register_date(
            job_id=f"plugin_{self._plugin_id}_{job_id}",
            func=func,
            run_date=run_date,
            name=self._plugin_name,
            jobstore="plugin",
        )
        if job:
            self.info(f"date 任务已注册: {job_id} (run_date={run_date})")
            return True
        self.error(f"date 任务注册失败: {job_id}")
        return False

    def remove_schedule(self, job_id: str) -> None:
        """移除定时任务"""
        SchedulerCore().remove_job(job_id=f"plugin_{self._plugin_id}_{job_id}", jobstore="plugin")

    def get_schedules(self):
        """获取当前插件的所有定时任务"""
        sched = SchedulerCore()
        if not sched:
            return []
        prefix = f"plugin_{self._plugin_id}_"
        return [j for j in sched.get_jobs(jobstore="plugin") if j.id.startswith(prefix)]

    def emit(self, event: str, data: dict | None = None) -> None:
        """触发全局事件"""

        HookSystem().emit(event, data or {})

    # ---------- 消息命令注册（委托给 Message） ----------

    def register_message_command(self, cmd: str, desc: str, func) -> None:
        """注册消息命令，用户发送该命令时触发 func"""
        Message().register_command(cmd=cmd, desc=desc, func=func, plugin_id=self._plugin_id)

    def unregister_message_command(self, cmd: str) -> None:
        """注销消息命令"""
        Message().unregister_command(cmd)

    def unregister_all_message_commands(self) -> None:
        """注销该插件的所有消息命令"""
        Message().clear_plugin_commands(self._plugin_id)
