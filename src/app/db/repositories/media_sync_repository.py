"""
媒体同步 Repository
处理媒体库同步相关的数据库操作
"""

import re
import time

from sqlalchemy import and_, or_

from app.db.models import MEDIASYNCITEMS, MEDIASYNCSTATISTIC
from app.db.repositories.base_repository import BaseRepository
from app.services.identity_resolver import IdentityResolver
from app.utils.json_utils import JsonUtils


class MediaSyncRepository(BaseRepository):
    """
    媒体同步数据仓储
    处理 MEDIASYNCITEMS 和 MEDIASYNCSTATISTIC 的数据库操作
    """

    def insert_item(
        self, server_type: str, iteminfo: dict, seasoninfo: list | None = None, server_id: int | None = None
    ) -> bool:
        """
        插入/更新媒体同步项目
        id 类字段统一转 str：MEDIASYNC_ITEMS 对应列为 varchar，PostgreSQL 不允许隐式转换
        """
        if not server_type or not iteminfo:
            return False

        item_id = str(iteminfo.get("id") or "")
        tmdb_id = str(iteminfo.get("tmdbid") or "") if iteminfo.get("tmdbid") is not None else ""
        imdb_id = str(iteminfo.get("imdbid") or "") if iteminfo.get("imdbid") is not None else ""
        year = str(iteminfo.get("year") or "") if iteminfo.get("year") is not None else ""
        anchor_provider = str(iteminfo.get("anchor_provider") or "").strip()
        anchor_external_id = str(iteminfo.get("anchor_external_id") or "").strip()
        display_title = iteminfo.get("seriesName") or iteminfo.get("title") or ""
        if not anchor_provider:
            if tmdb_id:
                anchor_provider, anchor_external_id = "tmdb", tmdb_id
            elif imdb_id:
                anchor_provider, anchor_external_id = "imdb", imdb_id
            else:
                match = re.search(r"([A-Za-z]{2,12})[-_ ]?(\d{2,6})", str(display_title))
                if match:
                    anchor_provider = "content_id"
                    anchor_external_id = f"{match.group(1).upper()}-{match.group(2)}"

        item_type = str(iteminfo.get("type") or "").lower()
        media_type = "movie" if item_type == "movie" else "tv"
        resolved = IdentityResolver().resolve_values(
            identity_id=iteminfo.get("identity_id"),
            provider=anchor_provider,
            external_id=anchor_external_id,
            title=display_title,
            year=year,
            media_type=media_type,
            content_profile=iteminfo.get("content_profile"),
            allow_local=False,
        )

        with self.session() as db:
            query = db.query(MEDIASYNCITEMS).filter(
                MEDIASYNCITEMS.SERVER == server_type,
                MEDIASYNCITEMS.ITEM_ID == item_id,
            )
            if server_id is not None:
                query = query.filter(MEDIASYNCITEMS.SERVER_ID == int(server_id))
            query.delete()

            new_item = MEDIASYNCITEMS(
                SERVER=server_type,
                SERVER_ID=server_id,
                LIBRARY=iteminfo.get("library") or "",
                ITEM_ID=item_id,
                ITEM_TYPE=iteminfo.get("type") or "",
                TITLE=iteminfo.get("title") or "",
                ORGIN_TITLE=iteminfo.get("originalTitle") or "",
                YEAR=year,
                TMDBID=tmdb_id,
                IMDBID=imdb_id,
                PATH=iteminfo.get("path") or "",
                NOTE=iteminfo.get("note") or "",
                JSON=JsonUtils.dumps(seasoninfo) if seasoninfo is not None else "",
                IDENTITY_ID=resolved.identity_id or None,
                ANCHOR_PROVIDER=anchor_provider or None,
                ANCHOR_EXTERNAL_ID=anchor_external_id or None,
                CONTENT_PROFILE=iteminfo.get("content_profile") or "default",
            )
            db.add(new_item)
            db.commit()
            return True

    def get_existing_anchors(self, pairs: list[tuple[str, str]]) -> set[tuple[str, str]]:
        """跨全部媒体实例查询已入库锚点，供探索页兜底标记."""
        normalized = {(str(p or "").strip(), str(e or "").strip()) for p, e in pairs if p and e}
        if not normalized:
            return set()
        conditions = [
            and_(MEDIASYNCITEMS.ANCHOR_PROVIDER == provider, MEDIASYNCITEMS.ANCHOR_EXTERNAL_ID == external)
            for provider, external in normalized
        ]
        with self.session() as db:
            rows = (
                db.query(MEDIASYNCITEMS.ANCHOR_PROVIDER, MEDIASYNCITEMS.ANCHOR_EXTERNAL_ID)
                .filter(or_(*conditions))
                .distinct()
                .all()
            )
        return {(str(provider or ""), str(external or "")) for provider, external in rows}

    def get_existing_identity_ids(self, identity_ids: list[str]) -> set[str]:
        """批量查询媒体同步索引中的身份 ID，供探索页跨 provider 锚点兜底."""
        normalized = {str(item).strip() for item in identity_ids if str(item or "").strip()}
        if not normalized:
            return set()
        with self.session() as db:
            rows = (
                db.query(MEDIASYNCITEMS.IDENTITY_ID)
                .filter(MEDIASYNCITEMS.IDENTITY_ID.in_(list(normalized)))
                .distinct()
                .all()
            )
        return {str(row[0]) for row in rows if row[0]}

    def empty_items(
        self, server_type: str | None = None, library: str | None = None, server_id: int | None = None
    ) -> bool:
        """
        清空媒体同步项目
        """
        with self.session() as db:
            query = db.query(MEDIASYNCITEMS)
            if server_id is not None:
                query = query.filter(MEDIASYNCITEMS.SERVER_ID == int(server_id))
            if server_type and library:
                query = query.filter(
                    MEDIASYNCITEMS.SERVER == server_type,
                    MEDIASYNCITEMS.LIBRARY == library,
                )
            elif server_type:
                query = query.filter(MEDIASYNCITEMS.SERVER == server_type)
            query.delete()
            db.commit()
            return True

    def save_statistics(
        self, server_type: str, total_count: int, movie_count: int, tv_count: int, server_id: int | None = None
    ) -> bool:
        """
        保存媒体同步统计
        """
        if not server_type:
            return False

        with self.session() as db:
            query = db.query(MEDIASYNCSTATISTIC).filter(MEDIASYNCSTATISTIC.SERVER == server_type)
            if server_id is not None:
                query = query.filter(MEDIASYNCSTATISTIC.SERVER_ID == int(server_id))
            query.delete()

            new_stat = MEDIASYNCSTATISTIC(
                SERVER=server_type,
                SERVER_ID=server_id,
                TOTAL_COUNT=str(total_count),
                MOVIE_COUNT=str(movie_count),
                TV_COUNT=str(tv_count),
                UPDATE_TIME=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            )
            db.add(new_stat)
            db.commit()
            return True

    def query_item(
        self,
        server_type: str,
        title: str,
        year: str | None = None,
        tmdbid: str | None = None,
        server_id: int | None = None,
    ):
        """
        查询媒体同步项目
        列 TMDBID/YEAR 为 varchar：入参统一转 str，避免 PostgreSQL 下 varchar = integer 报错
        """
        if not server_type or not title:
            return None
        if tmdbid is not None:
            tmdbid = str(tmdbid)
        if year is not None:
            year = str(year)

        with self.session() as db:
            query = db.query(MEDIASYNCITEMS).filter(MEDIASYNCITEMS.SERVER == server_type)
            if server_id is not None:
                query = query.filter(MEDIASYNCITEMS.SERVER_ID == int(server_id))

            if tmdbid:
                item = query.filter(MEDIASYNCITEMS.TMDBID == tmdbid).first()
                if item:
                    return item

            if year:
                item = query.filter(
                    MEDIASYNCITEMS.TITLE == title,
                    MEDIASYNCITEMS.YEAR == year,
                ).first()
            else:
                item = query.filter(MEDIASYNCITEMS.TITLE == title).first()

            return item

    def get_statistics(self, server_type: str, server_id: int | None = None):
        """获取指定实例的媒体同步统计。"""
        if not server_type:
            return None
        with self.session() as db:
            query = db.query(MEDIASYNCSTATISTIC).filter(MEDIASYNCSTATISTIC.SERVER == server_type)
            if server_id is not None:
                return query.filter(MEDIASYNCSTATISTIC.SERVER_ID == int(server_id)).first()
            return query.first()
