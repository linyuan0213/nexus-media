"""
Config - YAML 配置管理器（核心）
只负责 config.yaml 的读写，不含任何业务辅助方法
"""

import io
import os
import shutil
import sys
import tempfile
import threading
from threading import Lock

import ruamel.yaml
from filelock import FileLock

from app.core.settings import AppSettings

_ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


class _SingletonMeta(type):
    _instances = {}
    _lock = threading.RLock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


lock = Lock()


class Config(metaclass=_SingletonMeta):
    """YAML 配置管理器：仅负责 config.yaml 的读写"""

    def __init__(self):
        settings = AppSettings()
        self._config_path = settings.nastool_config or os.environ.get("NASTOOL_CONFIG")
        self._settings = settings

        tz = settings.tz or os.environ.get("TZ")
        if not os.environ.get("TZ"):
            os.environ["TZ"] = tz or "Asia/Shanghai"

        self._init_syspath()
        self._init_config()

    def _init_config(self):
        try:
            if not self._config_path:
                print("【Config】NASTOOL_CONFIG 环境变量未设置，程序无法工作，正在退出...")
                quit()

            if not os.path.exists(self._config_path):
                os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
                template = os.path.join(_ROOT_PATH, "config", "config.yaml").replace("\\", "/")
                shutil.copy(template, self._config_path)
                print("【Config】config.yaml 配置文件不存在，已将配置文件模板复制到配置目录...")

            with open(self._config_path, encoding="utf-8") as cf:
                try:
                    print(f"正在加载配置：{self._config_path}")
                    self._config = ruamel.yaml.YAML().load(cf)
                except Exception as e:
                    print(f"【Config】配置文件 config.yaml 格式出现严重错误！请检查：{str(e)}")
                    self._config = {}

            self._apply_env_database_config()

        except Exception as err:
            print(f"【Config】加载 config.yaml 配置出错：{str(err)}")
            return False

    def _apply_env_database_config(self):
        env_db_config = self._settings.get_database_config()
        if not env_db_config:
            return
        current = self._config.get("database", {}) or {}
        current.update(env_db_config)
        self._config["database"] = current
        try:
            self.save_config(self._config)
            print("【Config】已从环境变量更新数据库配置到配置文件")
        except Exception as e:
            print(f"【Config】保存数据库配置到文件失败：{str(e)}")

    def _init_syspath(self):
        txt = os.path.join(_ROOT_PATH, "third_party.txt")
        if not os.path.exists(txt):
            return
        with open(txt) as f:
            for line in f.readlines():
                p = os.path.join(_ROOT_PATH, "third_party", line.strip()).replace("\\", "/")
                if p not in sys.path:
                    sys.path.append(p)

    # ---------- 核心接口 ----------

    def get(self, node=None):
        """读取配置节点；node=None 时返回全部"""
        if not node:
            return self._config
        return self._config.get(node, {})

    def save(self, new_cfg):
        """保存完整配置到 YAML 文件"""
        self._config = new_cfg
        yaml = ruamel.yaml.YAML()
        try:
            yaml.dump(new_cfg, io.StringIO())
        except Exception as e:
            raise ValueError(f"Invalid YAML data: {e}") from e

        lock_path = self._config_path + ".lock"
        with FileLock(lock_path):
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as temp_file:
                yaml.dump(new_cfg, temp_file)
                temp_path = temp_file.name
            shutil.move(temp_path, self._config_path or "")

    @property
    def config_path(self):
        """配置目录路径"""
        return os.path.dirname(self._config_path or "")

    @property
    def current_user(self):
        return getattr(self, "_user", None)

    @current_user.setter
    def current_user(self, user):
        self._user = user

    # 向后兼容别名
    get_config = get
    save_config = save
    get_config_path = config_path.fget
