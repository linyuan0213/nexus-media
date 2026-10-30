"""数据库连接容量预算.

连接池容量、调度并发和目录同步并发必须共享同一个预算，避免各自按默认值
扩张后超过数据库服务端的可用连接槽位。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from app.core.settings import settings

_ENV_MAP = {
    "pool_size": "DATABASE__POOL_SIZE",
    "max_overflow": "DATABASE__MAX_OVERFLOW",
    "scheduler_pool_size": "DATABASE__SCHEDULER_POOL_SIZE",
    "scheduler_max_overflow": "DATABASE__SCHEDULER_MAX_OVERFLOW",
    "sync_workers": "DATABASE__SYNC_WORKERS",
    "max_connections": "DATABASE__MAX_CONNECTIONS",
    "connection_reserve": "DATABASE__CONNECTION_RESERVE",
    "external_reserve": "DATABASE__EXTERNAL_CONNECTION_RESERVE",
    "api_connection_reserve": "DATABASE__API_CONNECTION_RESERVE",
}

_DEFAULTS = {
    "pool_size": 10,
    "max_overflow": 10,
    "scheduler_pool_size": 5,
    "scheduler_max_overflow": 5,
    "sync_workers": 4,
    "max_connections": 100,
    "connection_reserve": 3,
    "external_reserve": 5,
    "api_connection_reserve": 8,
}
_DEFAULT_MYSQL_MAX_CONNECTIONS = 151


def _config_int(key: str, default: int) -> int:
    env_name = _ENV_MAP.get(key)
    if env_name:
        raw = os.environ.get(env_name)
        if raw:
            try:
                return max(0, int(raw))
            except ValueError:
                return default
    try:
        database = settings.get().get("database", {})
        value = database.get(key)
        if value is not None:
            return max(0, int(value))
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return default


@dataclass(frozen=True)
class ConnectionBudget:
    """进程级数据库连接预算."""

    main_pool_size: int
    main_max_overflow: int
    scheduler_pool_size: int
    scheduler_max_overflow: int
    sync_workers: int
    server_max_connections: int
    reserved_connections: int
    external_reserve: int
    transient_reserve: int = 2

    @property
    def main_capacity(self) -> int:
        return self.main_pool_size + self.main_max_overflow

    @property
    def scheduler_capacity(self) -> int:
        return self.scheduler_pool_size + self.scheduler_max_overflow

    @property
    def resident_connections(self) -> int:
        return self.main_pool_size + self.scheduler_pool_size + self.transient_reserve

    @property
    def available_connections(self) -> int:
        return max(0, self.server_max_connections - self.reserved_connections - self.external_reserve)

    @property
    def total_capacity(self) -> int:
        return self.main_capacity + self.scheduler_capacity + self.transient_reserve

    @property
    def is_valid(self) -> bool:
        return self.total_capacity <= self.available_connections

    def resolve(self) -> ConnectionBudget:
        """把配置收敛到服务端可用槽位内，并限制同步并发。

        优先保留常驻 pool_size，先削 overflow；仍不够时再削调度池/主池。
        显式配置过大时不会静默超过服务端容量。
        """
        available = self.available_connections
        main_pool = max(1, self.main_pool_size)
        sched_pool = max(1, self.scheduler_pool_size)
        transient = max(0, self.transient_reserve)

        if main_pool + sched_pool + transient > available:
            sched_pool = max(1, available - main_pool - transient)
        if main_pool + sched_pool + transient > available:
            main_pool = max(1, available - sched_pool - transient)
        if main_pool + sched_pool + transient > available:
            sched_pool = max(1, available - main_pool - transient)
        if main_pool + sched_pool + transient > available:
            main_pool = 1
            sched_pool = 1

        remaining = max(0, available - main_pool - sched_pool - transient)
        main_overflow = min(self.main_max_overflow, remaining)
        remaining -= main_overflow
        sched_overflow = min(self.scheduler_max_overflow, remaining)

        api_reserve = max(1, _config_int("api_connection_reserve", _DEFAULTS["api_connection_reserve"]))
        sync_limit = max(1, main_pool + main_overflow - api_reserve)
        sync_workers = max(1, min(self.sync_workers, sync_limit))

        return replace(
            self,
            main_pool_size=main_pool,
            main_max_overflow=main_overflow,
            scheduler_pool_size=sched_pool,
            scheduler_max_overflow=sched_overflow,
            sync_workers=sync_workers,
        )

    def describe(self) -> str:
        state = "OK" if self.is_valid else "OVER_BUDGET"
        return (
            f"主池 {self.main_pool_size}+{self.main_max_overflow}={self.main_capacity} 条，"
            f"调度池 {self.scheduler_pool_size}+{self.scheduler_max_overflow}={self.scheduler_capacity} 条，"
            f"临时预留 {self.transient_reserve} 条，合计 {self.total_capacity} 条；"
            f"服务端可用 {self.available_connections} 条（max_connections={self.server_max_connections}，"
            f"保留 {self.reserved_connections}+{self.external_reserve}），{state}"
        )


def load_connection_budget(
    db_type: str,
    server_max_connections: int | None = None,
    *,
    main_pool_size: int | None = None,
    main_max_overflow: int | None = None,
) -> ConnectionBudget:
    """从配置构造并收敛连接预算."""
    default_server = _DEFAULT_MYSQL_MAX_CONNECTIONS if db_type == "mysql" else _DEFAULTS["max_connections"]
    configured_server = server_max_connections or _config_int("max_connections", default_server)
    reserved = 0 if db_type == "mysql" else _config_int("connection_reserve", _DEFAULTS["connection_reserve"])
    budget = ConnectionBudget(
        main_pool_size=main_pool_size
        if main_pool_size is not None
        else _config_int("pool_size", _DEFAULTS["pool_size"]),
        main_max_overflow=main_max_overflow
        if main_max_overflow is not None
        else _config_int("max_overflow", _DEFAULTS["max_overflow"]),
        scheduler_pool_size=_config_int("scheduler_pool_size", _DEFAULTS["scheduler_pool_size"]),
        scheduler_max_overflow=_config_int("scheduler_max_overflow", _DEFAULTS["scheduler_max_overflow"]),
        sync_workers=_config_int("sync_workers", _DEFAULTS["sync_workers"]),
        server_max_connections=configured_server,
        reserved_connections=reserved,
        external_reserve=_config_int("external_reserve", _DEFAULTS["external_reserve"]) if db_type != "mysql" else 0,
    )
    if db_type == "sqlite":
        return replace(budget, server_max_connections=9999, reserved_connections=0, external_reserve=0)
    return budget.resolve()
