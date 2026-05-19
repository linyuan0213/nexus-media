from app.indexer.registry import register

from .builtin import BuiltinIndexer
from .jackett import Jackett
from .prowlarr import Prowlarr


def init_clients() -> None:
    """显式注册所有内置索引器。在应用启动时调用。"""
    register(BuiltinIndexer)
    register(Jackett)
    register(Prowlarr)
