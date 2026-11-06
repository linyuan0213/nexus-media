from typing import Any

import cn2an

from app.domain.mediatypes import MediaType
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.security import generate_password_hash
from app.media import meta_info
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.utils import ExceptionUtils, IpUtils, StringUtils
from app.utils.config_tools import get_proxies
from version import APP_VERSION


class WebUtils:
    def __init__(
        self,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._metadata_gateway = metadata_gateway

        global _default_web_utils
        if _default_web_utils is None:
            _default_web_utils = self

    @staticmethod
    def get_location(ip):
        """
        根据IP址查询真实地址
        """
        if not IpUtils.is_ipv4(ip):
            return ""
        url = (
            "https://sp0.baidu.com/8aQDcjqpAAV3otqbppnN2DJv/api.php?co=&resource_id=6006&t=1529895387942&ie=utf8"
            "&oe=gbk&cb=op_aladdin_callback&format=json&tn=baidu&"
            f"cb=jQuery110203920624944751099_1529894588086&_=1529894588088&query={ip}"
        )
        try:
            r = HttpClient().get(url)
            html = r.content.decode("gbk")
            c1 = html.split('location":"')[1]
            c2 = c1.split('","')[0]
            return c2
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return ""

    @staticmethod
    def get_current_version():
        """
        获取当前版本号
        """
        return f"{APP_VERSION}"

    @staticmethod
    def get_latest_version():
        """
        获取最新版本号
        """
        try:
            proxies = get_proxies()
            proxy_url = proxies.get("http") if proxies else None
            version_res = HttpClient(config=HttpClientConfig(proxy_url=proxy_url)).get(
                "https://api.github.com/repos/linyuan0213/nexus-media/releases/latest"
            )
            commit_res = HttpClient(config=HttpClientConfig(proxy_url=proxy_url)).get(
                "https://api.github.com/repos/linyuan0213/nexus-media/commits/master"
            )
            ver_json = version_res.json()
            commit_json = commit_res.json()
            version = f"{ver_json['tag_name']} {commit_json['sha'][:7]}"
            url = ver_json["html_url"]
            return version, url, True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        return None, None, False

    def _lookup_record(self, provider: str, external_id: str, media_type) -> dict[str, Any] | None:
        if self._metadata_gateway is None:
            return None
        try:
            return self._metadata_gateway.lookup(
                provider,
                external_id,
                context=MetadataContext(
                    purpose="legacy_ref",
                    allow_private=True,
                    content_profile="default",
                ),
                media_type=media_type,
            )
        except Exception:  # noqa: BLE001 - 旧入口失败返回空，由调用方兜底
            return None

    @staticmethod
    def _media_info_from_record(record: dict[str, Any], provider: str, external_id: str, media_type):
        title = str(record.get("title") or "").strip()
        if not title:
            return None
        resolved_type = MediaType.from_string(str(record.get("media_type") or ""))
        if resolved_type == MediaType.UNKNOWN:
            resolved_type = media_type or (MediaType.TV if provider == "bangumi" else MediaType.MOVIE)
        info = meta_info(title=title, mtype=resolved_type)
        info.title = title
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in title)
        info.cn_name = title if has_cjk else None
        info.en_name = None if has_cjk else title
        info.original_title = str(record.get("original_title") or title)
        info.year = str(record.get("year") or "")
        info.type = resolved_type
        info.overview = str(record.get("overview") or "")
        info.anchor_provider = provider
        info.anchor_external_id = str(external_id)
        info.content_profile = str(record.get("content_profile") or ("anime" if provider == "bangumi" else "default"))
        info.tmdb_id = str(external_id) if provider == "tmdb" else ""
        if provider == "douban":
            info.douban_id = str(external_id)
        ratings = record.get("ratings") or {}
        value = ratings.get("douban") or ratings.get("bangumi")
        if isinstance(value, (int, float)):
            info.vote_average = float(value)
        seasons = record.get("seasons") or []
        if seasons and isinstance(seasons[0], dict):
            info.total_episodes = int(seasons[0].get("episode_count") or 0)
        extra = record.get("extra") or {}
        if not info.total_episodes:
            for key in ("episodes_count", "total_episodes", "douban.episodes_count"):
                value = extra.get(key) or record.get(key)
                if str(value or "").isdigit():
                    info.total_episodes = int(str(value))
                    break
        if resolved_type in (MediaType.TV, MediaType.ANIME) and not info.begin_season:
            info.begin_season = 1
        images = record.get("images") or {}
        posters = images.get("poster") or []
        poster = posters[0].get("url") if posters and isinstance(posters[0], dict) else ""
        if poster:
            info.poster_path = str(poster)
            info.backdrop_path = str(poster)
        return info

    def get_mediainfo_from_id(self, mtype, mediaid, wait=False):
        """
        根据TMDB/豆瓣/BANGUMI获取媒体信息；非 TMDB 详情统一走元数据网关。
        """
        if not mediaid:
            return None
        raw_id = str(mediaid)
        if raw_id.startswith("DB:"):
            douban_id = raw_id[3:]
            record = self._lookup_record("douban", douban_id, mtype)
            return self._media_info_from_record(record, "douban", douban_id, mtype) if record else None
        if raw_id.startswith("BG:"):
            bangumi_id = raw_id[3:]
            record = self._lookup_record("bangumi", bangumi_id, mtype or MediaType.TV)
            if not record:
                return None
            return self._media_info_from_record(record, "bangumi", bangumi_id, mtype or MediaType.TV)
        if ":" in raw_id:
            provider_key, external_id = raw_id.split(":", 1)
            provider_key = provider_key.strip().lower()
            if provider_key not in ("db", "bg", "tmdb") and external_id:
                record = self._lookup_record(provider_key, external_id, mtype)
                if record and str(record.get("title") or "").strip():
                    return self._media_info_from_record(record, provider_key, external_id, mtype)
        # TMDB 兼容路径统一经网关
        if self._metadata_gateway is None:
            return None
        info = self._metadata_gateway.details("tmdb", mediaid, media_type=mtype, append_to_response="all")
        if not info:
            return None
        title = str(info.get("title") if mtype == MediaType.MOVIE else info.get("name") or "")
        media_info = meta_info(title=title)
        media_info.set_provider_data(info)
        return media_info

    def search_media_infos(self, keyword, source=None, page=1):
        """
        搜索TMDB或豆瓣词条
        :param: keyword 关键字
        :param: source 渠道 tmdb/douban，为空时同时搜索两者
        :param: season 季号
        :param: episode 集号
        """
        if not keyword:
            return []
        result: Any = StringUtils.get_keyword_from_string(keyword)
        if not result:
            return []
        mtype, key_word, season_num, episode_num, _, content = result

        def _search_tmdb():
            mi = meta_info(title=content)
            if self._metadata_gateway is None:
                return []
            tmdbinfos = self._metadata_gateway.search_page(
                mi.get_name(),
                provider="tmdb",
                media_type=mtype,
                year=mi.year,
                page=page,
            )
            results = []
            for tmdbinfo in tmdbinfos:
                tmp_info = meta_info(title=keyword)
                tmp_info.set_provider_data(tmdbinfo)
                if tmp_info.type == MediaType.MOVIE and (season_num or episode_num):
                    continue
                if tmp_info.begin_season:
                    tmp_info.title = "{} 第{}季".format(tmp_info.title, cn2an.an2cn(mi.begin_season or 0, mode="low"))
                if tmp_info.begin_episode:
                    tmp_info.title = f"{tmp_info.title} 第{mi.begin_episode}集"
                results.append(tmp_info)
            return results

        def _search_douban():
            if self._metadata_gateway is None:
                return []
            try:
                hits = self._metadata_gateway.search(
                    query=key_word,
                    context=MetadataContext(purpose="legacy_search", allow_private=True),
                    provider="douban",
                    media_type=mtype,
                    content_profile="default",
                    limit=max(page * 20, 20),
                )
            except Exception:  # noqa: BLE001 - 豆瓣搜索失败只影响该来源
                return []
            results = []
            for hit in hits[(page - 1) * 20 : page * 20]:
                ref = hit.get("ref") or {}
                external_id = str(ref.get("external_id") or hit.get("external_id") or "")
                if not external_id:
                    continue
                title = str(hit.get("title") or "").strip()
                if not title:
                    continue
                hit_type = MediaType.from_string(str(hit.get("media_type") or ""))
                info = meta_info(title=title, mtype=hit_type if hit_type != MediaType.UNKNOWN else mtype)
                info.title = title
                info.cn_name = title
                info.year = str(hit.get("year") or "")
                info.anchor_provider = "douban"
                info.anchor_external_id = external_id
                info.douban_id = external_id
                info.poster_path = str(hit.get("poster") or "")
                results.append(info)
            return results

        if source == "tmdb":
            medias = _search_tmdb()
        elif source == "douban":
            medias = _search_douban()
        else:
            tmdb_medias = _search_tmdb()
            douban_medias = _search_douban()
            seen = set()
            medias = []
            for media in tmdb_medias + douban_medias:
                key = (
                    str(media.title or "").lower().strip(),
                    str(media.year or ""),
                    str(media.type.value if media.type else ""),
                )
                if key not in seen:
                    seen.add(key)
                    medias.append(media)
        return medias


# 与框架无关的 Action 工具函数（从 web/core/action_utils.py 迁移）


def mediainfo_dict(media_info):
    """将 MediaInfo 对象转为字典"""
    if not media_info:
        return {}
    tmdb_id = media_info.tmdb_id
    tmdb_link = media_info.get_detail_url()
    tmdb_se_link = ""
    if tmdb_id and media_info.get_season_string():
        tmdb_se_link = f"{tmdb_link}/season/{media_info.get_season_seq()}"
        if media_info.get_episode_string():
            tmdb_se_link = f"{tmdb_se_link}/episode/{media_info.get_episode_seq()}"
    return {
        "type": media_info.type.value if media_info.type else "",
        "name": media_info.get_name(),
        "title": media_info.title,
        "year": media_info.year,
        "season": media_info.get_season_string(),
        "episode": media_info.get_episode_string(),
        "tmdbid": tmdb_id,
        "imdbid": media_info.imdb_id,
        "overview": media_info.overview,
        "tmdb_link": tmdb_link,
        "tmdb_se_link": tmdb_se_link,
        "poster_path": media_info.get_poster_image(),
        "backdrop_path": media_info.get_backdrop_image(),
        "vote_average": media_info.vote_average,
        "cn_name": media_info.cn_name,
        "en_name": media_info.en_name,
        "douban_id": media_info.douban_id,
        "org_string": media_info.org_string,
        "rev_string": media_info.rev_string,
        "ignored_words": media_info.ignored_words or [],
        "replaced_words": media_info.replaced_words or [],
        "offset_words": media_info.offset_words or [],
        "resource_type": media_info.resource_type,
        "resource_effect": media_info.resource_effect,
        "resource_pix": media_info.resource_pix,
        "resource_team": media_info.resource_team,
        "video_encode": media_info.video_encode,
        "audio_encode": media_info.audio_encode,
        "category": media_info.category,
        "customization": media_info.customization,
        "part": media_info.part,
    }


def set_config_value(cfg, cfg_key, cfg_value):
    """根据Key设置配置值"""
    if cfg_key == "app.login_password":
        if cfg_value and not cfg_value.startswith("[hash]"):
            cfg["app"]["login_password"] = f"[hash]{generate_password_hash(cfg_value)}"
        else:
            cfg["app"]["login_password"] = cfg_value or "password"
        return cfg
    if cfg_key == "app.proxies":
        if cfg_value:
            if not cfg_value.startswith("http") and not cfg_value.startswith("sock"):
                cfg["app"]["proxies"] = {"https": f"http://{cfg_value}", "http": f"http://{cfg_value}"}
            else:
                cfg["app"]["proxies"] = {"https": f"{cfg_value}", "http": f"{cfg_value}"}
        else:
            cfg["app"]["proxies"] = {"https": None, "http": None}
        return cfg
    keys = cfg_key.split(".")
    if keys:
        if len(keys) == 1:
            cfg[keys[0]] = cfg_value
        elif len(keys) == 2:
            if not cfg.get(keys[0]):
                cfg[keys[0]] = {}
            cfg[keys[0]][keys[1]] = cfg_value
        elif len(keys) == 3:
            if cfg.get(keys[0]):
                if not cfg[keys[0]].get(keys[1]) or isinstance(cfg[keys[0]][keys[1]], str):
                    cfg[keys[0]][keys[1]] = {}
                cfg[keys[0]][keys[1]][keys[2]] = cfg_value
            else:
                cfg[keys[0]] = {}
                cfg[keys[0]][keys[1]] = {}
                cfg[keys[0]][keys[1]][keys[2]] = cfg_value
        else:
            # 4+ 层嵌套键（如 agent.providers.deepseek.model）
            d = cfg
            for key in keys[:-1]:
                if key not in d or not isinstance(d[key], dict):
                    d[key] = {}
                d = d[key]
            d[keys[-1]] = cfg_value
    return cfg


def set_config_directory(cfg, oper, cfg_key, cfg_value, update_value=None):
    """更新目录数据"""

    def remove_sync_path(obj, key):
        if not isinstance(obj, list):
            return []
        ret_obj = []
        for item in obj:
            if item.split("@")[0].replace("\\", "/") != key.split("@")[0].replace("\\", "/"):
                ret_obj.append(item)
        return ret_obj

    keys = cfg_key.split(".")
    if keys:
        if len(keys) == 1:
            if cfg.get(keys[0]):
                if not isinstance(cfg[keys[0]], list):
                    cfg[keys[0]] = [cfg[keys[0]]]
                if oper == "add":
                    cfg[keys[0]].append(cfg_value)
                elif oper == "sub":
                    cfg[keys[0]].remove(cfg_value)
                    if not cfg[keys[0]]:
                        cfg[keys[0]] = None
                elif oper == "set":
                    cfg[keys[0]].remove(cfg_value)
                    if update_value:
                        cfg[keys[0]].append(update_value)
            else:
                cfg[keys[0]] = cfg_value
        elif len(keys) == 2:
            if cfg.get(keys[0]):
                if not cfg[keys[0]].get(keys[1]):
                    cfg[keys[0]][keys[1]] = []
                if not isinstance(cfg[keys[0]][keys[1]], list):
                    cfg[keys[0]][keys[1]] = [cfg[keys[0]][keys[1]]]
                if oper == "add":
                    cfg[keys[0]][keys[1]].append(cfg_value.replace("\\", "/"))
                elif oper == "sub":
                    cfg[keys[0]][keys[1]] = remove_sync_path(cfg[keys[0]][keys[1]], cfg_value)
                    if not cfg[keys[0]][keys[1]]:
                        cfg[keys[0]][keys[1]] = None
                elif oper == "set":
                    cfg[keys[0]][keys[1]] = remove_sync_path(cfg[keys[0]][keys[1]], cfg_value)
                    if update_value:
                        cfg[keys[0]][keys[1]].append(update_value.replace("\\", "/"))
            else:
                cfg[keys[0]] = {}
                cfg[keys[0]][keys[1]] = cfg_value.replace("\\", "/")
    return cfg


# 默认实例（向后兼容）
_default_web_utils: WebUtils | None = None


def _get_default_web_utils() -> WebUtils:
    if _default_web_utils is None:
        raise RuntimeError("WebUtils default instance is not initialized")
    return _default_web_utils


# 向后兼容的模块级函数
def get_mediainfo_from_id(mtype, mediaid, wait=False):
    return _get_default_web_utils().get_mediainfo_from_id(mtype, mediaid, wait)


def search_media_infos(keyword, source=None, page=1):
    return _get_default_web_utils().search_media_infos(keyword, source, page)
