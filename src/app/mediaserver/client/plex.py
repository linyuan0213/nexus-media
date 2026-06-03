import os
from functools import lru_cache
from typing import Any
from urllib.parse import quote, quote_plus

from plexapi import media
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

import log
from app.core.exceptions import InfrastructureError, MediaServerError, NetworkError
from app.mediaserver.client._base import _IMediaClient
from app.mediaserver.schema import ConfigField, MediaServerConfigSchema
from app.utils import ExceptionUtils
from app.domain.mediatypes import MediaType


class Plex(_IMediaClient):
    # 媒体服务器ID
    client_id = "plex"
    # 媒体服务器类型
    client_type = "plex"
    # 媒体服务器名称
    client_name = "Plex"
    # 配置架构
    config_schema = MediaServerConfigSchema(
        name="Plex",
        fields=[
            ConfigField(
                id="enabled",
                required=False,
                title="启用",
                type="switch",
                tooltip="启用该媒体服务器",
            ),
            ConfigField(
                id="is_default",
                required=False,
                title="默认",
                type="switch",
                tooltip="设置为默认使用的媒体服务器，同一时间只能有一个默认",
            ),
            ConfigField(
                id="host",
                required=True,
                title="服务器地址",
                type="text",
                tooltip="配置IP地址和端口，如为https则需要增加https://前缀",
                placeholder="http://127.0.0.1:32400",
            ),
            ConfigField(
                id="token",
                required=False,
                title="X-Plex-Token",
                type="text",
                tooltip="Plex网页Url中的X-Plex-Token，通过浏览器F12->网络从请求URL中获取，如填写将优先使用；Token与服务器名称、用户名及密码 二选一，推荐使用Token，连接速度更快",
            ),
            ConfigField(
                id="play_host",
                required=False,
                title="媒体播放地址",
                type="text",
                tooltip="配置播放设备的访问地址，用于媒体详情页跳转播放页面；如为https则需要增加https://前缀，留空则默认与服务器地址一致",
                placeholder="http://127.0.0.1:32400",
            ),
        ],
    )

    # 私有属性
    _client_config = {}
    _host = None
    _token = None
    _username = None
    _password = None
    _servername = None
    _plex = None
    _play_host = None
    _libraries = []

    def __init__(self, config=None):
        if config:
            self._client_config = config
        else:
            self._client_config = self.get_db_config("plex")
        self.init_config()

    def init_config(self) -> None:
        if self._client_config:
            self._host = self._client_config.get("host")
            self._token = self._client_config.get("token")
            if self._host:
                if not self._host.startswith("http"):
                    self._host = "http://" + self._host
                if not self._host.endswith("/"):
                    self._host = self._host + "/"
            self._play_host = self._client_config.get("play_host")
            if not self._play_host:
                self._play_host = self._host
            else:
                if not self._play_host.startswith("http"):
                    self._play_host = "http://" + self._play_host
                if not self._play_host.endswith("/"):
                    self._play_host = self._play_host + "/"
            if "app.plex.tv" in (self._play_host or ""):
                self._play_host = (self._play_host or "") + "desktop/"
            else:
                self._play_host = (self._play_host or "") + "web/index.html"
            self._username = self._client_config.get("username")
            self._password = self._client_config.get("password")
            self._servername = self._client_config.get("servername")
            if self._host and self._token:
                try:
                    self._plex = PlexServer(self._host, self._token)
                except (InfrastructureError, NetworkError, MediaServerError):
                    raise
                except Exception as e:  # type: ignore[unreachable]
                    ExceptionUtils.exception_traceback(e)
                    self._plex = None
                    log.error(f"[{self.client_name}]Plex服务器连接失败：{e!s}")
            elif self._username and self._password and self._servername:
                try:
                    self._plex = MyPlexAccount(self._username, self._password).resource(self._servername).connect()
                except (InfrastructureError, NetworkError, MediaServerError):
                    raise
                except Exception as e:  # type: ignore[unreachable]
                    ExceptionUtils.exception_traceback(e)
                    self._plex = None
                    log.error(f"[{self.client_name}]Plex服务器连接失败：{e!s}")

    @classmethod
    def match(cls, ctype: Any) -> bool:
        return ctype in [cls.client_id, cls.client_type, cls.client_name]

    def get_type(self) -> str:
        return self.client_type

    def get_status(self) -> bool:
        """
        测试连通性
        """
        return bool(self._plex)

    def get_user_count(self, **_kwargs: Any) -> int:
        """
        获得用户数量，Plex只能配置一个用户，固定返回1
        """
        return 1

    def get_activity_log(self, num: int) -> list:
        """
        获取Plex活动记录
        """
        if not self._plex:
            return []
        ret_array = []
        try:
            # type的含义: 1 电影 4 剧集单集 详见 plexapi/utils.py中SEARCHTYPES的定义
            # 根据最后播放时间倒序获取数据
            historys = self._plex.library.search(sort="lastViewedAt:desc", limit=num, type="1,4")
            for his in historys:
                # 过滤掉最后播放时间为空的
                if his.lastViewedAt:
                    if his.type == "episode":
                        event_title = "{} {}{} {}".format(
                            his.grandparentTitle,
                            "S" + str(his.parentIndex),
                            "E" + str(his.index),
                            his.title,
                        )
                        event_str = f"开始播放剧集 {event_title}"
                    else:
                        event_title = "{} {}".format(his.title, "(" + str(his.year) + ")")
                        event_str = f"开始播放电影 {event_title}"

                    event_type = "PL"
                    event_date = his.lastViewedAt.strftime("%Y-%m-%d %H:%M:%S")
                    activity = {"type": event_type, "event": event_str, "date": event_date}
                    ret_array.append(activity)
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as e:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(e)
            log.error(f"[{self.client_name}]连接System/ActivityLog/Entries出错：" + str(e))
            return []
        if ret_array:
            ret_array = sorted(ret_array, key=lambda x: x["date"], reverse=True)
        return ret_array

    def get_medias_count(self) -> dict:
        """
        获得电影、电视剧、动漫媒体数量
        :return: MovieCount SeriesCount SongCount
        """
        if not self._plex:
            return {}
        sections = self._plex.library.sections()
        movie_count = series_count = song_count = episode_count = 0
        for sec in sections:
            if sec.type == "movie":
                movie_count += sec.totalSize
            if sec.type == "show":
                series_count += sec.totalSize
                episode_count += sec.totalViewSize(libtype="episode")
            if sec.type == "artist":
                song_count += sec.totalSize
        return {
            "MovieCount": movie_count,
            "SeriesCount": series_count,
            "SongCount": song_count,
            "EpisodeCount": episode_count,
        }

    def get_movies(self, title: str, year: Any = None) -> Any:
        """
        根据标题和年份，检查电影是否在Plex中存在，存在则返回列表
        :param title: 标题
        :param year: 年份，为空则不过滤
        :return: 含title、year属性的字典列表
        """
        if not self._plex:
            return None
        ret_movies = []
        if year:
            movies = self._plex.library.search(title=title, year=year, libtype="movie")
        else:
            movies = self._plex.library.search(title=title, libtype="movie")
        for movie in movies:
            ret_movies.append({"title": movie.title, "year": movie.year})
        return ret_movies

    def get_tv_episodes(
        self, item_id: Any = None, title: Any = None, year: Any = None, tmdbid: Any = None, season: Any = None
    ) -> list:
        """
        根据标题、年份、季查询电视剧所有集信息
        :param item_id: Plex中的ID
        :param title: 标题
        :param year: 年份，可以为空，为空时不按年份过滤
        :param tmdbid: TMDBID
        :param season: 季号，数字
        :return: 所有集的列表
        """
        if not self._plex:
            return []
        if not item_id:
            videos = self._plex.library.search(title=title, year=year, libtype="show")
            if not videos or not videos[0]:
                return []
            episodes = videos[0].episodes()
        else:
            item = self._plex.fetchItem(item_id)
            if item is None:
                return []
            episodes = item.episodes()
        ret_tvs = []
        for episode in episodes:
            if season and episode.seasonNumber != int(season):
                continue
            ret_tvs.append({"season_num": episode.seasonNumber, "episode_num": episode.index})
        return ret_tvs

    def get_no_exists_episodes(self, meta_info: Any, season: int, total_num: int) -> Any:
        """
        根据标题、年份、季、总集数，查询Plex中缺少哪几集
        :param meta_info: 已识别的需要查询的媒体信息
        :param season: 季号，数字
        :param total_num: 该季的总集数
        :return: 该季不存在的集号列表
        """
        if not self._plex:
            return None
        # 没有季默认为和1季
        if not season:
            season = 1
        episodes = self.get_tv_episodes(title=meta_info.title, year=meta_info.year, season=season)
        exists_episodes = [episode["episode_num"] for episode in episodes]
        total_episodes = list(range(1, total_num + 1))
        return list(set(total_episodes).difference(set(exists_episodes)))

    def get_episode_image_by_id(self, item_id: Any, season_id: Any, episode_id: Any) -> Any:
        """
        根据itemid、season_id、episode_id从Plex查询图片地址
        :param item_id: 在Plex中具体的一集的ID
        :param season_id: 季,目前没有使用
        :param episode_id: 集,目前没有使用
        :return: 图片对应在TMDB中的URL
        """
        if not self._plex:
            return None
        try:
            images = self._plex.fetchItems(f"/library/metadata/{item_id}/posters", cls=media.Poster)
            for image in images:
                if image is not None and hasattr(image, "key") and image.key.startswith("http"):
                    return image.key
            return None
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as e:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(e)
            log.error(f"[{self.client_name}]获取剧集封面出错：" + str(e))
            return None

    def get_remote_image_by_id(self, item_id: Any, image_type: str) -> Any:
        """
        根据ItemId从Plex查询图片地址
        :param item_id: 在Emby中的ID
        :param image_type: 图片的类型，Poster或者Backdrop等
        :return: 图片对应在TMDB中的URL
        """
        if not self._plex:
            return None
        try:
            if image_type == "Poster":
                images = self._plex.fetchItems(f"/library/metadata/{item_id}/posters", cls=media.Poster)
            else:
                images = self._plex.fetchItems(f"/library/metadata/{item_id}/arts", cls=media.Art)
            for image in images:
                if image is not None and hasattr(image, "key") and image.key.startswith("http"):
                    return image.key
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as e:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(e)
            log.error(f"[{self.client_name}]获取封面出错：" + str(e))
        return None

    def get_local_image_by_id(self, item_id: Any, remote: bool = True) -> Any:
        """
        根据ItemId从媒体服务器查询有声书图片地址
        :param item_id: 在Emby中的ID
        :param remote: 是否远程使用
        """
        return None

    def refresh_root_library(self) -> bool:
        """
        通知Plex刷新整个媒体库
        """
        if not self._plex:
            return False
        return self._plex.library.update()

    def refresh_library_by_items(self, items: list) -> None:
        """
        按路径刷新媒体库
        """
        if not self._plex:
            return
        # _libraries可能未初始化,初始化一下
        if not self._libraries:
            try:
                self._libraries = self._plex.library.sections()
            except (InfrastructureError, NetworkError, MediaServerError):
                raise
            except Exception as err:  # type: ignore[unreachable]
                ExceptionUtils.exception_traceback(err)
        result_dict = {}
        for item in items:
            file_path = item.get("file_path")
            lib_key, path = self.__find_librarie(file_path, self._libraries)
            # 如果存在同一剧集的多集,key(path)相同会合并
            result_dict[path] = lib_key
        if "" in result_dict:
            # 如果有匹配失败的,刷新整个库
            self._plex.library.update()
        else:
            # 否则一个一个刷新
            for path, lib_key in result_dict.items():
                log.info(f"[{self.client_name}]刷新媒体库：{lib_key} : {path}")
                self._plex.query(f"/library/sections/{lib_key}/refresh?path={quote_plus(path)}")

    @staticmethod
    def __find_librarie(path, libraries):
        """
        判断这个path属于哪个媒体库
        多个媒体库配置的目录不应有重复和嵌套,
        使用os.path.commonprefix([path, location]) == location应该没问题
        """
        if path is None:
            return "", ""
        # 只要路径,不要文件名
        dir_path = os.path.dirname(path)
        try:
            for lib in libraries:
                if hasattr(lib, "locations") and lib.locations:
                    for location in lib.locations:
                        if os.path.commonprefix([dir_path, location]) == location:
                            return lib.key, dir_path
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as err:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(err)
        return "", ""

    def get_libraries(self) -> list:
        """
        获取媒体服务器所有媒体库列表
        """
        if not self._plex:
            return []
        try:
            self._libraries = self._plex.library.sections()
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as err:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(err)
            return []
        libraries = []
        for library in self._libraries:
            match library.type:
                case "movie":
                    library_type = MediaType.MOVIE.value
                    image_list_str = self.get_libraries_image(library.key, 1)
                case "show":
                    library_type = MediaType.TV.value
                    image_list_str = self.get_libraries_image(library.key, 2)
                case _:
                    continue
            libraries.append(
                {
                    "id": library.key,
                    "name": library.title,
                    "paths": library.locations,
                    "type": library_type,
                    "image_list": image_list_str,
                    "link": f"{self._play_host or self._host}#!/media/{self._plex.machineIdentifier}"
                    f"/com.plexapp.plugins.library?source={library.key}",
                }
            )
        return libraries

    @lru_cache(maxsize=10)  # noqa: B019
    def get_libraries_image(self, library_key: Any, type: int) -> str:
        """
        获取媒体服务器最近添加的媒体的图片列表
        param: library_key
        param: type type的含义: 1 电影 2 剧集 详见 plexapi/utils.py中SEARCHTYPES的定义
        """
        if not self._plex:
            return ""
        # 返回结果
        poster_urls = {}
        # 页码计数
        container_start = 0
        # 需要的总条数/每页的条数
        total_size = 4

        # 如果总数不足,接续获取下一页
        while len(poster_urls) < total_size:
            items = self._plex.fetchItems(
                f"/hubs/home/recentlyAdded?type={type}&sectionID={library_key}",
                container_size=total_size,
                container_start=container_start,
            )
            for item in items:
                if item is None:
                    continue
                if item.type == "episode":
                    # 如果是剧集的单集,则去找上级的图片
                    if item.parentThumb is not None:
                        poster_urls[item.parentThumb] = None
                else:
                    # 否则就用自己的图片
                    if item.thumb is not None:
                        poster_urls[item.thumb] = None
                if len(poster_urls) == total_size:
                    break
            if len(items) < total_size:
                break
            container_start += total_size
        if self._host is None:
            return ""
        image_list_str = ", ".join(
            [
                f"{self.get_nt_image_url(self._host.rstrip('/') + url)}?X-Plex-Token={self._token}"
                for url in list(poster_urls.keys())[:total_size]
            ]
        )
        return image_list_str

    def get_iteminfo(self, itemid: Any) -> dict:
        """
        获取单个项目详情
        """
        if not self._plex:
            return {}
        try:
            item = self._plex.fetchItem(itemid)
            if item is None:
                return {}
            ids = self.__get_ids(item.guids)
            return {"ProviderIds": {"Tmdb": ids["tmdb_id"], "Imdb": ids["imdb_id"]}}
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as err:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(err)
            return {}

    def get_play_url(self, item_id: Any) -> str:
        """
        拼装媒体播放链接
        :param item_id: 媒体的的ID
        """
        if self._plex is None:
            return ""
        return f"{self._play_host or self._host}#!/server/{self._plex.machineIdentifier}/details?key={item_id}"

    def get_items(self, parent: Any) -> Any:
        """
        获取媒体服务器所有媒体库列表
        """
        if not parent:
            yield {}
            return
        if not self._plex:
            yield {}
            return
        try:
            section = self._plex.library.sectionByID(parent)
            if section:
                for item in section.all():
                    if not item:
                        continue
                    ids = self.__get_ids(item.guids)
                    path = None
                    if item.locations:
                        path = item.locations[0]
                    yield {
                        "id": item.key,
                        "library": item.librarySectionID,
                        "type": item.type,
                        "title": item.title,
                        "originalTitle": item.originalTitle,
                        "year": item.year,
                        "tmdbid": ids["tmdb_id"],
                        "imdbid": ids["imdb_id"],
                        "tvdbid": ids["tvdb_id"],
                        "path": path,
                    }
        except (InfrastructureError, NetworkError, MediaServerError):
            raise
        except Exception as err:  # type: ignore[unreachable]
            ExceptionUtils.exception_traceback(err)
        yield {}

    @staticmethod
    def __get_ids(guids):
        guid_mapping = {"imdb://": "imdb_id", "tmdb://": "tmdb_id", "tvdb://": "tvdb_id"}
        ids = {}
        for _, varname in guid_mapping.items():
            ids[varname] = None
        for guid in guids:
            for prefix, varname in guid_mapping.items():
                if isinstance(guid, dict):
                    if guid["id"].startswith(prefix):
                        # 找到匹配的ID
                        ids[varname] = guid["id"][len(prefix) :]
                        break
                else:
                    if guid.id.startswith(prefix):
                        # 找到匹配的ID
                        ids[varname] = guid.id[len(prefix) :]
                        break
        return ids

    def get_playing_sessions(self) -> list:
        """
        获取正在播放的会话
        """
        if not self._plex:
            return []
        sessions = self._plex.sessions()
        ret_sessions = []
        for session in sessions:
            if session is None:
                continue
            bitrate = sum([m.bitrate or 0 for m in session.media])
            ret_sessions.append({"type": session.TAG, "bitrate": bitrate, "address": session.player.address})
        return ret_sessions

    def get_webhook_message(self, message: dict) -> dict:
        """
        解析Plex报文
        eventItem  字段的含义
        event      事件类型
        item_type  媒体类型 TV,MOV
        item_name  TV:琅琊榜 S1E6 剖心明志 虎口脱险
                   MOV:猪猪侠大冒险(2001)
        overview   剧情描述
        """
        event_item = {"event": message.get("event", "")}
        if message.get("Metadata"):
            if message.get("Metadata", {}).get("type") == "episode":
                event_item["item_type"] = "tv"
                event_item["item_name"] = "{} {}{} {}".format(
                    message.get("Metadata", {}).get("grandparentTitle"),
                    "S" + str(message.get("Metadata", {}).get("parentIndex")),
                    "E" + str(message.get("Metadata", {}).get("index")),
                    message.get("Metadata", {}).get("title"),
                )
                event_item["item_id"] = message.get("Metadata", {}).get("ratingKey")
                event_item["season_id"] = message.get("Metadata", {}).get("parentIndex")
                event_item["episode_id"] = message.get("Metadata", {}).get("index")

                if message.get("Metadata", {}).get("summary") and len(message.get("Metadata", {}).get("summary")) > 100:
                    event_item["overview"] = str(message.get("Metadata", {}).get("summary"))[:100] + "..."
                else:
                    event_item["overview"] = message.get("Metadata", {}).get("summary")
            else:
                event_item["item_type"] = "movie" if message.get("Metadata", {}).get("type") == "movie" else "show"
                event_item["item_name"] = "{} {}".format(
                    message.get("Metadata", {}).get("title"),
                    "(" + str(message.get("Metadata", {}).get("year")) + ")",
                )
                event_item["item_id"] = message.get("Metadata", {}).get("ratingKey")
                if len(message.get("Metadata", {}).get("summary")) > 100:
                    event_item["overview"] = str(message.get("Metadata", {}).get("summary"))[:100] + "..."
                else:
                    event_item["overview"] = message.get("Metadata", {}).get("summary")
        if event_item.get("event") == "library.new":
            event_item["play_url"] = (
                f"/open?url={quote(self.get_play_url(message.get('Metadata', {}).get('key')))}&type=plex"
            )
        player = message.get("Player")
        if player:
            event_item["ip"] = player.get("publicAddress")
            event_item["client"] = player.get("title")
            event_item["device_name"] = " "
        account = message.get("Account")
        if account:
            event_item["user_name"] = account.get("title")

        return event_item

    def get_resume(self, num: int = 12) -> list:
        """
        获取继续观看的媒体
        """
        if not self._plex:
            return []
        items = self._plex.fetchItems("/hubs/continueWatching/items", container_start=0, container_size=num)
        ret_resume = []
        for item in items:
            if item is None:
                continue
            item_type = MediaType.MOVIE.value if item.TYPE == "movie" else MediaType.TV.value
            if item_type == MediaType.MOVIE.value:
                name = item.title
            else:
                if item.parentIndex == 1:
                    name = f"{item.grandparentTitle} 第{item.index}集"
                else:
                    name = f"{item.grandparentTitle} 第{item.parentIndex}季第{item.index}集"
            link = self.get_play_url(item.key)
            image = self.get_nt_image_url(item.thumbUrl)
            ret_resume.append(
                {
                    "id": item.key,
                    "name": name,
                    "type": item_type,
                    "image": image,
                    "link": link,
                    "percent": item.viewOffset / item.duration * 100 if item.viewOffset and item.duration else 0,
                }
            )
        return ret_resume

    def get_latest(self, num: int = 20) -> list:
        """
        获取最近添加媒体
        """
        if not self._plex:
            return []
        items = self._plex.fetchItems("/library/recentlyAdded", container_start=0, container_size=num)
        ret_resume = []
        for item in items:
            if item is None:
                continue
            item_type = MediaType.MOVIE.value if item.TYPE == "movie" else MediaType.TV.value
            link = self.get_play_url(item.key)
            title = item.title if item_type == MediaType.MOVIE.value else f"{item.parentTitle} 第{item.index}季"
            image = self.get_nt_image_url(item.posterUrl)
            ret_resume.append({"id": item.key, "name": title, "type": item_type, "image": image, "link": link})
        return ret_resume
