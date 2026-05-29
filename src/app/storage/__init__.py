"""存储系统 — 统一文件操作抽象层。"""

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig, StorageType
from app.storage.backends.local import LocalStorageBackend
from app.storage.backends.openlist import OpenListStorageBackend
from app.storage.backends.rclone import RcloneStorageBackend
from app.storage.backends.s3 import S3StorageBackend
from app.storage.backends.smb import SMBStorageBackend
from app.storage.backends.webdav import WebDAVStorageBackend
from app.storage.cross_backend import cross_copy, cross_move
from app.storage.factory import StorageBackendFactory

__all__ = [
    "FileInfo",
    "LocalStorageBackend",
    "OpenListStorageBackend",
    "RcloneStorageBackend",
    "S3StorageBackend",
    "SMBStorageBackend",
    "StorageBackend",
    "StorageBackendFactory",
    "StorageConfig",
    "StorageType",
    "WebDAVStorageBackend",
    "cross_copy",
    "cross_move",
]
