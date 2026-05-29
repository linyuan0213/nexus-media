import requests

from app.helper import IndexerConf
from app.indexer.client._base import _IIndexClient
from app.indexer.schema import ConfigField, IndexerConfigSchema
from app.utils import ExceptionUtils, RequestUtils
from app.di import container


class Jackett(_IIndexClient):
    schema = "jackett"
    _client_config = {}
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
    _password = None

    def __init__(self, config=None):
        super().__init__()
        if config:
            self._client_config = config
        else:
            from app.utils.types import SystemConfigKey

            indexer_config = container.system_config().get(SystemConfigKey.IndexerConfig) or {}
            self._client_config = indexer_config.get("jackett") or {}
        self._refresh()

    def _refresh(self):
        if self._client_config:
            self.api_key = self._client_config.get("api_key")
            self._password = self._client_config.get("password")
            self.host = self._client_config.get("host")
            if self.host:
                if not self.host.startswith("http"):
                    self.host = "http://" + self.host
                if not self.host.endswith("/"):
                    self.host = self.host + "/"

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

    @classmethod
    def match(cls, ctype):
        return ctype in [cls.schema, cls.index_type]

    def get_indexers(self, check=True, indexer_id=None, public=True):
        """
        获取配置的jackett indexer
        :return: indexer 信息 [(indexerId, indexerName, url)]
        """
        # 获取Cookie
        cookie = None
        session = requests.session()
        res = RequestUtils(session=session).post_res(url=f"{self.host}UI/Dashboard", data={"password": self._password})
        if res and session.cookies:
            cookie = session.cookies.get_dict()
        indexer_query_url = f"{self.host}api/v2.0/indexers?configured=true"
        try:
            ret = RequestUtils(cookies=cookie).get_res(indexer_query_url)
            if not ret or not ret.json():
                return []
            return [
                IndexerConf(
                    datas={
                        "id": v["id"],
                        "name": v["name"],
                        "domain": f"{self.host}api/v2.0/indexers/{v['id']}/results/torznab/",
                    },
                    public=v["type"] == "public",
                    builtin=False,
                )
                for v in ret.json()
            ]
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            return []

    def search(self, order_seq, indexer, key_word, filter_args, match_media, in_from):
        return super().search(order_seq, indexer, key_word, filter_args, match_media, in_from)
