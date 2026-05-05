# -*- coding: utf-8 -*-
"""
AppSettings - 基于 pydantic-settings 的应用配置
支持 .env 文件和环境变量，优先级高于 config.yaml
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    NAS-Tools 应用级环境变量配置
    所有字段均可通过 .env 文件或环境变量设置
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )

    # 基础路径
    nastool_config: str = ""
    """config.yaml 配置文件路径"""

    tz: str = "Asia/Shanghai"
    """时区"""

    # 数据库
    db_type: str = ""
    db_host: str = ""
    db_port: int = 0
    db_username: str = ""
    db_password: str = ""
    db_name: str = ""

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: str = "6379"

    # 日志
    log_type: str = ""
    log_server: str = ""
    log_path: str = ""

    # TMDB
    tmdb_api_domain: str = ""

    # 代理
    proxies: str = ""

    # UA
    user_agent: str = ""

    # 安全
    api_key: str = ""

    @property
    def has_database_config(self) -> bool:
        return bool(self.db_type or self.db_host or self.db_name)

    def get_database_config(self) -> dict:
        config = {}
        if self.db_type:
            config["type"] = self.db_type
        if self.db_host:
            config["host"] = self.db_host
        if self.db_port:
            config["port"] = self.db_port
        if self.db_username:
            config["username"] = self.db_username
        if self.db_password:
            config["password"] = self.db_password
        if self.db_name:
            config["database"] = self.db_name
        return config
