"""Prowlarr 索引器客户端。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.indexer.client._torznab import TorznabIndexerClient
from app.indexer.configuration import IndexerConf
from app.indexer.schema import ConfigField, IndexerConfigSchema
from app.infrastructure.http.client import HttpClient


class Prowlarr(TorznabIndexerClient):
    schema = "prowlarr"
    index_type = "Prowlarr"
    client_id = "prowlarr"
    client_type = "prowlarr"
    client_name = "Prowlarr"
    config_schema = IndexerConfigSchema(
        name="Prowlarr",
        icon_url="/static/img/indexer/prowlarr.png",
        fields=[
            ConfigField(
                id="host",
                required=True,
                title="Prowlarr地址",
                tooltip="Prowlarr访问地址和端口，如为https需加https://前缀。注意需要先在Prowlarr中添加搜刮器，同时勾选所有搜刮器后搜索一次，才能正常测试通过和使用",
                type="text",
                placeholder="http://127.0.0.1:9696",
            ),
            ConfigField(
                id="api_key",
                required=True,
                title="Api Key",
                tooltip="在Prowlarr->Settings->General->Security-> API Key中获取",
                type="text",
                placeholder="",
            ),
        ],
    )

    def __init__(self, config=None, **kwargs):
        super().__init__(**kwargs)
        self._client_config = config or {}
        self._refresh()

    def _refresh(self) -> None:
        if self._client_config:
            self.api_key = self._client_config.get("api_key", "")
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
        ret = HttpClient().get(f"{self.host}api/v1/indexer?apikey={self.api_key}")
        if not ret:
            raise RuntimeError("Prowlarr 索引器列表请求无响应")
        return [
            IndexerConf(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "domain": f"{self.host}{row.get('id')}/api",
                },
                builtin=False,
                public=row.get("privacy") in ("public", "semiPrivate"),
            )
            for row in ret.json()
        ]

    def _search_items(self, indexer: Any, keyword: str) -> list[dict[str, Any]]:
        api_url = f"{indexer.domain}?apikey={self.api_key}&t=search&q={quote(self._search_text(keyword))}"
        return self._parse_torznabxml(api_url)

    def _list_items(self, indexer: Any, keyword: str | None, offset: int, limit: int) -> list[dict[str, Any]]:
        api_url = f"{indexer.domain}?apikey={self.api_key}&t=search&offset={offset}&limit={limit}"
        if keyword:
            api_url += f"&q={quote(self._search_text(keyword))}"
        return self._parse_torznabxml(api_url)
