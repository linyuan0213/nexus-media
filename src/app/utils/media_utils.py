"""
媒体工具函数

纯逻辑、无状态，不依赖服务层。
"""

from app.utils.types import MediaType


def check_media_exists(media_server, subscribe, mtype, title, year, mediaid=None):
    """判断媒体是否存在并返回相关信息 (fav, rssid, extra)

    参数：
        media_server: MediaServer 实例，用于检查媒体库是否已入库
        subscribe: SubscribeService 实例，用于查询是否已订阅

    返回：
        (fav: str, rssid: str, extra: str)
        - fav: "2"=已入库, "1"=已订阅, ""=无
    """
    if not mtype or not title:
        return False, None, ""
    if str(mtype).lower() != "movie":
        title = f"{title} ({year})" if year else title
    subscribe_mediaid = mediaid
    if mediaid and (str(mediaid).startswith("DB:") or str(mediaid).startswith("BGM:")):
        subscribe_mediaid = None
    favor = media_server.check_item_exists(mtype=mtype, title=title, year=year, tmdbid=mediaid)
    rssid = subscribe.get_subscribe_id(
        mtype=MediaType.MOVIE if str(mtype).lower() == "movie" else MediaType.TV,
        title=title,
        year=year,
        tmdbid=subscribe_mediaid,
    )
    if not rssid:
        rssid = subscribe.get_subscribe_id(
            mtype=MediaType.MOVIE if str(mtype).lower() == "movie" else MediaType.TV,
            title=title,
            year=year,
            tmdbid=None,
        )
    if not rssid:
        rssid = subscribe.get_subscribe_id(
            mtype=MediaType.MOVIE if str(mtype).lower() == "movie" else MediaType.TV,
            title=title,
            year=None,
            tmdbid=None,
        )
    if rssid:
        if str(rssid).find("\n") != -1:
            _, rssid = str(rssid).split("\n")
    else:
        rssid = ""
    fav = "2" if favor else ("1" if rssid else "")
    return fav, rssid, ""
