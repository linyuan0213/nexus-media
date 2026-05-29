from app.downloader.registry import register

from .aria2 import Aria2
from .qbittorrent import Qbittorrent
from .thunder import Thunder
from .transmission import Transmission


def init_clients() -> None:
    """显式注册所有内置下载器。在应用启动时调用。"""
    register(Qbittorrent)
    register(Transmission)
    register(Aria2)
    register(Thunder)
