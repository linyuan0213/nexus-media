"""Jackett 索引器客户端。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.indexer.client._torznab import TorznabIndexerClient
from app.indexer.configuration import IndexerConf
from app.indexer.schema import ConfigField, IndexerConfigSchema
from app.infrastructure.http.client import HttpClient


class Jackett(TorznabIndexerClient):
    schema = "jackett"
    index_type = "Jackett"
    client_id = "jackett"
    client_type = "jackett"
    client_name = "Jackett"
    config_schema = IndexerConfigSchema(
        name="Jackett",
        icon_url="/static/img/indexer/jackett.png",
        fields=[
            ConfigField(
                id="host",
                required=True,
                title="Jackett地址",
                tooltip="Jackett访问地址和端口，如为https需加https://前缀。注意需要先在Jackett中添加indexer，才能正常测试通过和使用",
                type="text",
                placeholder="http://127.0.0.1:9117",
            ),
            ConfigField(
                id="api_key",
                required=True,
                title="Api Key",
                tooltip="Jackett管理界面右上角复制API Key",
                type="text",
                placeholder="",
            ),
            ConfigField(
                id="password",
                required=False,
                title="密码",
                tooltip="Jackett管理界面中配置的Admin password，如未配置可为空",
                type="password",
                placeholder="",
            ),
        ],
    )

    def __init__(self, config=None, **kwargs):
        super().__init__(**kwargs)
        self._client_config = config or {}
        self._password = None
        self._refresh()

    def _refresh(self) -> None:
        if self._client_config:
            self.api_key = self._client_config.get("api_key", "")
            self._password = self._client_config.get("password")
            self.host = self._client_config.get("host", "")
            if self.host:
                if not self.host.startswith("http"):
                    self.host = "http://" + self.host
                if not self.host.endswith("/"):
                    self.host = self.host + "/"

    @classmethod
    def match(cls, ctype):
        return ctype in [cls.schema, cls.index_type]

    def get_type(self):
        return self.client_type

    def get_client_id(self):
        return self.client_id

    def _fetch_indexers(self) -> list[Any]:
        indexer_query_url = f"{self.host}api/v2.0/indexers?configured=true&apikey={self.api_key}"
        client = HttpClient()
        client.post(url=f"{self.host}UI/Dashboard", data={"password": self._password})
        ret = client.get(indexer_query_url)
        if not ret:
            raise RuntimeError("Jackett 索引器列表请求无响应")
        return [
            IndexerConf(
                datas={
                    "id": v["id"],
                    "name": v["name"],
                    "domain": f"{self.host}api/v2.0/indexers/{v['id']}/results/torznab/api",
                },
                public=v["type"] in ("public", "semi-private"),
                builtin=False,
            )
            for v in ret.json()
        ]

    def _search_items(self, indexer: Any, keyword: str) -> list[dict[str, Any]]:
        search_word = self._search_text(keyword)
        api_url = (
            f"{self.host}api/v2.0/indexers/all/results"
            f"?apikey={self.api_key}"
            f"&Query={quote(search_word)}"
            f"&Tracker[]={quote(str(indexer.id))}"
        )
        ret = HttpClient().get(api_url)
        if not ret:
            raise RuntimeError("Jackett 搜索请求无响应")
        return self._to_items(ret.json().get("Results", []))

    def _list_items(self, indexer: Any, keyword: str | None, offset: int, limit: int) -> list[dict[str, Any]]:
        api_url = f"{self.host}api/v2.0/indexers/all/results?apikey={self.api_key}"
        if keyword:
            api_url += f"&Query={quote(self._search_text(keyword))}"
        api_url += f"&Tracker[]={quote(str(indexer.id))}"
        ret = HttpClient().get(api_url)
        if not ret:
            raise RuntimeError("Jackett 列表请求无响应")
        items = self._to_items(ret.json().get("Results", []))
        return items[offset : offset + limit]

    @staticmethod
    def _to_items(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": row.get("Title", ""),
                "enclosure": row.get("Link") or row.get("MagnetUri") or "",
                "description": row.get("Details", ""),
                "page_url": row.get("Details", ""),
                "size": row.get("Size", 0),
                "seeders": row.get("Seeders", 0),
                "peers": row.get("Peers", 0),
                "uploadvolumefactor": row.get("UploadVolumeFactor"),
                "downloadvolumefactor": row.get("DownloadVolumeFactor"),
            }
            for row in results
        ]
