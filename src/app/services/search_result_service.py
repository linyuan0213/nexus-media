import re

import log
from app.domain.episode_utils import infer_episode_key
from app.domain.media_types import media_type_registry
from app.domain.media_utils import check_media_exists
from app.domain.mediatypes import MediaType
from app.infrastructure.image_proxy import ImageProxy
from app.media import meta_info
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.media.models import MediaInfo
from app.mediaserver.media_server import MediaServer
from app.schemas.media import MediaSearchResultDTO
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils


class SearchResultService:
    """
    搜索结果分组业务服务
    """

    def __init__(
        self,
        media_server: MediaServer,
        subscribe: Subscribe,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._media_server = media_server
        self._subscribe = subscribe
        self._metadata_gateway = metadata_gateway

    def _resolve_vote(self, item, rating_cache: dict[tuple[str, str, str], str]) -> str:
        vote = str(getattr(item, "VOTE", "") or "").strip()
        if vote and vote not in {"0", "0.0"}:
            return vote
        provider = str(getattr(item, "ANCHOR_PROVIDER", "") or "")
        external_id = str(getattr(item, "ANCHOR_EXTERNAL_ID", "") or "")
        if not provider or not external_id or self._metadata_gateway is None:
            return vote or "0"
        media_type = MediaType.from_string(str(getattr(item, "TYPE", "") or ""))
        cache_key = (provider, external_id, media_type.value)
        if cache_key in rating_cache:
            return rating_cache[cache_key]
        try:
            record = (
                self._metadata_gateway.lookup(
                    provider,
                    external_id,
                    media_type=media_type,
                    context=MetadataContext(purpose="search.result", allow_private=True),
                )
                or {}
            )
            ratings = record.get("ratings") or {}
            rating = ratings.get(provider) if hasattr(ratings, "get") else None
            if rating is None and isinstance(ratings, dict) and ratings:
                rating = max(ratings.values())
            resolved = str(round(float(rating), 1)) if rating else "0"
        except Exception as exc:  # noqa: BLE001 - 评分补全失败不影响结果展示
            log.debug(f"[Search]评分补全失败 {provider}:{external_id}: {exc}")
            resolved = vote or "0"
        rating_cache[cache_key] = resolved
        return resolved

    def group_search_results(self, search_results: list) -> MediaSearchResultDTO:
        """
        对搜索结果按标题、季集、分辨率等维度分组
        """
        search_results_dict = {}
        total = len(search_results)
        rating_cache: dict[tuple[str, str, str], str] = {}

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
                "releasegroup": item.OTHERINFO or "未知",
            }
            title_string = f"{item.TITLE}"
            mtype = item.TYPE or ""
            parsed_mtype = MediaType.from_string(mtype)
            media_type = mtype or MediaType.UNKNOWN.value
            # 兼容修复前落库的旧结果：TYPE/ES_STRING 为空时从种子名补解析，
            # 避免旧搜索会话把动漫/剧集全部归到 movie。
            if (not item.TYPE or not item.ES_STRING) and item.TORRENT_NAME:
                parsed = meta_info(title=item.TORRENT_NAME, subtitle=item.DESCRIPTION or "")
                if parsed is not None and not item.TYPE:
                    parsed_mtype = parsed.type or MediaType.UNKNOWN
                    media_type = parsed.type.value if parsed.type is not None else media_type
                if parsed is not None and not item.ES_STRING:
                    item.ES_STRING = parsed.get_season_episode_string() or ""
            # 剧集/动漫按标题聚合，避免同一部剧的 2025/2026 季标签拆成多张卡片；
            # 电影保留年份，用于区分同名翻拍。
            if item.YEAR and parsed_mtype == MediaType.MOVIE:
                title_string = f"{title_string} ({item.YEAR})"
            se_key = item.ES_STRING if item.ES_STRING and parsed_mtype != MediaType.MOVIE else MediaType.MOVIE.value
            if parsed_mtype != MediaType.MOVIE:
                se_key = infer_episode_key(se_key, item.TORRENT_NAME)
            if parsed_mtype != MediaType.UNKNOWN:
                media_type = parsed_mtype.value
            labels = [label.strip() for label in str(item.NOTE).split("|") if label.strip()]
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
                "releasegroup": item.OTHERINFO or "未知",
                "video_encode": video_encode,
                "labels": labels,
            }
            free_item = {
                "value": f"{item.UPLOAD_VOLUME_FACTOR} {item.DOWNLOAD_VOLUME_FACTOR}",
                "name": MediaInfo.get_free_string(item.UPLOAD_VOLUME_FACTOR, item.DOWNLOAD_VOLUME_FACTOR),
            }
            releasegroup = item.OTHERINFO if item.OTHERINFO else "未知"
            filter_season = se_key.split()[0] if se_key and se_key != MediaType.MOVIE.value else None

            if search_results_dict.get(title_string):
                self._merge_into_existing(
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
                    item.SITE,
                    video_encode,
                    filter_season,
                    respix,
                )
            else:
                anchor_provider = str(getattr(item, "ANCHOR_PROVIDER", "") or "")
                anchor_external = str(getattr(item, "ANCHOR_EXTERNAL_ID", "") or "")
                if not anchor_provider and item.TMDBID:
                    anchor_provider, anchor_external = "tmdb", str(item.TMDBID)
                fav, rssid = 0, None
                if item.TMDBID or anchor_provider:
                    fav, rssid, _ = check_media_exists(
                        media_server=self._media_server,
                        subscribe=self._subscribe,
                        mtype=mtype,
                        title=item.TITLE,
                        year=item.YEAR,
                        mediaid=item.TMDBID,
                        anchor_provider=anchor_provider or None,
                        anchor_external_id=anchor_external or None,
                    )
                poster_url = item.POSTER
                try:
                    poster_url = ImageProxy.get_proxy_image_url(item.POSTER, use_proxy=True)
                except Exception as e:  # noqa: BLE001
                    log.debug(f"[Search]忽略异常: {e}")
                search_results_dict[title_string] = {
                    "key": item.ID,
                    "title": item.TITLE,
                    "year": item.YEAR,
                    "type_key": mtype,
                    "identity_id": getattr(item, "IDENTITY_ID", None),
                    "anchor_provider": anchor_provider,
                    "anchor_external_id": anchor_external,
                    "metadata_ref": (
                        f"{anchor_provider}:{anchor_external}" if anchor_provider and anchor_external else ""
                    ),
                    "provider": anchor_provider,
                    "content_profile": getattr(item, "CONTENT_PROFILE", None) or "default",
                    "image": poster_url,
                    "type": media_type,
                    "media_type_name": media_type_registry.resolve(media_type).display_name,
                    "media_kind": media_type_registry.resolve(media_type).kind.value,
                    "vote": self._resolve_vote(item, rating_cache),
                    "tmdbid": item.TMDBID,
                    "backdrop": poster_url,
                    "poster": poster_url,
                    "overview": item.OVERVIEW,
                    "fav": fav,
                    "rssid": rssid,
                    "torrent_dict": {
                        se_key: {
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
                        "resolution": [respix] if respix else [],
                    },
                }

        for _title, item in search_results_dict.items():
            item["filter"]["season"].sort(reverse=True)
            item["filter"]["releasegroup"] = sorted(item["filter"]["releasegroup"], key=lambda x: (x == "未知", x))
            item["filter"]["resolution"] = sorted(
                item["filter"]["resolution"], key=self._resolution_weight, reverse=True
            )
            item["torrent_dict"] = sorted(item["torrent_dict"].items(), key=self._se_sort, reverse=True)
        return MediaSearchResultDTO(total=total, result=search_results_dict)

    @staticmethod
    def _parse_res_type(res_type_str):
        """解析资源类型"""
        if res_type_str:
            try:
                res_mix = JsonUtils.loads(res_type_str)
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
        resolution,
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
        # 防御旧数据无 resolution 键（浅拷贝的 dict 需 setdefault 回原对象）
        if resolution:
            res_list = result_item["filter"].setdefault("resolution", [])
            if resolution not in res_list:
                res_list.append(resolution)

    @staticmethod
    def _resolution_weight(res: str) -> int:
        """分辨率排序权重：高清在前"""
        r = (res or "").lower()
        if "8k" in r or "4320" in r:
            return 5
        if "4k" in r or "2160" in r:
            return 4
        if "1080" in r:
            return 3
        if "720" in r:
            return 2
        return 1 if r else 0

    @staticmethod
    def _se_sort(k):
        """季/集排序键：季降序（新季在前）→ 整季（无集号）优先 → 集降序（新集在前）"""
        se = k[0]
        seasons = [int(x) for x in re.findall(r"[Ss](\d+)", se)]
        season = max(seasons) if seasons else 0
        episodes = [int(x) for x in re.findall(r"[Ee](\d+)", se)]
        episode = max(episodes) if episodes else 0
        return (season, 1 if episode == 0 else 0, episode)
