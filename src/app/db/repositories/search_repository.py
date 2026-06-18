"""
Search Repository
Handles search result related database operations.
"""

from sqlalchemy import and_, or_

from app.db.models import SEARCHRESULTINFO
from app.db.repositories.base_repository import BaseRepository
from app.domain.mediatypes import MediaType
from app.utils.json_utils import JsonUtils


class SearchRepository(BaseRepository):
    """
    搜索结果仓储
    处理搜索结果的数据库操作
    """

    def insert_search_results(self, media_items: list, title=None, ident_flag=True, session_id: str | None = None):
        """
        将返回信息插入数据库
        使用 UPSERT 语义：先删除同 session 冲突记录，再批量插入

        Args:
            media_items: 媒体信息列表
            title: 标题（用于非识别模式）
            ident_flag: 是否已识别标识
            session_id: 搜索会话 ID（用于多用户隔离）
        """
        if not media_items:
            return

        with self.session() as db:
            # 收集本次插入的 pageurl + site 用于删除同 session 冲突记录
            pageurl_site_pairs = []
            for media_item in media_items:
                if media_item.page_url and media_item.site:
                    pageurl_site_pairs.append((media_item.page_url, media_item.site))

            if pageurl_site_pairs:
                conditions = [
                    and_(SEARCHRESULTINFO.PAGEURL == pu, SEARCHRESULTINFO.SITE == st) for pu, st in pageurl_site_pairs
                ]
                query = db.query(SEARCHRESULTINFO).filter(or_(*conditions))
                if session_id:
                    query = query.filter(SEARCHRESULTINFO.SEARCH_SESSION_ID == session_id)
                query.delete(synchronize_session=False)

            mappings = []
            for media_item in media_items:
                if media_item.type == MediaType.TV:
                    mtype = MediaType.TV.value
                elif media_item.type == MediaType.MOVIE:
                    mtype = MediaType.MOVIE.value
                else:
                    mtype = MediaType.ANIME.value

                # 截断超长 ENCLOSURE：去掉磁力链接中多余的 tracker，只保留核心 btih
                enclosure = media_item.enclosure
                if enclosure and enclosure.startswith("magnet:"):
                    enclosure = enclosure.split("&")[0]
                elif enclosure and len(enclosure) > 4000:
                    enclosure = enclosure[:4000]

                mapping = {
                    "TORRENT_NAME": media_item.org_string,
                    "ENCLOSURE": enclosure,
                    "DESCRIPTION": media_item.description,
                    "TYPE": mtype if ident_flag else "",
                    "TITLE": media_item.title if ident_flag else title,
                    "YEAR": media_item.year if ident_flag else "",
                    "SEASON": media_item.get_season_string() if ident_flag else "",
                    "EPISODE": media_item.get_episode_string() if ident_flag else "",
                    "ES_STRING": media_item.get_season_episode_string() if ident_flag else "",
                    "VOTE": media_item.vote_average or "0",
                    "IMAGE": media_item.get_backdrop_image(default=False, original=True),
                    "POSTER": media_item.get_poster_image(),
                    "TMDBID": media_item.tmdb_id,
                    "OVERVIEW": media_item.overview,
                    "RES_TYPE": JsonUtils.dumps(
                        {
                            "respix": media_item.resource_pix,
                            "restype": media_item.resource_type,
                            "reseffect": media_item.resource_effect,
                            "video_encode": media_item.video_encode,
                        }
                    ),
                    "RES_ORDER": media_item.res_order,
                    "SIZE": int(media_item.size or 0),
                    "SEEDERS": int(media_item.seeders)
                    if media_item.seeders and str(media_item.seeders).strip().lstrip("-+").isdigit()
                    else 0,
                    "PEERS": int(media_item.peers)
                    if media_item.peers and str(media_item.peers).strip().lstrip("-+").isdigit()
                    else 0,
                    "SITE": media_item.site,
                    "SITE_ORDER": media_item.site_order,
                    "PAGEURL": media_item.page_url,
                    "OTHERINFO": media_item.resource_team,
                    "UPLOAD_VOLUME_FACTOR": media_item.upload_volume_factor,
                    "DOWNLOAD_VOLUME_FACTOR": media_item.download_volume_factor,
                    "NOTE": "|".join(media_item.labels)
                    if isinstance(media_item.labels, list)
                    else (media_item.labels or ""),
                }
                if session_id:
                    mapping["SEARCH_SESSION_ID"] = session_id
                mappings.append(mapping)

            # 按唯一约束 (PAGEURL, SITE, SEARCH_SESSION_ID) 去重，保留最后出现的
            deduped = {}
            for m in mappings:
                key = (m["PAGEURL"], m["SITE"], m.get("SEARCH_SESSION_ID"))
                deduped[key] = m
            mappings = list(deduped.values())

            db.bulk_insert_mappings(SEARCHRESULTINFO, mappings)
            db.commit()

    def get_search_result_by_id(self, dl_id):
        """
        根据ID从数据库中查询搜索结果的一条记录
        """
        with self.session() as db:
            return db.query(SEARCHRESULTINFO).filter(dl_id == SEARCHRESULTINFO.ID).all()

    def get_search_results(self, session_id: str | None = None):
        """
        查询搜索结果

        Args:
            session_id: 搜索会话 ID，传入时只返回该会话结果
        """
        with self.session() as db:
            query = db.query(SEARCHRESULTINFO)
            if session_id:
                query = query.filter(SEARCHRESULTINFO.SEARCH_SESSION_ID == session_id)
            return query.all()

    def delete_all_search_torrents(self):
        """
        删除所有搜索的记录（全局清理）
        """
        with self.session() as db:
            db.query(SEARCHRESULTINFO).delete()

    def delete_by_session(self, session_id: str):
        """
        按搜索会话删除记录
        """
        with self.session() as db:
            db.query(SEARCHRESULTINFO).filter(SEARCHRESULTINFO.SEARCH_SESSION_ID == session_id).delete(
                synchronize_session=False
            )
