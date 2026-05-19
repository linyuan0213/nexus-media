from app.downloader.registry import register

from .qbittorrent import Qbittorrent
from .transmission import Transmission
from .aria2 import Aria2
from .thunder import Thunder

register(Qbittorrent)
register(Transmission)
register(Aria2)
register(Thunder)
