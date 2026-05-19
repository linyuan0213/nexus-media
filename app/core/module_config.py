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

    # 媒体服务器
    MEDIASERVER_CONF = {
        "emby": {
            "name": "Emby",
            "img_url": "../static/img/mediaserver/emby.png",
            "background": "bg-green",
            "test_command": "app.mediaserver.client.emby|Emby",
            "config": {
                "enabled": {
                    "id": "emby.enabled",
                    "required": False,
                    "title": "启用",
                    "tooltip": "启用该媒体服务器",
                    "type": "switch",
                },
                "is_default": {
                    "id": "emby.is_default",
                    "required": False,
                    "title": "默认",
                    "tooltip": "设置为默认使用的媒体服务器，同一时间只能有一个默认",
                    "type": "switch",
                },
                "host": {
                    "id": "emby.host",
                    "required": True,
                    "title": "服务器地址",
                    "tooltip": "配置IP地址和端口，如为https则需要增加https://前缀",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:8096",
                },
                "api_key": {
                    "id": "emby.api_key",
                    "required": True,
                    "title": "Api Key",
                    "tooltip": "在Emby设置->高级->API密钥处生成，注意不要复制到了应用名称",
                    "type": "text",
                    "placeholder": "",
                },
                "play_host": {
                    "id": "emby.play_host",
                    "required": False,
                    "title": "媒体播放地址",
                    "tooltip": "配置播放设备的访问地址，用于媒体详情页跳转播放页面；如为https则需要增加https://前缀，留空则默认与服务器地址一致",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:8096",
                },
            },
        },
        "jellyfin": {
            "name": "Jellyfin",
            "img_url": "../static/img/mediaserver/jellyfin.jpg",
            "background": "bg-purple",
            "test_command": "app.mediaserver.client.jellyfin|Jellyfin",
            "config": {
                "enabled": {
                    "id": "jellyfin.enabled",
                    "required": False,
                    "title": "启用",
                    "tooltip": "启用该媒体服务器",
                    "type": "switch",
                },
                "is_default": {
                    "id": "jellyfin.is_default",
                    "required": False,
                    "title": "默认",
                    "tooltip": "设置为默认使用的媒体服务器，同一时间只能有一个默认",
                    "type": "switch",
                },
                "host": {
                    "id": "jellyfin.host",
                    "required": True,
                    "title": "服务器地址",
                    "tooltip": "配置IP地址和端口，如为https则需要增加https://前缀",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:8096",
                },
                "api_key": {
                    "id": "jellyfin.api_key",
                    "required": True,
                    "title": "Api Key",
                    "tooltip": "在Jellyfin设置->高级->API密钥处生成",
                    "type": "text",
                    "placeholder": "",
                },
                "play_host": {
                    "id": "jellyfin.play_host",
                    "required": False,
                    "title": "媒体播放地址",
                    "tooltip": "配置播放设备的访问地址，用于媒体详情页跳转播放页面；如为https则需要增加https://前缀，留空则默认与服务器地址一致",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:8096",
                },
            },
        },
        "plex": {
            "name": "Plex",
            "img_url": "../static/img/mediaserver/plex.png",
            "background": "bg-yellow",
            "test_command": "app.mediaserver.client.plex|Plex",
            "config": {
                "enabled": {
                    "id": "plex.enabled",
                    "required": False,
                    "title": "启用",
                    "tooltip": "启用该媒体服务器",
                    "type": "switch",
                },
                "is_default": {
                    "id": "plex.is_default",
                    "required": False,
                    "title": "默认",
                    "tooltip": "设置为默认使用的媒体服务器，同一时间只能有一个默认",
                    "type": "switch",
                },
                "host": {
                    "id": "plex.host",
                    "required": True,
                    "title": "服务器地址",
                    "tooltip": "配置IP地址和端口，如为https则需要增加https://前缀",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:32400",
                },
                "token": {
                    "id": "plex.token",
                    "required": False,
                    "title": "X-Plex-Token",
                    "tooltip": "Plex网页Url中的X-Plex-Token，通过浏览器F12->网络从请求URL中获取，如填写将优先使用；Token与服务器名称、用户名及密码 二选一，推荐使用Token，连接速度更快",
                    "type": "text",
                    "placeholder": "X-Plex-Token与其它认证信息二选一",
                },
                "servername": {
                    "id": "plex.servername",
                    "required": False,
                    "title": "服务器名称",
                    "tooltip": "配置Plex设置->左侧下拉框中看到的服务器名称；如填写了Token则无需填写服务器名称、用户名及密码",
                    "type": "text",
                    "placeholder": "",
                },
                "username": {
                    "id": "plex.username",
                    "required": False,
                    "title": "用户名",
                    "type": "text",
                    "placeholder": "",
                },
                "password": {
                    "id": "plex.password",
                    "required": False,
                    "title": "密码",
                    "type": "password",
                    "placeholder": "",
                },
                "play_host": {
                    "id": "plex.play_host",
                    "required": False,
                    "title": "媒体播放地址",
                    "tooltip": "配置播放设备的访问地址，用于媒体详情页跳转播放页面；如为https则需要增加https://前缀，留空则默认与服务器地址一致",
                    "type": "text",
                    "placeholder": "https://app.plex.tv",
                },
            },
        },
        "fnos": {
            "name": "FnOS",
            "img_url": "../static/img/mediaserver/fnos.png",
            "background": "bg-blue",
            "test_command": "app.mediaserver.client.fnos|FnOS",
            "config": {
                "enabled": {
                    "id": "fnos.enabled",
                    "required": False,
                    "title": "启用",
                    "tooltip": "启用该媒体服务器",
                    "type": "switch",
                },
                "is_default": {
                    "id": "fnos.is_default",
                    "required": False,
                    "title": "默认",
                    "tooltip": "设置为默认使用的媒体服务器，同一时间只能有一个默认",
                    "type": "switch",
                },
                "host": {
                    "id": "fnos.host",
                    "required": True,
                    "title": "服务器地址",
                    "tooltip": "配置IP地址和端口，如为https则需要增加https://前缀",
                    "type": "text",
                    "placeholder": "http://127.0.0.1:5666",
                },
                "username": {
                    "id": "fnos.username",
                    "required": False,
                    "title": "用户名",
                    "type": "text",
                    "placeholder": "",
                },
                "password": {
                    "id": "fnos.password",
                    "required": False,
                    "title": "密码",
                    "type": "password",
                    "placeholder": "",
                },
                "play_host": {
                    "id": "fnos.play_host",
                    "required": False,
                    "title": "媒体播放地址",
                    "tooltip": "配置播放设备的访问地址，用于媒体详情页跳转播放页面；如为https则需要增加https://前缀，留空则默认与服务器地址一致",
                    "type": "text",
                    "placeholder": "https://app.fnos.tv",
                },
            },
        },
    }

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
