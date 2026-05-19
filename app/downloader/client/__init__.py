from app.downloader.registry import register

from .qbittorrent import Qbittorrent
from .transmission import Transmission
from .aria2 import Aria2
from .thunder import Thunder


def init_clients() -> None:
    """显式注册所有内置下载器。在应用启动时调用。"""
    register(Qbittorrent)
    register(Transmission)
    register(Aria2)
    register(Thunder)
