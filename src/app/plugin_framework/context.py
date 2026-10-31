"""
Plugin Context - 插件运行时上下文
提供给插件访问系统能力的接口
"""

import contextlib
import json
import os
from collections.abc import Callable
from typing import Any

import log
from app.core.settings import settings
from app.db.repositories.plugin_framework_repo_adapter import PluginConfigRepositoryAdapter, PluginLogRepositoryAdapter
from app.domain.entities.plugin import PluginConfigEntity
from app.media.category_contributions import (
    register_category_contribution,
    unregister_category_contribution,
    unregister_plugin_contributions,
)
from app.media.display_image_policy import (
    register_display_image_transformer,
    unregister_display_image_transformer,
)
from app.media.message_image_policy import (
    register_message_image_transformer,
    unregister_message_image_transformer,
)
from app.media.metadata.registry import registry as metadata_registry
from app.media.scraper.processor_registry import scraper_processor_registry
from app.plugin_framework import api_registry
from app.utils.json_utils import JsonUtils


class PluginContext:
    """插件上下文，每个插件实例拥有独立的上下文"""

    def __init__(
        self,
        plugin_id: str,
        plugin_name: str = "",
        plugin_log_repo: Any = None,
        message: Any = None,
        scheduler_core: Any = None,
        hook_system: Any = None,
        site_engine: Any = None,
        media_service: Any = None,
        metadata_service: Any = None,
        manifest_metadata: Any = None,
        filter_service: Any = None,
        discovery_service: Any = None,
    ):
        self._plugin_id = plugin_id
        self._plugin_name = plugin_name or plugin_id
        self._data_dir = os.path.join(settings.data_path, "plugins_data", plugin_id)
        if not os.path.exists(self._data_dir):
            os.makedirs(self._data_dir)
        self._config_repo = PluginConfigRepositoryAdapter()
        self._log_repo = plugin_log_repo or PluginLogRepositoryAdapter()
        self._message = message
        self._scheduler = scheduler_core
        self._hook_system = hook_system
        self._site_engine = site_engine
        self._media_service = media_service
        self._metadata_service = metadata_service
        self._metadata_manifest = manifest_metadata
        self._filter_service = filter_service
        self._discovery_service = discovery_service
        self._metadata_cleanups: list[Callable[[], None]] = []
        self._scraper_processors: list[str] = []
        self._category_contributions: list[str] = []
        self._metadata_visibility = (
            getattr(manifest_metadata, "visibility", "public") if manifest_metadata else "public"
        )

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
            config = entity.config if isinstance(entity.config, dict) else JsonUtils.loads(entity.config or "{}")
        except (json.JSONDecodeError, TypeError):
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

    def get_plugin_config(self, plugin_id: str, key: str | None = None, default: Any = None) -> Any:
        """读取其他插件的配置"""
        entity = self._config_repo.get(plugin_id)
        if not entity:
            return default if key else {}
        try:
            config = entity.config if isinstance(entity.config, dict) else JsonUtils.loads(entity.config or "{}")
        except (json.JSONDecodeError, TypeError):
            return default if key else {}
        if key is None:
            return config
        return config.get(key, default)

    def set_plugin_config(self, plugin_id: str, config: dict) -> None:
        """写入其他插件的全部配置，并通知其重载"""
        entity = PluginConfigEntity(plugin_id=plugin_id, config=config)
        self._config_repo.save(entity)
        self.emit("plugin.config_changed", {"plugin_id": plugin_id})

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

    def read_plugin_data(self, plugin_id: str, filename: str) -> str | None:
        """读取其他插件的持久化数据（读文件，同 data 目录布局）"""
        filepath = os.path.join(settings.data_path, "plugins_data", plugin_id, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, encoding="utf-8") as f:
            return f.read()

    def _write_db_log(self, level: str, msg: str) -> None:
        """同时写入数据库日志"""
        with contextlib.suppress(Exception):
            self._log_repo.insert(self._plugin_id, level, msg)

    def log_info(self, msg: str) -> None:
        log.info(f"[{self._plugin_id}] {msg}")
        self._write_db_log("info", msg)

    info = log_info

    def log_warn(self, msg: str) -> None:
        log.warn(f"[{self._plugin_id}] {msg}")
        self._write_db_log("warn", msg)

    warn = log_warn

    def log_error(self, msg: str) -> None:
        log.error(f"[{self._plugin_id}] {msg}")
        self._write_db_log("error", msg)

    error = log_error

    def log_debug(self, msg: str) -> None:
        log.debug(f"[{self._plugin_id}] {msg}")
        self._write_db_log("debug", msg)

    debug = log_debug

    def notify(self, title: str, text: str | None = None, image: str | None = None) -> None:
        """发送消息通知"""
        self._message.send_plugin_message(title=title, text=text, image=image)

    def schedule_cron(self, job_id: str, func, cron: str, **kwargs) -> bool:
        """注册 cron 定时任务，返回是否成功"""
        job = self._scheduler.register_smart_cron(
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
        job = self._scheduler.register_interval(
            job_id=f"plugin_{self._plugin_id}_{job_id}", func=func, name=self._plugin_name, jobstore="plugin", **kwargs
        )
        if job:
            self.info(f"interval 任务已注册: {job_id}")
            return True
        self.error(f"interval 任务注册失败: {job_id}")
        return False

    def schedule_date(self, job_id: str, func, run_date) -> bool:
        """注册一次性日期任务，返回是否成功"""
        job = self._scheduler.register_date(
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
        self._scheduler.remove_job(job_id=f"plugin_{self._plugin_id}_{job_id}", jobstore="plugin")

    @property
    def site_engine(self) -> Any:
        """获取站点引擎"""
        return self._site_engine

    @property
    def media_service(self) -> Any:
        """获取媒体服务"""
        return self._media_service

    @property
    def metadata_service(self) -> Any:
        """获取元数据快照服务"""
        return self._metadata_service

    @property
    def hook_system(self) -> Any:
        """获取钩子系统"""
        return self._hook_system

    def get_schedules(self):
        """获取当前插件的所有定时任务"""
        sched = self._scheduler
        if not sched:
            return []
        prefix = f"plugin_{self._plugin_id}_"
        return [j for j in sched.get_jobs(jobstore="plugin") if j.id.startswith(prefix)]

    def emit(self, event: str, data: dict | None = None) -> None:
        """触发全局事件"""

        self._hook_system.emit(event, data or {})

    # ---------- 消息命令注册（委托给 Message） ----------

    def register_message_command(self, cmd: str, desc: str, func) -> None:
        """注册消息命令，用户发送该命令时触发 func"""
        self._message.register_command(cmd=cmd, desc=desc, func=func, plugin_id=self._plugin_id)

    def unregister_message_command(self, cmd: str) -> None:
        """注销消息命令"""
        self._message.unregister_command(cmd)

    def unregister_all_message_commands(self) -> None:
        """注销该插件的所有消息命令"""
        self._message.clear_plugin_commands(self._plugin_id)

    def register_api(
        self,
        path: str,
        handler: Callable[[dict], object],
        methods: tuple[str, ...] | None = None,
    ) -> None:
        """注册插件自定义 API，由通用调度路由分发：
        GET/POST /api/plugin-framework/plugins/{plugin_id}/api/{path}
        默认仅 POST；只读接口显式传 methods=("GET",)。
        """
        api_registry.register_api(self._plugin_id, path, handler, methods)

    def unregister_all_apis(self) -> None:
        """注销该插件的所有自定义 API"""
        api_registry.unregister_plugin_apis(self._plugin_id)

    # ---------- 元数据扩展注册 ----------

    def register_metadata_provider(self, key: str, provider: Any) -> None:
        """注册元数据 provider（key 必须与 manifest 声明一致）."""
        self._assert_metadata_declared("providers", key)
        self._assert_private_visibility(provider)
        self._apply_required_permission(provider)
        metadata_registry.register_provider(provider, plugin_id=self._plugin_id, declared_key=key)

    def register_discovery_provider(self, key: str, provider: Any) -> None:
        """注册探索页发现来源."""
        self._assert_metadata_declared("discovery_providers", key)
        self._assert_private_visibility(provider)
        self._apply_required_permission(provider)
        metadata_registry.register_discovery_provider(provider, plugin_id=self._plugin_id, declared_key=key)

    def unregister_metadata_provider(self, key: str) -> None:
        """注销本插件注册的元数据 provider."""
        metadata_registry.unregister_provider(key, plugin_id=self._plugin_id)

    def unregister_discovery_provider(self, key: str) -> None:
        """注销本插件注册的探索来源."""
        metadata_registry.unregister_discovery_provider(key, plugin_id=self._plugin_id)

    def register_metadata_profile(self, kind: str, key: str, profile: Any) -> None:
        """注册 content/match/parser/naming/nfo 扩展."""
        field = {
            "content": "content_profiles",
            "match": "match_profiles",
            "parser": "parser_profiles",
            "naming": "naming_profiles",
            "nfo": "nfo_profiles",
        }.get(kind, kind)
        self._assert_metadata_declared(field, key)
        metadata_registry.register_profile(kind, key, profile, plugin_id=self._plugin_id, declared_key=key)

    def register_match_profile(self, key: str, profile: Any) -> None:
        self.register_metadata_profile("match", key, profile)

    def register_naming_profile(self, key: str, profile: Any) -> None:
        self.register_metadata_profile("naming", key, profile)

    def register_category_contribution(self, contribution: Any, persist: Any = None) -> None:
        """注册插件分类贡献；scope=core 时参与核心分类."""
        register_category_contribution(contribution, self._plugin_id, persist=persist)
        namespace = str(contribution.namespace).strip()
        if namespace not in self._category_contributions:
            self._category_contributions.append(namespace)
        self.info(f"分类贡献已注册: {namespace}")

    def unregister_category_contribution(self, namespace: str) -> None:
        unregister_category_contribution(namespace, self._plugin_id)
        if namespace in self._category_contributions:
            self._category_contributions.remove(namespace)

    def register_metadata_cleanup(self, cleanup: Callable[[], None]) -> None:
        """注册 provider 缓存/限流清理回调，卸载时自动执行."""
        self._metadata_cleanups.append(cleanup)

    def register_scraper_processor(self, kind: str, processor: Callable[..., Any]) -> None:
        """注册刮削后处理器：snapshot / poster / watermark."""
        scraper_processor_registry.register(self._plugin_id, kind, processor)
        if kind not in self._scraper_processors:
            self._scraper_processors.append(kind)

    def unregister_all_scraper_processors(self) -> None:
        scraper_processor_registry.unregister_plugin(self._plugin_id)
        self._scraper_processors.clear()

    def unregister_all_metadata(self) -> None:
        """注销该插件的全部 provider/发现来源/profile，并执行清理回调."""
        while self._metadata_cleanups:
            cleanup = self._metadata_cleanups.pop()
            with contextlib.suppress(Exception):
                cleanup()
        metadata_registry.unregister_plugin(self._plugin_id)
        unregister_plugin_contributions(self._plugin_id)
        self._category_contributions.clear()

    def _assert_metadata_declared(self, field: str, key: str) -> None:
        manifest = self._metadata_manifest
        declared = manifest.keys(field) if manifest is not None else set()
        if declared and key not in declared:
            raise ValueError(f"插件未在 manifest 声明 {field}: {key}")

    def _apply_required_permission(self, provider: Any) -> None:
        descriptor = getattr(provider, "descriptor", None)
        manifest = self._metadata_manifest
        if descriptor is None or manifest is None:
            return
        required = getattr(manifest, "required_permission", "")
        if getattr(self, "_metadata_visibility", "public") == "private" and required:
            if not getattr(descriptor, "required_permission", ""):
                descriptor.required_permission = required

    def _assert_private_visibility(self, provider: Any) -> None:
        descriptor = getattr(provider, "descriptor", None)
        visibility = getattr(descriptor, "visibility", "public")
        if self._metadata_visibility == "private" and visibility != "private":
            raise ValueError("私有插件包注册的 provider 必须声明 visibility=private")
        if self._metadata_visibility == "public" and visibility == "private":
            raise ValueError("私有 provider 必须由 private 插件包注册")

    def ensure_filter_group(self, name: str, rules: list[dict], default: str = "N") -> int:
        """确保插件声明的过滤规则组存在；已存在时保留用户修改."""
        if not self._filter_service:
            self.warn("过滤规则服务未注入，跳过默认规则组")
            return 0
        try:
            return int(self._filter_service.ensure_filter_group(name, rules, default))
        except Exception as exc:  # noqa: BLE001
            self.error(f"创建默认过滤规则组失败: {exc}")
            return 0

    def clear_discovery_cache(self) -> None:
        """插件配置改变后清空探索来源缓存."""
        if self._discovery_service is not None:
            self._discovery_service.clear_cache()

    def register_message_image_transformer(self, transformer: Callable[[str, str], str]) -> None:
        """注册通知图片改写器；仅影响消息，不改变页面展示图片."""
        register_message_image_transformer(transformer)

    def unregister_message_image_transformer(self, transformer: Callable[[str, str], str]) -> None:
        """移除通知图片改写器."""
        unregister_message_image_transformer(transformer)

    def register_display_image_transformer(self, transformer: Callable[[str, str], str]) -> None:
        """注册展示图片改写器；探索/下载/历史/订阅/通知共用."""
        register_display_image_transformer(transformer)

    def unregister_display_image_transformer(self, transformer: Callable[[str, str], str]) -> None:
        """移除展示图片改写器."""
        unregister_display_image_transformer(transformer)

    def register_public_webhook(self, path: str, handler: Callable[[dict], object]) -> None:
        """注册插件公开回调（免鉴权），供飞书/Telegram 等外部平台 webhook 回调：
        POST /api/plugin-framework/webhooks/{plugin_id}/{path}
        """
        api_registry.register_public_webhook(self._plugin_id, path, handler)

    @property
    def message(self) -> Any:
        """消息业务 Facade"""
        return self._message
