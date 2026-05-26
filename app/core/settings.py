"""
AppSettings - 基于 pydantic-settings 的应用配置
支持 .env 文件、环境变量和 config.yaml，优先级：环境变量 > .env > config.yaml
"""

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import ruamel.yaml
from filelock import FileLock
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_ROOT_PATH = Path(__file__).parent.parent.parent.resolve()


class AppConfig(BaseModel):
    """应用核心配置"""

    web_host: str = "::"
    web_port: int = 3000
    login_user: str = "admin"
    login_password: str = "password"
    ssl_cert: str = ""
    ssl_key: str = ""
    rmt_tmdbkey: str = ""
    rmt_match_mode: str = "normal"
    proxies: dict = Field(default_factory=lambda: {"https": None, "http": None})
    domain: str = ""
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    )
    init_files: list[str] = Field(default_factory=list)
    tmdb_domain: str = "api.themoviedb.org"
    wallpaper: str = "bing"
    debug: bool = True
    releases_update_only: bool = False
    tmdb_image_url: str = ""
    enable_image_proxy: int = 1
    cookie_secure: bool = False


class MediaConfig(BaseModel):
    """媒体库配置（路径字段已迁移到数据库 CONFIGMEDIA 表）"""

    mediasync_interval: str = "8"
    category: str = "default-category"
    min_filesize: str = "150"
    filesize_cover: bool = True
    movie_name_format: str = "{title} ({year})/{title}-{part} ({year}) - {videoFormat}"
    tv_name_format: str = "{title} ({year})/Season {season}/{title}-{part} - {season_episode} - 第{episode}集"
    nfo_poster: bool = True
    refresh_mediaserver: bool = True
    ignored_paths: str = "Specials;Extras;Bonus.*;.*Scan;Menu.*;CDs"
    ignored_files: str = "SP\\d+"
    media_default_path: str = ""
    default_rmt_mode: str = "link"
    tmdb_language: str = "zh"
    episode_mapping_enabled: bool = True


class PtConfig(BaseModel):
    """站点搜索配置"""

    search_auto: bool = False
    search_no_result_rss: bool = False
    pt_check_interval: str = "3600"
    search_rss_interval: str = "6"
    download_order: str = "seeder"
    ptrefresh_date_cron: str = "22:36"


class WebhookAllowIp(BaseModel):
    """Webhook 允许 IP 范围"""

    ipv4: str = "0.0.0.0/0"
    ipv6: str = "::/0"


class SecurityConfig(BaseModel):
    """安全配置"""

    media_server_webhook_allow_ip: WebhookAllowIp = Field(default_factory=WebhookAllowIp)
    telegram_webhook_allow_ip: WebhookAllowIp = Field(default_factory=WebhookAllowIp)
    synology_webhook_allow_ip: WebhookAllowIp = Field(default_factory=WebhookAllowIp)
    jwt_secret: str = ""


class LaboratoryConfig(BaseModel):
    """实验室功能配置"""

    search_keyword: bool = False
    tmdb_cache_expire: bool = True
    use_douban_titles: bool = True
    search_en_title: bool = True
    show_more_sites: bool = True
    ocr_server_host: str = ""
    search_multi_language: bool = True
    chrome_server_host: str = ""


class AgentProviderConfig(BaseModel):
    """Agent 提供商配置"""

    api_key: str = ""
    api_url: str = ""
    model: str = ""


class AgentConfig(BaseModel):
    """Agent 配置"""

    enabled: bool = True
    default_provider: str = ""
    media_recognizer_enabled: bool = False
    batch_size: int = 100
    providers: dict[str, AgentProviderConfig] = Field(default_factory=dict)


class DatabaseConfig(BaseModel):
    """数据库配置"""

    type: str = "sqlite"
    host: str = "localhost"
    port: int = 0
    username: str = ""
    password: str = ""
    database: str = "nas_tools"


class LogConfig(BaseModel):
    """日志配置"""

    type: str = "file"
    level: str = "debug"
    server: str = ""
    path: str = ""


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """从 config.yaml 加载配置的自定义 SettingsSource"""

    def get_field_value(self, field, field_name: str) -> tuple[Any, str, bool]:
        yaml_data = self._load_yaml()
        value = yaml_data.get(field_name)
        if value is not None:
            return value, field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        yaml_data = self._load_yaml()
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            if field_name in yaml_data:
                result[field_name] = yaml_data[field_name]
        return result

    def _load_yaml(self) -> dict[str, Any]:
        config_path = os.environ.get("NEXUS_MEDIA_CONFIG", "")
        if not config_path or not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, encoding="utf-8") as f:
                return ruamel.yaml.YAML().load(f) or {}
        except Exception:
            return {}


class AppSettings(BaseSettings):
    """
    Nexus Media 统一配置（pydantic-settings）
    支持环境变量、.env 文件和 config.yaml，优先级：环境变量 > .env > config.yaml
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    nexus_media_config: str = ""
    tz: str = "Asia/Shanghai"

    app: AppConfig = Field(default_factory=AppConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    pt: PtConfig = Field(default_factory=PtConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    laboratory: LaboratoryConfig = Field(default_factory=LaboratoryConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig, validate_default=True)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @field_validator("agent", mode="before")
    @classmethod
    def _validate_agent(cls, v):
        if not isinstance(v, dict):
            return AgentConfig()
        return v

    log: LogConfig = Field(default_factory=LogConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    def get(self, node: str | None = None) -> Any:
        """读取配置节点；node=None 时返回全部字典"""
        data = self.model_dump(exclude={"nexus_media_config", "tz"}, exclude_none=False)
        if not node:
            return data
        return data.get(node, {})

    def save(self, new_cfg: dict[str, Any]) -> None:
        """保存完整配置到 YAML 文件"""
        yaml = ruamel.yaml.YAML()
        try:
            yaml.dump(new_cfg, io.StringIO())
        except Exception as e:
            raise ValueError(f"Invalid YAML data: {e}") from e

        config_path = self._config_path()
        lock_path = config_path + ".lock"
        with FileLock(lock_path):
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as temp_file:
                yaml.dump(new_cfg, temp_file)
                temp_path = temp_file.name
            shutil.move(temp_path, config_path)

    def reload(self) -> None:
        """重新从 YAML 文件加载配置"""
        new = AppSettings()
        for key in self.model_fields:
            setattr(self, key, getattr(new, key))

    def get_database_config(self) -> dict[str, Any]:
        """获取数据库配置字典"""
        config: dict[str, Any] = {}
        if self.database.type:
            config["type"] = self.database.type
        if self.database.host:
            config["host"] = self.database.host
        if self.database.port:
            config["port"] = self.database.port
        if self.database.username:
            config["username"] = self.database.username
        if self.database.password:
            config["password"] = self.database.password
        if self.database.database:
            config["database"] = self.database.database
        return config

    def _config_path(self) -> str:
        return self.nexus_media_config or os.environ.get("NEXUS_MEDIA_CONFIG", "")

    @property
    def config_path(self) -> str:
        return os.path.dirname(self._config_path())


def _init_config_file() -> str:
    config_path = os.environ.get("NEXUS_MEDIA_CONFIG", "")
    if not config_path:
        print("【Config】NEXUS_MEDIA_CONFIG 环境变量未设置，程序无法工作，正在退出...")
        sys.exit()

    if not os.path.exists(config_path):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        template = str(_ROOT_PATH / "config" / "config.yaml")
        shutil.copy(template, config_path)
        print("【Config】config.yaml 配置文件不存在，已将配置文件模板复制到配置目录...")

    return config_path


def _init_syspath() -> None:
    for pkg in ("anitopy",):
        p = str(_ROOT_PATH / "third_party" / pkg)
        if p not in sys.path:
            sys.path.append(p)


def _apply_env_database_config(settings: AppSettings) -> None:
    env_db: dict[str, Any] = {}
    if os.environ.get("DB_TYPE"):
        env_db["type"] = os.environ["DB_TYPE"]
    if os.environ.get("DB_HOST"):
        env_db["host"] = os.environ["DB_HOST"]
    if os.environ.get("DB_PORT"):
        env_db["port"] = os.environ["DB_PORT"]
    if os.environ.get("DB_USERNAME"):
        env_db["username"] = os.environ["DB_USERNAME"]
    if os.environ.get("DB_PASSWORD"):
        env_db["password"] = os.environ["DB_PASSWORD"]
    if os.environ.get("DB_NAME"):
        env_db["database"] = os.environ["DB_NAME"]
    if not env_db:
        return
    current = settings.database.model_dump()
    current.update(env_db)
    try:
        settings.save({"database": current})
        print("【Config】已从环境变量更新数据库配置到配置文件")
    except Exception as e:
        print(f"【Config】保存数据库配置到文件失败：{e!s}")


_config_path = _init_config_file()

tz = os.environ.get("TZ", "Asia/Shanghai")
if not os.environ.get("TZ"):
    os.environ["TZ"] = tz

_init_syspath()

settings = AppSettings()

if _config_path:
    print(f"正在加载配置：{_config_path}")
    _apply_env_database_config(settings)
