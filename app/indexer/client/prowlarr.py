from app.helper import IndexerConf
from app.indexer.client._base import _IIndexClient
from app.indexer.schema import ConfigField, IndexerConfigSchema
from app.utils import ExceptionUtils, RequestUtils
from app.di import container


class Prowlarr(_IIndexClient):
    schema = "prowlarr"
    _client_config = {}
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

    def __init__(self, config=None):
        super().__init__()
        if config:
            self._client_config = config
        else:
            from app.utils.types import SystemConfigKey

            indexer_config = container.system_config().get(SystemConfigKey.IndexerConfig) or {}
            self._client_config = indexer_config.get("prowlarr") or {}
        self._refresh()

    def _refresh(self):
        if self._client_config:
            self.api_key = self._client_config.get("api_key")
            self.host = self._client_config.get("host")
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

    def get_status(self):
        """
        检查连通性
        :return: True、False
        """
        if not self.api_key or not self.host:
            return False
        return bool(self.get_indexers())

    def get_indexers(self, check=True, indexer_id=None, public=True):
        """
        获取配置的prowlarr indexer
        :return: indexer 信息 [(indexerId, indexerName, url)]
        """
        indexer_query_url = f"{self.host}api/v1/indexerstats?apikey={self.api_key}"
        try:
            ret = RequestUtils().get_res(indexer_query_url)
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            return []
        if not ret:
            return []
        indexers = ret.json().get("indexers", [])
        return [
            IndexerConf(
                {"id": v["indexerId"], "name": v["indexerName"], "domain": f"{self.host}{v['indexerId']}/api"},
                builtin=False,
            )
            for v in indexers
        ]

    def search(self, order_seq, indexer, key_word, filter_args, match_media, in_from):
        return super().search(order_seq, indexer, key_word, filter_args, match_media, in_from)
