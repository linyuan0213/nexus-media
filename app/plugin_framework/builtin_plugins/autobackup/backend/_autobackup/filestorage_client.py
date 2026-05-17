import contextlib
import os
import shutil
from abc import ABC, abstractmethod

from smbclient import makedirs, open_file, register_session, remove, scandir
from smbclient.path import isdir
from smbclient.shutil import rmtree
from webdav4.client import Client, ResourceAlreadyExists, ResourceNotFound


class FileStorageClient(ABC):
    @abstractmethod
    def list_files(self, path) -> list:
        pass

    @abstractmethod
    def download_file(self, remote_path, local_path):
        pass

    @abstractmethod
    def upload_file(self, local_path, remote_path):
        pass

    @abstractmethod
    def delete_file(self, path):
        pass


class WebDAVClient(FileStorageClient):
    def __init__(self, base_url, username, password, share_name):
        base_url = f"{base_url.rstrip('/')}/{share_name.rstrip('/')}"
        auth = (username, password)
        self.client = Client(base_url, auth)

    def list_files(self, path="/"):
        files = self.client.ls(path)
        return [file.get("name") for file in files if file.get("type") != "directory"]  # type: ignore[union-attr]

    def download_file(self, remote_path, local_path):
        try:
            self.client.download_file(remote_path, local_path)
        except ResourceNotFound:
            os.remove(local_path)

    def upload_file(self, local_path, remote_path):
        with contextlib.suppress(ResourceAlreadyExists):
            self.client.upload_file(local_path, remote_path)

    def delete_file(self, path):
        with contextlib.suppress(ResourceNotFound):
            self.client.remove(path)


class SambaClient(FileStorageClient):
    def __init__(self, base_url, username, password, client_name, server_name, share_name):
        if not base_url.startswith("smb://"):
            raise ValueError("Samba base_url must start with 'smb://'")

        url_parts = base_url.replace("smb://", "").split(":")
        self._server = url_parts[0]
        self._port = int(url_parts[1]) if len(url_parts) > 1 else 445
        self._share = share_name
        self._base = f"\\\\{self._server}\\{self._share}"

        if username:
            register_session(
                self._server,
                username=username,
                password=password,
                port=self._port,
            )

    def _path(self, path: str) -> str:
        return os.path.join(self._base, path.lstrip("/").replace("/", "\\"))

    def list_files(self, path="/"):
        rp = self._path(path)
        return [entry.name for entry in scandir(rp) if not entry.is_dir()]

    def download_file(self, remote_path, local_path):
        try:
            with open_file(self._path(remote_path), mode="rb") as src, open(local_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.remove(local_path)

    def upload_file(self, local_path, remote_path):
        rp = self._path(remote_path)
        makedirs(os.path.dirname(rp), exist_ok=True)
        with open(local_path, "rb") as src, open_file(rp, mode="wb") as dst:
            shutil.copyfileobj(src, dst)

    def delete_file(self, path):
        rp = self._path(path)
        if isdir(rp):
            rmtree(rp)
        else:
            remove(rp)


class LocalClient(FileStorageClient):
    def __init__(self, share_name="."):
        self.root_directory = share_name

    def list_files(self, path=""):
        path = "" if path == "/" else path
        full_path = os.path.join(self.root_directory, path)
        return [file for file in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, file))]

    def download_file(self, remote_path, local_path):
        full_remote_path = os.path.join(self.root_directory, remote_path)
        shutil.copy(full_remote_path, local_path)

    def upload_file(self, local_path, remote_path):
        full_remote_path = os.path.join(self.root_directory, remote_path)
        shutil.copy(local_path, full_remote_path)

    def delete_file(self, path):
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)


class FileClientFactory:
    @staticmethod
    def create_client(client_type, **kwargs):
        client_type = client_type.lower()
        if client_type == "webdav":
            return WebDAVClient(
                base_url=kwargs.get("base_url"),
                username=kwargs.get("username"),
                password=kwargs.get("password"),
                share_name=kwargs.get("share_name"),
            )
        elif client_type == "samba":
            return SambaClient(
                base_url=kwargs.get("base_url"),
                username=kwargs.get("username"),
                password=kwargs.get("password"),
                client_name="NT",
                server_name="",
                share_name=kwargs.get("share_name"),
            )
        return None
