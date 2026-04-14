import json
import os
import datetime
from abc import ABCMeta, abstractmethod
from typing import Optional, Callable, Any, Dict

import log
from app.conf import SystemConfig
from app.helper import DbHelper
from app.message import Message
from config import Config


class _IPluginModule(metaclass=ABCMeta):
    """
    插件模块基类，通过继续该类实现插件功能
    除内置属性外，还有以下方法可以扩展或调用：
    - get_fields() 获取配置字典，用于生成插件配置表单
    - get_state() 获取插件启用状态，用于展示运行状态
    - stop_service() 停止插件服务
    - get_config() 获取配置信息
    - update_config() 更新配置信息
    - init_config() 生效配置信息
    - info(msg) 记录INFO日志
    - warn(msg) 记录插件WARN日志
    - error(msg) 记录插件ERROR日志
    - debug(msg) 记录插件DEBUG日志
    - get_page() 插件额外页面数据，在插件配置页面左下解按钮展示
    - get_script() 插件额外脚本（Javascript），将会写入插件页面，可在插件元素中绑定使用，，XX_PluginInit为初始化函数
    - send_message() 发送消息
    - get_data_path() 获取插件数据保存目录
    - history() 记录插件运行数据，key需要唯一，value为对象
    - get_history() 获取插件运行数据
    - update_history() 更新插件运行数据
    - delete_history() 删除插件运行数据
    - get_command() 获取插件命令，使用消息机制通过远程控制
    - register_interval() / register_date() / register_cron() 注册定时任务
    - remove_job() 移除定时任务
    - start_job() 启动定时任务

    """
    # 插件名称
    module_name = ""
    # 插件描述
    module_desc = ""
    # 插件图标
    module_icon = ""
    # 主题色
    module_color = ""
    # 插件版本
    module_version = "1.0"
    # 插件作者
    module_author = ""
    # 作者主页
    author_url = ""
    # 插件配置项ID前缀：为了避免各插件配置表单相冲突，配置表单元素ID自动在前面加上此前缀
    module_config_prefix = "plugin_"
    # 显示顺序
    module_order = 0
    # 可使用的用户级别
    auth_level = 1

    _scheduler = None
    _jobstore = 'plugin'
    _job_ids = []

    @staticmethod
    @abstractmethod
    def get_fields():
        """
        获取配置字典，用于生成表单
        """
        pass

    @abstractmethod
    def get_state(self):
        """
        获取插件启用状态
        """
        pass

    @abstractmethod
    def init_config(self, config: dict = None):
        """
        生效配置信息
        :param config: 配置信息字典
        """
        pass

    @abstractmethod
    def stop_service(self):
        """
        停止插件
        """
        pass

    @staticmethod
    def __is_obj(obj):
        if isinstance(obj, list) or isinstance(obj, dict):
            return True
        else:
            return str(obj).startswith("{") or str(obj).startswith("[")

    def update_config(self, config: dict, plugin_id=None):
        """
        更新配置信息
        :param config: 配置信息字典
        :param plugin_id: 插件ID
        """
        if not plugin_id:
            plugin_id = self.__class__.__name__
        return SystemConfig().set("plugin.%s" % plugin_id, config)

    def get_config(self, plugin_id=None):
        """
        获取配置信息
        :param plugin_id: 插件ID
        """
        if not plugin_id:
            plugin_id = self.__class__.__name__
        return SystemConfig().get("plugin.%s" % plugin_id)

    def get_data_path(self, plugin_id=None):
        """
        获取插件数据保存目录
        """
        if not plugin_id:
            plugin_id = self.__class__.__name__
        data_path = os.path.join(Config().get_user_plugin_path(), plugin_id)
        if not os.path.exists(data_path):
            os.makedirs(data_path)
        return data_path

    def history(self, key, value):
        """
        记录插件运行数据，key需要唯一，value为对象是自动转换为str，
        """
        if not key or not value:
            return
        if self.__is_obj(value):
            value = json.dumps(value)
        DbHelper().insert_plugin_history(plugin_id=self.__class__.__name__,
                                         key=key,
                                         value=value)

    def get_history(self, key=None, plugin_id=None):
        """
        获取插件运行数据，只返回一条，自动识别转换为对象
        """
        if not plugin_id:
            plugin_id = self.__class__.__name__

        historys = DbHelper().get_plugin_history(plugin_id=plugin_id, key=key)
        if not isinstance(historys, list):
            historys = [historys]
        result = []
        for history in historys:
            if not history:
                continue
            if self.__is_obj(history.VALUE):
                try:
                    if key:
                        return json.loads(history.VALUE)
                    else:
                        result.append(json.loads(history.VALUE))
                    continue
                except Exception as err:
                    print(str(err))
            if key:
                return history.VALUE
            else:
                result.append(history.VALUE)
        return None if key else result

    def update_history(self, key, value, plugin_id=None):
        """
        更新插件运行数据
        """
        if not key or not value:
            return False
        if not plugin_id:
            plugin_id = self.__class__.__name__
        if self.__is_obj(value):
            value = json.dumps(value)
        return DbHelper().update_plugin_history(plugin_id=plugin_id, key=key, value=value)

    def delete_history(self, key, plugin_id=None):
        """
        删除插件运行数据
        """
        if not key:
            return False
        if not plugin_id:
            plugin_id = self.__class__.__name__
        return DbHelper().delete_plugin_history(plugin_id=plugin_id, key=key)

    @staticmethod
    def send_message(title, text=None, image=None, url=""):
        """
        发送消息
        """
        return Message().send_plugin_message(title=title,
                                             text=text,
                                             url=url,
                                             image=image)

    def info(self, msg):
        """
        记录INFO日志
        :param msg: 日志信息
        """
        log.info(f"【Plugin】{self.module_name} - {msg}")

    def warn(self, msg):
        """
        记录插件WARN日志
        :param msg: 日志信息
        """
        log.warn(f"【Plugin】{self.module_name} - {msg}")

    def error(self, msg):
        """
        记录插件ERROR日志
        :param msg: 日志信息
        """
        log.error(f"【Plugin】{self.module_name} - {msg}")

    def debug(self, msg):
        """
        记录插件Debug日志
        :param msg: 日志信息
        """
        log.debug(f"【Plugin】{self.module_name} - {msg}")

    def _get_scheduler(self):
        """
        获取调度器服务实例（懒加载）
        """
        if self._scheduler is None:
            from app.scheduler_service import SchedulerService
            self._scheduler = SchedulerService()
        return self._scheduler

    def start_job(self, task: dict):
        """
        启动单个定时任务（兼容旧版字典方式）
        :param task: 任务配置字典
        """
        scheduler = self._get_scheduler()
        self._job_ids.append(task.get("job_id"))
        return scheduler.start_job(task)

    def start_schedule_job(self, job_id: str, func: Callable, func_desc: str, cron: str,
                           next_run_time: Optional[Any] = None):
        """
        启动带 cron/时间范围/固定时间解析的定时任务（封装 SchedulerUtils.start_job）
        :param job_id: 任务ID
        :param func: 执行函数
        :param func_desc: 功能描述
        :param cron: cron表达式/时间范围/固定时间/间隔小时数
        :param next_run_time: 下次运行时间
        """
        from app.utils import SchedulerUtils
        scheduler = self._get_scheduler()
        self._job_ids.append(job_id)
        return SchedulerUtils.start_job(
            scheduler=scheduler.SCHEDULER,
            func=func,
            job_id=job_id,
            func_desc=func_desc,
            cron=cron,
            next_run_time=next_run_time
        )

    def register_interval(
        self,
        job_id: str,
        func: Callable,
        seconds: Optional[int] = None,
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        next_run_time: Optional[Any] = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True
    ):
        """
        注册 interval 类型定时任务
        """
        scheduler = self._get_scheduler()
        self._job_ids.append(job_id)
        return scheduler.register_interval(
            job_id=job_id,
            func=func,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            args=args,
            kwargs=kwargs,
            jobstore=self._jobstore,
            next_run_time=next_run_time,
            max_instances=max_instances,
            misfire_grace_time=misfire_grace_time,
            coalesce=coalesce
        )

    def register_date(
        self,
        job_id: str,
        func: Callable,
        run_date: datetime.datetime,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        max_instances: int = 1,
        misfire_grace_time: int = 60,
        coalesce: bool = True
    ):
        """
        注册 date 类型一次性定时任务
        """
        scheduler = self._get_scheduler()
        self._job_ids.append(job_id)
        return scheduler.register_date(
            job_id=job_id,
            func=func,
            run_date=run_date,
            args=args,
            kwargs=kwargs,
            jobstore=self._jobstore,
            max_instances=max_instances,
            misfire_grace_time=misfire_grace_time,
            coalesce=coalesce
        )

    def register_cron(
        self,
        job_id: str,
        func: Callable,
        cron: str,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        next_run_time: Optional[Any] = None,
        max_instances: int = 1,
        misfire_grace_time: int = 300,
        coalesce: bool = True
    ):
        """
        注册 cron 类型定时任务
        """
        scheduler = self._get_scheduler()
        self._job_ids.append(job_id)
        return scheduler.register_cron(
            job_id=job_id,
            func=func,
            cron=cron,
            args=args,
            kwargs=kwargs,
            jobstore=self._jobstore,
            next_run_time=next_run_time,
            max_instances=max_instances,
            misfire_grace_time=misfire_grace_time,
            coalesce=coalesce
        )

    def remove_job(self, job_id: str):
        """
        移除单个定时任务
        :param job_id: 任务ID
        """
        scheduler = self._get_scheduler()
        return scheduler.remove_job(job_id=job_id, jobstore=self._jobstore)

    def remove_all_jobs(self):
        """
        移除本插件所有定时任务
        """
        for job_id in list(self._job_ids):
            self.remove_job(job_id)
        self._job_ids.clear()

    def get_jobs(self):
        """
        获取本插件所有定时任务
        """
        jobs = []
        for job_id in self._job_ids:
            job = self.get_job(job_id)
            if job:
                jobs.append(job)
        return jobs

    def get_job(self, job_id: str):
        """
        获取单个定时任务
        :param job_id: 任务ID
        """
        scheduler = self._get_scheduler()
        return scheduler.get_job(job_id=job_id, jobstore=self._jobstore)
