import json
import re

from app.media.models import MediaInfo
from app.mediaserver import MediaServer
from app.schemas.media import MediaSearchResultDTO
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils import StringUtils
from app.utils.media_utils import check_media_exists


class SearchResultService:
    """
    搜索结果分组业务服务
    """

    def __init__(self, media_server: MediaServer | None = None, subscribe: Subscribe | None = None):
        self._media_server = media_server or MediaServer()
        self._subscribe = subscribe or Subscribe()

    def group_search_results(self, search_results: list) -> MediaSearchResultDTO:
        """
        对搜索结果按标题、季集、分辨率等维度分组
        """
        search_results_dict = {}
        total = len(search_results)

        for item in search_results:
            restype, respix, reseffect, video_encode = self._parse_res_type(item.RES_TYPE)
            group_key = re.sub(r"[-.\s@|]", "", f"{respix}_{restype}").lower()
            group_info = {"respix": respix, "restype": restype}
            unique_key = re.sub(
                r"[-.\s@|]", "", f"{respix}_{restype}_{video_encode}_{reseffect}_{item.SIZE}_{item.OTHERINFO}"
            ).lower()
            unique_info = {
                "video_encode": video_encode,
                "size": StringUtils.str_filesize(item.SIZE),
                "reseffect": reseffect,
                "releasegroup": item.OTHERINFO,
            }
            title_string = f"{item.TITLE}"
            if item.YEAR:
                title_string = f"{title_string} ({item.YEAR})"
            mtype = item.TYPE or ""
            SE_key = item.ES_STRING if item.ES_STRING and mtype != "MOV" else "MOV"
            media_type = {"MOV": "电影", "TV": "电视剧", "ANI": "动漫"}.get(mtype)
            labels = [
                label
                for label in str(item.NOTE).split("|")
                if label in ["官方", "官组", "中字", "国语", "粤语", "国配", "特效", "特效字幕"]
            ]
            torrent_item = {
                "id": item.ID,
                "seeders": item.SEEDERS,
                "enclosure": item.ENCLOSURE,
                "site": item.SITE,
                "torrent_name": item.TORRENT_NAME,
                "description": item.DESCRIPTION,
                "pageurl": item.PAGEURL,
                "uploadvalue": item.UPLOAD_VOLUME_FACTOR,
                "downloadvalue": item.DOWNLOAD_VOLUME_FACTOR,
                "size": StringUtils.str_filesize(item.SIZE),
                "respix": respix,
                "restype": restype,
                "reseffect": reseffect,
                "releasegroup": item.OTHERINFO,
                "video_encode": video_encode,
                "labels": labels,
            }
            free_item = {
                "value": f"{item.UPLOAD_VOLUME_FACTOR} {item.DOWNLOAD_VOLUME_FACTOR}",
                "name": MediaInfo.get_free_string(item.UPLOAD_VOLUME_FACTOR, item.DOWNLOAD_VOLUME_FACTOR),
            }
            releasegroup = item.OTHERINFO if item.OTHERINFO is not None else "未知"
            filter_season = SE_key.split()[0] if SE_key and SE_key not in ["MOV", "TV"] else None

            if search_results_dict.get(title_string):
                self._merge_into_existing(
                    search_results_dict,
                    title_string,
                    SE_key,
                    group_key,
                    unique_key,
                    torrent_item,
                    group_info,
                    unique_info,
                    free_item,
                    releasegroup,
                    item.SITE,
                    video_encode,
                    filter_season,
                )
            else:
                fav, rssid = 0, None
                if item.TMDBID:
                    fav, rssid, _ = check_media_exists(
                        media_server=self._media_server,
                        subscribe=self._subscribe,
                        mtype=mtype,
                        title=item.TITLE,
                        year=item.YEAR,
                        mediaid=item.TMDBID,
                    )
                poster_url = item.POSTER
                try:
                    from app.helper.image_proxy_helper import ImageProxyHelper

                    poster_url = ImageProxyHelper.get_proxy_image_url(item.POSTER, use_proxy=True)
                except Exception:
                    pass
                search_results_dict[title_string] = {
                    "key": item.ID,
                    "title": item.TITLE,
                    "year": item.YEAR,
                    "type_key": mtype,
                    "image": poster_url,
                    "type": media_type,
                    "vote": item.VOTE,
                    "tmdbid": item.TMDBID,
                    "backdrop": poster_url,
                    "poster": poster_url,
                    "overview": item.OVERVIEW,
                    "fav": fav,
                    "rssid": rssid,
                    "torrent_dict": {
                        SE_key: {
                            group_key: {
                                "group_info": group_info,
                                "group_total": 1,
                                "group_torrents": {
                                    unique_key: {"unique_info": unique_info, "torrent_list": [torrent_item]}
                                },
                            }
                        }
                    },
                    "filter": {
                        "site": [item.SITE],
                        "free": [free_item],
                        "releasegroup": [releasegroup],
                        "video": [video_encode] if video_encode else [],
                        "season": [filter_season] if filter_season else [],
                    },
                }

        for _title, item in search_results_dict.items():
            item["filter"]["season"].sort(reverse=True)
            item["filter"]["releasegroup"] = sorted(item["filter"]["releasegroup"], key=lambda x: (x == "未知", x))
            item["torrent_dict"] = sorted(item["torrent_dict"].items(), key=self._se_sort, reverse=True)
        return MediaSearchResultDTO(total=total, result=search_results_dict)

    @staticmethod
    def _parse_res_type(res_type_str):
        """解析资源类型"""
        if res_type_str:
            try:
                res_mix = json.loads(res_type_str)
            except Exception:
                return "", "", "", ""
            return (
                res_mix.get("restype") or "",
                res_mix.get("respix") or "",
                res_mix.get("reseffect") or "",
                res_mix.get("video_encode") or "",
            )
        return "", "", "", ""

    @staticmethod
    def _merge_into_existing(
        search_results_dict,
        title_string,
        se_key,
        group_key,
        unique_key,
        torrent_item,
        group_info,
        unique_info,
        free_item,
        releasegroup,
        site,
        video_encode,
        filter_season,
    ):
        """将新结果合并到已有标题分组中"""
        result_item = search_results_dict[title_string]
        torrent_dict = result_item.get("torrent_dict")
        se_dict = torrent_dict.get(se_key)
        if se_dict:
            group = se_dict.get(group_key)
            if group:
                unique = group.get("group_torrents").get(unique_key)
                if unique:
                    unique["torrent_list"].append(torrent_item)
                    group["group_total"] += 1
                else:
                    group["group_total"] += 1
                    group.get("group_torrents")[unique_key] = {
                        "unique_info": unique_info,
                        "torrent_list": [torrent_item],
                    }
            else:
                se_dict[group_key] = {
                    "group_info": group_info,
                    "group_total": 1,
                    "group_torrents": {unique_key: {"unique_info": unique_info, "torrent_list": [torrent_item]}},
                }
        else:
            torrent_dict[se_key] = {
                group_key: {
                    "group_info": group_info,
                    "group_total": 1,
                    "group_torrents": {unique_key: {"unique_info": unique_info, "torrent_list": [torrent_item]}},
                }
            }
        torrent_filter = dict(result_item.get("filter"))
        if free_item not in torrent_filter.get("free"):
            torrent_filter["free"].append(free_item)
        if releasegroup not in torrent_filter.get("releasegroup"):
            torrent_filter["releasegroup"].append(releasegroup)
        if site not in torrent_filter.get("site"):
            torrent_filter["site"].append(site)
        if video_encode and video_encode not in torrent_filter.get("video"):
            torrent_filter["video"].append(video_encode)
        if filter_season and filter_season not in torrent_filter.get("season"):
            torrent_filter["season"].append(filter_season)

    @staticmethod
    def _se_sort(k):
        k = re.sub(r" +|(?<=s\d)\D*?(?=e)|(?<=s\d\d)\D*?(?=e)", " ", k[0], flags=re.I).split()
        return (k[0], k[1]) if len(k) > 1 else ("Z" + k[0], "ZZZ")
