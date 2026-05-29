"""ConfigReloader — 集中式配置热重载协调器（DI provider reset 模式）.

职责：
1. 维护 provider 重载优先级列表
2. 配置变更时按优先级 reset + 重新实例化各 provider
3. 失败隔离：单个 provider 重置失败不影响其他
4. 可观测：每一步都记录日志

用法：
    # 注册 provider（字符串名）和优先级
    container.config_reloader().register("category", priority=0)
    container.config_reloader().register("sites", priority=1)
    container.config_reloader().register("downloader_core", priority=10)

    # 触发重载
    container.config_reloader().reload()
"""

from dataclasses import dataclass, field

import log


@dataclass(order=True)
class _ReloadStep:
    """重载步骤 — 按 priority 排序（数值越小越优先）."""

    priority: int
    name: str = field(compare=False)


class ConfigReloader:
    """集中式配置热重载协调器."""

    # 标准优先级分组（数值越小越早执行）
    PRIORITY_SETTINGS = 0  # AppSettings / SystemConfig
    PRIORITY_CATEGORY = 5  # Category 策略文件
    PRIORITY_INFRA = 10  # Sites, SiteConf, SiteUserInfo
    PRIORITY_CORE = 20  # DownloaderCore, MediaServer, Message
    PRIORITY_SERVICE = 30  # FileTransfer, SearchService, BrushCore
    PRIORITY_INDEXER = 40  # Indexer 及客户端
    PRIORITY_PLUGIN = 50  # PluginFramework
    PRIORITY_AUX = 100  # ProgressHelper, ThreadHelper, WordsHelper

    def __init__(self):
        self._steps: list[_ReloadStep] = []
        self._version = 0
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册所有需要热重载的 provider（按优先级分组）."""
        # 基础配置（最优先）
        self.register("system_config", self.PRIORITY_SETTINGS)
        self.register("category", self.PRIORITY_CATEGORY)
        # 核心基础设施
        self.register("sites", self.PRIORITY_INFRA)
        self.register("site_conf", self.PRIORITY_INFRA)
        self.register("site_userinfo", self.PRIORITY_INFRA)
        # 核心服务
        self.register("downloader_core", self.PRIORITY_CORE)
        self.register("media_server", self.PRIORITY_CORE)
        self.register("message", self.PRIORITY_CORE)
        # 业务服务
        self.register("filetransfer_service", self.PRIORITY_SERVICE)
        self.register("searcher", self.PRIORITY_SERVICE)
        self.register("brush_task_service", self.PRIORITY_SERVICE)
        self.register("rss_task_service", self.PRIORITY_SERVICE)
        self.register("indexer_service", self.PRIORITY_INDEXER)
        # 辅助
        self.register("words_helper", self.PRIORITY_AUX)
        self.register("fanart", self.PRIORITY_AUX)

    def register(self, provider_name: str, priority: int = 100) -> None:
        """
        注册一个 DI provider，配置变更时 reset + 重新实例化.

        :param provider_name: container 上的 provider 属性名，如 "category"
        :param priority: 优先级，数值越小越早执行
        """
        self._steps = [s for s in self._steps if s.name != provider_name]
        self._steps.append(_ReloadStep(priority, provider_name))
        self._steps.sort()

    def unregister(self, provider_name: str) -> None:
        """注销一个 provider."""
        self._steps = [s for s in self._steps if s.name != provider_name]

    def reload(self, container) -> dict:
        """
        执行完整配置重载：按优先级 reset 并重载各 provider.

        :param container: DI 容器实例
        :return: {"version": int, "results": {name: bool}, "failed": [name]}
        """
        self._version += 1
        log.info(f"[ConfigReloader]开始配置重载，版本 v{self._version}")

        results: dict[str, bool] = {}
        failed: list[str] = []

        for step in self._steps:
            try:
                provider = getattr(container, step.name, None)
                if provider is None:
                    log.warn(f"[ConfigReloader][{step.priority}] {step.name} 未找到对应 provider，跳过")
                    continue

                log.debug(f"[ConfigReloader][{step.priority}] reset {step.name} ...")
                provider.reset()
                log.debug(f"[ConfigReloader][{step.priority}] re-instantiate {step.name} ...")
                provider()
                results[step.name] = True
                log.debug(f"[ConfigReloader][{step.priority}] {step.name} OK")
            except Exception as e:
                results[step.name] = False
                failed.append(step.name)
                log.error(f"[ConfigReloader][{step.priority}] {step.name} 失败: {e}")

        if failed:
            log.warn(f"[ConfigReloader]重载完成 v{self._version}，{len(failed)}/{len(self._steps)} 失败: {failed}")
        else:
            log.info(f"[ConfigReloader]重载完成 v{self._version}，全部 {len(self._steps)} 步成功")

        return {"version": self._version, "results": results, "failed": failed}

    @property
    def version(self) -> int:
        """当前配置版本号."""
        return self._version

    @property
    def steps(self) -> list[str]:
        """已注册的 provider 名称列表（按执行顺序）."""
        return [s.name for s in self._steps]
