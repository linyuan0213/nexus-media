"""
媒体工具函数

纯逻辑、无状态，不依赖服务层。
"""

from app.domain.mediatypes import MediaType


def _subscribe_id(subscribe, mtype, title: str, year, tmdbid):
    """查询进行中的订阅 ID（回退：带年份/TMDB -> 原始标题且忽略年份）."""
    for cand_title, cand_year, cand_tmdbid in (
        (title, year, tmdbid),
        (str(title or "").split(" (")[0].strip(), None, None),
    ):
        rssid = subscribe.get_subscribe_id(mtype=mtype, title=cand_title, year=cand_year, tmdbid=cand_tmdbid)
        if rssid:
            return rssid
    return None


def check_media_exists(media_server, subscribe, mtype, title, year, mediaid=None):
    """判断媒体是否存在并返回相关信息 (fav, rssid, extra)

    参数：
        media_server: MediaServer 实例，用于检查媒体库是否已入库
        subscribe: SubscribeService 实例，用于查询是否已订阅

    返回：
        (fav: str, rssid: str, extra: str)
        - fav: "1"=订阅中, "2"=已入库(含订阅完成), ""=无
    """
    if not mtype or not title:
        return False, None, ""
    subscribe_mtype = MediaType.MOVIE if str(mtype).lower() == "movie" else MediaType.TV
    media_title = f"{title} ({year})" if (str(mtype).lower() != "movie" and year) else title
    subscribe_mediaid = mediaid
    if mediaid and (str(mediaid).startswith("DB:") or str(mediaid).startswith("BGM:")):
        subscribe_mediaid = None

    # 1) 订阅中优先：存在进行中的订阅即显示"已订阅"，不再被库存在状态覆盖
    rssid = _subscribe_id(subscribe, subscribe_mtype, media_title, year, subscribe_mediaid)
    if not rssid and subscribe_mediaid is not None:
        # TMDB 未命中时忽略 tmdbid 再按标题查一次
        rssid = _subscribe_id(subscribe, subscribe_mtype, media_title, year, None)
    if rssid:
        if "\n" in str(rssid):
            rssid = str(rssid).split("\n")[1]
        return "1", rssid, ""

    # 1.5) TMDB 别名匹配：BGM/豆瓣名称与订阅名不同（如「画完这个再去死」=「描绘直至生命尽头」）
    get_by_alias = getattr(subscribe, "get_subscribe_id_by_alias", None)
    if get_by_alias is not None:
        try:
            alias_rssid = get_by_alias(title=str(title).strip(), mtype=subscribe_mtype)
        except Exception:  # noqa: BLE001
            alias_rssid = None
        if alias_rssid:
            return "1", alias_rssid, ""

    # 2) 已入库：媒体服务器登记薄，未命中时回退实时查询
    favor = media_server.check_item_exists(mtype=mtype, title=media_title, year=year, tmdbid=mediaid)
    if not favor:
        live_check = getattr(media_server, "check_library_present", None)
        if live_check is not None:
            try:
                favor = live_check(mtype=subscribe_mtype, title=title, year=year, tmdbid=mediaid)
            except Exception:  # noqa: BLE001
                favor = False
    if favor:
        return "2", "", ""

    # 3) 订阅已完成（已从订阅表移除、进入历史）→ 视作已入库
    get_history_id = getattr(subscribe, "get_history_id", None)
    if get_history_id is not None:
        try:
            finished_id = get_history_id(
                mtype=subscribe_mtype, title=str(title).strip(), year=year, tmdbid=subscribe_mediaid
            )
        except Exception:  # noqa: BLE001
            finished_id = None
        if finished_id:
            return "2", str(finished_id), ""

    return "", "", ""
