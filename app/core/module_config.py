from app.utils.types import IndexerType


class ModuleConf:
    # 索引器
    INDEXER_DICT = {"prowlarr": IndexerType.PROWLARR, "jackett": IndexerType.JACKETT, "builtin": IndexerType.BUILTIN}

    # 搜索种子过滤属性
    TORRENT_SEARCH_PARAMS = {
        "restype": {
            "BLURAY": r"Blu-?Ray|BD|BDRIP",
            "REMUX": r"REMUX",
            "DOLBY": r"DOLBY|DOVI|\s+DV$|\s+DV\s+",
            "WEB": r"WEB-?DL|WEBRIP",
            "HDTV": r"U?HDTV",
            "UHD": r"UHD",
            "HDR": r"HDR",
            "3D": r"3D",
        },
        "pix": {"8k": r"8K", "4k": r"4K|2160P|X2160", "1080p": r"1080[PIX]|X1080", "720p": r"720P"},
    }

    # 网络测试对象，TMDB API除外
    NETTEST_TARGETS = [
        "www.themoviedb.org",
        "image.tmdb.org",
        "webservice.fanart.tv",
        "api.telegram.org",
        "qyapi.weixin.qq.com",
        "frodo.douban.com",
    ]

    # 索引器
    INDEXER_CONF = {
        "jackett": {
            "name": "Jackett",
            "img_url": "./static/img/indexer/jackett.png",
            "background": "bg-black",
            "test_command": "app.indexer.client.jackett|Jackett",
            "config": {
                "host": {
                    "id": "jackett.host",
                    "required": True,
                    "title": "Jackett地址",
                    "tooltip": "Jackett访问地址和端口，如为https需加https://前缀。注意需要先在Jackett中添加indexer，才能正常测试通过和使用",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:9117",
                },
                "api_key": {
                    "id": "jackett.api_key",
                    "required": True,
                    "title": "Api Key",
                    "tooltip": "Jackett管理界面右上角复制API Key",
                    "type": "text",
                    "placeholder": "",
                },
                "password": {
                    "id": "jackett.password",
                    "required": False,
                    "title": "密码",
                    "tooltip": "Jackett管理界面中配置的Admin password，如未配置可为空",
                    "type": "password",
                    "placeholder": "",
                },
            },
        },
        "prowlarr": {
            "name": "Prowlarr",
            "img_url": "../static/img/indexer/prowlarr.png",
            "background": "bg-orange",
            "test_command": "app.indexer.client.prowlarr|Prowlarr",
            "config": {
                "host": {
                    "id": "prowlarr.host",
                    "required": True,
                    "title": "Prowlarr地址",
                    "tooltip": "Prowlarr访问地址和端口，如为https需加https://前缀。注意需要先在Prowlarr中添加搜刮器，同时勾选所有搜刮器后搜索一次，才能正常测试通过和使用",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:9696",
                },
                "api_key": {
                    "id": "prowlarr.api_key",
                    "required": True,
                    "title": "Api Key",
                    "tooltip": "在Prowlarr->Settings->General->Security-> API Key中获取",
                    "type": "text",
                    "placeholder": "",
                },
            },
        },
    }

    @staticmethod
    def get_enum_name(enum, value):
        """
        根据Enum的value查询name
        :param enum: 枚举
        :param value: 枚举值
        :return: 枚举名或None
        """
        for e in enum:
            if e.value == value:
                return e.name
        return None

    @staticmethod
    def get_enum_item(enum, value):
        """
        根据Enum的value查询name
        :param enum: 枚举
        :param value: 枚举值
        :return: 枚举项
        """
        for e in enum:
            if e.value == value:
                return e
        return None

    @staticmethod
    def get_dictenum_key(dictenum, value):
        """
        根据Enum dict的value查询key
        :param dictenum: 枚举字典
        :param value: 枚举类（字典值）的值
        :return: 字典键或None
        """
        for k, v in dictenum.items():
            if v.value == value:
                return k
        return None
