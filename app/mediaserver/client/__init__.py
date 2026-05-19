from app.mediaserver.registry import register

from .emby import Emby
from .fnos import FnOS
from .jellyfin import Jellyfin
from .plex import Plex


def init_clients() -> None:
    """显式注册所有内置媒体服务器。在应用启动时调用。"""
    register(Emby)
    register(Jellyfin)
    register(Plex)
    register(FnOS)
