"""
RSS Repository
Handles RSS movies, TV shows, episodes and history related database operations.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import TYPE_CHECKING

from sqlalchemy import Integer, and_, cast, or_
from sqlalchemy.exc import IntegrityError

from app.db.models import SubscribeHistory, SubscribeMovies, SubscribeTorrents, SubscribeTvEpisodes, SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.data_scope import apply_owner_scope
from app.domain.entities.rss import SubscribeState
from app.domain.mediatypes import MediaType
from app.media.metadata.legacy import parse_legacy_ref
from app.media.metadata.policy import ANCHOR_POLICY
from app.schemas.auth import UserContext
from app.services.identity_resolver import IdentityResolver
from app.utils.json_utils import JsonUtils

_SEASON_PATTERN = re.compile(r"^S?(\d+)$", re.IGNORECASE)


def _normalize_tv_season(value: object) -> str:
    """订阅季号统一为 Sxx；范围/自定义值保持原样。"""
    text = str(value or "").strip()
    if not text:
        return ""
    match = _SEASON_PATTERN.fullmatch(text)
    return f"S{int(match.group(1)):02d}" if match else text


if TYPE_CHECKING:
    from app.media.models import MediaInfo


# DESC 列为 varchar(255)，存的是 TMDB 简介（可能超长）；SQLite 不校验长度，
# PostgreSQL 严格校验会抛 StringDataRightTruncation，故所有写入路径统一截断。
_DESC_MAX_LEN = 200


def _trim_desc(desc: str | None) -> str:
    """按仓库既有约定截断简介，保证新增/更新/历史各写入路径一致。"""
    return (desc or "")[:_DESC_MAX_LEN]


def _subscription_scope(row) -> dict[str, str | None]:
    if row is None:
        return {}
    return {
        "IDENTITY_ID": getattr(row, "IDENTITY_ID", None),
        "ANCHOR_PROVIDER": getattr(row, "ANCHOR_PROVIDER", None),
        "ANCHOR_EXTERNAL_ID": getattr(row, "ANCHOR_EXTERNAL_ID", None),
        "CONTENT_PROFILE": getattr(row, "CONTENT_PROFILE", None),
        "PROVIDER": getattr(row, "PROVIDER", None),
        "METADATA_REF": getattr(row, "METADATA_REF", None),
    }


def _history_scope(
    tmdbid: str | None,
    rtype: str,
    *,
    anchor_provider: str | None = None,
    anchor_external_id: str | None = None,
    identity_id: str | None = None,
    content_profile: str | None = None,
    metadata_policy: str | None = None,
    provider: str | None = None,
    metadata_ref: str | None = None,
    naming_profile: str | None = None,
) -> dict[str, str | None]:
    metadata_provider = str(provider or "").strip() or None
    provider = str(anchor_provider or "").strip()
    external = str(anchor_external_id or "").strip()
    if not provider or not external:
        media_type = MediaType.from_string(str(rtype or ""))
        if media_type == MediaType.UNKNOWN:
            media_type = MediaType.MOVIE
        ref = parse_legacy_ref(tmdbid, media_type)
        if ref is not None:
            provider = provider or ref.provider
            external = external or ref.external_id
    if not provider or not external:
        return {
            "IDENTITY_ID": identity_id,
            "ANCHOR_PROVIDER": None,
            "ANCHOR_EXTERNAL_ID": None,
            "CONTENT_PROFILE": content_profile,
            "PROVIDER": metadata_provider,
            "METADATA_REF": metadata_ref,
            "METADATA_POLICY": metadata_policy,
            "NAMING_PROFILE": naming_profile,
        }
    profile = content_profile or ("anime" if provider == "bangumi" else "default")
    return {
        "IDENTITY_ID": identity_id,
        "ANCHOR_PROVIDER": provider,
        "ANCHOR_EXTERNAL_ID": external,
        "CONTENT_PROFILE": profile,
        "PROVIDER": metadata_provider,
        "METADATA_REF": metadata_ref,
        "METADATA_POLICY": metadata_policy or ANCHOR_POLICY.get(provider),
        "NAMING_PROFILE": naming_profile,
    }


def _require_subscription_identity(
    *,
    identity_id: str | None,
    anchor_provider: str | None,
    anchor_external_id: str | None,
    media_info: MediaInfo,
    media_type: str,
    content_profile: str | None,
) -> str | None:
    resolved = IdentityResolver().resolve_values(
        identity_id=identity_id,
        provider=anchor_provider,
        external_id=anchor_external_id,
        title=getattr(media_info, "title", None),
        year=getattr(media_info, "year", None),
        media_type=media_type,
        content_profile=content_profile,
        allow_local=False,
    )
    if resolved.identity_id:
        return resolved.identity_id
    if anchor_provider and anchor_external_id:
        raise ValueError("可识别的订阅缺少规范 IDENTITY_ID")
    return identity_id


class SubscribeRepository(BaseRepository):
    """
    RSS订阅仓储
    处理RSS电影、电视剧、剧集和历史记录的数据库操作
    """

    def reset_rss_state(self) -> None:
        """
        初始化时批量重置所有 RSS 订阅状态
        将 STATE='S' 的订阅重置为 STATE='D'，由 SubscriptionMonitor 重新启动队列搜索
        """
        with self.session() as db:
            db.query(SubscribeMovies).filter(SubscribeMovies.STATE == SubscribeState.SEARCHING.value).update(
                {"STATE": SubscribeState.PENDING.value}, synchronize_session=False
            )
            db.query(SubscribeTvs).filter(SubscribeTvs.STATE == SubscribeState.SEARCHING.value).update(
                {"STATE": SubscribeState.PENDING.value}, synchronize_session=False
            )

    # ==================== RSS Movies ====================

    def get_rss_movies(
        self, state: str | None = None, rssid: int | None = None, user: UserContext | None = None
    ) -> list[SubscribeMovies]:
        """
        查询订阅电影信息（user=None 为系统上下文不过滤；否则按数据归属过滤）
        """
        with self.session() as db:
            query = db.query(SubscribeMovies)
            if rssid:
                query = query.filter(SubscribeMovies.ID == int(rssid))
            elif state:
                query = query.filter(SubscribeMovies.STATE == state)
            if user is not None:
                query = apply_owner_scope(query, SubscribeMovies, user)
            return query.all()

    def get_rss_movie_id(
        self,
        title: str,
        year: str | None = None,
        tmdbid: str | None = None,
        user_id: int | None = None,
        content_profile: str | None = None,
    ) -> int | str | None:
        """
        获取订阅电影ID（按归属用户与内容画像收敛，避免返回他人/其他画像的订阅）
        """
        if not title:
            return None
        with self.session() as db:

            def _scope(query):
                if user_id is not None:
                    query = query.filter(SubscribeMovies.USER_ID == user_id)
                if content_profile == "default":
                    query = query.filter(
                        or_(
                            SubscribeMovies.CONTENT_PROFILE == "default",
                            SubscribeMovies.CONTENT_PROFILE.is_(None),
                            SubscribeMovies.CONTENT_PROFILE == "",
                        )
                    )
                elif content_profile:
                    query = query.filter(SubscribeMovies.CONTENT_PROFILE == content_profile)
                return query

            if tmdbid:
                ret = _scope(db.query(SubscribeMovies.ID).filter(SubscribeMovies.TMDBID == str(tmdbid))).first()
                if ret:
                    return ret[0]
            query = _scope(db.query(SubscribeMovies.ID).filter(SubscribeMovies.NAME == title))
            if year:
                query = query.filter(SubscribeMovies.YEAR == str(year))
            ret = query.first()
            if ret:
                return ret[0]
            return self._fuzzy_subscribe_id(db, SubscribeMovies, title, year)

    def get_rss_tv_id(
        self,
        title: str,
        year: str | None = None,
        season: str | None = None,
        tmdbid: str | None = None,
        user_id: int | None = None,
        content_profile: str | None = None,
    ) -> int | str | None:
        """
        获取订阅电视剧ID（按归属用户与内容画像收敛）
        """
        if not title:
            return None
        with self.session() as db:

            def _scope(query):
                if user_id is not None:
                    query = query.filter(SubscribeTvs.USER_ID == user_id)
                if content_profile == "default":
                    query = query.filter(
                        or_(
                            SubscribeTvs.CONTENT_PROFILE == "default",
                            SubscribeTvs.CONTENT_PROFILE.is_(None),
                            SubscribeTvs.CONTENT_PROFILE == "",
                        )
                    )
                elif content_profile:
                    query = query.filter(SubscribeTvs.CONTENT_PROFILE == content_profile)
                return query

            if tmdbid:
                query = _scope(db.query(SubscribeTvs.ID).filter(SubscribeTvs.TMDBID == str(tmdbid)))
                if season:
                    query = query.filter(SubscribeTvs.SEASON == str(season))
                ret = query.first()
                if ret:
                    return ret[0]
            query = _scope(db.query(SubscribeTvs.ID).filter(SubscribeTvs.NAME == title))
            if season:
                query = query.filter(SubscribeTvs.SEASON == str(season))
            if year:
                query = query.filter(SubscribeTvs.YEAR == str(year))
            ret = query.first()
            if ret:
                return ret[0]
            return self._fuzzy_subscribe_id(db, SubscribeTvs, title, year)

    def get_rss_tv_id_by_anchor(
        self,
        provider: str,
        external_id: str,
        season: str | None = None,
        content_profile: str | None = None,
        user_id: int | None = None,
    ) -> int | None:
        """按多元数据锚点查订阅 ID（非 TMDB 订阅的转移进度依赖此方法）."""
        provider = str(provider or "").strip()
        external_id = str(external_id or "").strip()
        if not provider or not external_id:
            return None
        with self.session() as db:
            query = db.query(SubscribeTvs.ID).filter(
                SubscribeTvs.ANCHOR_PROVIDER == provider,
                SubscribeTvs.ANCHOR_EXTERNAL_ID == external_id,
            )
            if season:
                query = query.filter(SubscribeTvs.SEASON == str(season))
            if user_id is not None:
                query = query.filter(SubscribeTvs.USER_ID == user_id)
            if content_profile == "default":
                query = query.filter(
                    or_(
                        SubscribeTvs.CONTENT_PROFILE == "default",
                        SubscribeTvs.CONTENT_PROFILE.is_(None),
                        SubscribeTvs.CONTENT_PROFILE == "",
                    )
                )
            elif content_profile:
                query = query.filter(SubscribeTvs.CONTENT_PROFILE == content_profile)
            row = query.order_by(SubscribeTvs.ID.desc()).first()
            return int(row[0]) if row else None

    @staticmethod
    def _normalize_title(value) -> str:
        """标题归一化：去空白与常见标点，便于豆瓣/探索页标题与订阅名比对."""
        return re.sub(r"""[\s~～\-—–:：·・,，.。!！?？'"“”()（）\[\]【】]""", "", str(value or "")).lower()

    @classmethod
    def _titles_match(cls, candidate, target) -> bool:
        """标题匹配：归一化后互为子串，或相似度足够高（覆盖 我不是/我是不 之类差异）."""
        left, right = cls._normalize_title(candidate), cls._normalize_title(target)
        if not left or not right:
            return False
        if left in right or right in left:
            return True
        return difflib.SequenceMatcher(None, left, right).ratio() >= 0.85

    @classmethod
    def _fuzzy_subscribe_id(cls, db, model, title: str, year: str | None = None):
        """精确标题未命中时的模糊回退（豆瓣/探索页标题与订阅名常不一致）.

        先按年份优先做标题匹配，避免同名不同年误判。
        """
        base_title = str(title or "").split(" (")[0].strip()
        if not base_title:
            return None
        ret = db.query(model.ID).filter(model.NAME.contains(base_title, autoescape=True)).first()
        if ret:
            return ret[0]
        rows = db.query(model.ID, model.NAME, model.YEAR).all()
        for year_first in (True, False):
            for rid, name, row_year in rows:
                if year_first and year and str(row_year) != str(year):
                    continue
                if cls._titles_match(name, base_title):
                    return rid
        return None

    def get_subscribe_id(self, mtype, title, year, tmdbid) -> int | None:
        """
        查询订阅ID
        """
        if not title:
            return None
        if mtype == MediaType.MOVIE:
            result = self.get_rss_movie_id(title, year, tmdbid)
        else:
            result = self.get_rss_tv_id(title, year, tmdbid)
        return int(result) if isinstance(result, (int, str)) and str(result).isdigit() else None

    def get_rss_movie_sites(self, rssid: int | None) -> str:
        """
        获取订阅电影站点
        """
        if not rssid:
            return ""
        with self.session() as db:
            ret = db.query(SubscribeMovies.DESC).filter(SubscribeMovies.ID == int(rssid)).first()
            if ret:
                return ret[0]
            return ""

    def update_rss_movie_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, image: str, desc: str, note: str
    ) -> None:
        """
        更新订阅电影的部分信息
        """
        if not tmdbid:
            return
        with self.session() as db:
            db.query(SubscribeMovies).filter(SubscribeMovies.ID == int(rid)).update(
                {
                    "TMDBID": tmdbid,
                    "NAME": title,
                    "YEAR": year,
                    "IMAGE": image,
                    "NOTE": note,
                    "DESC": _trim_desc(desc),
                }
            )

    def update_rss_movie_desc(self, rid: int, desc: str) -> None:
        """
        更新订阅电影的DESC
        """
        with self.session() as db:
            db.query(SubscribeMovies).filter(SubscribeMovies.ID == int(rid)).update({"DESC": _trim_desc(desc)})

    def update_rss_filter_order(self, rtype: str, rssid: int, res_order: str) -> None:
        """
        更新订阅命中的过滤规则优先级
        """
        with self.session() as db:
            if rtype == MediaType.MOVIE:
                db.query(SubscribeMovies).filter(SubscribeMovies.ID == int(rssid)).update({"FILTER_ORDER": res_order})
            else:
                db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid)).update({"FILTER_ORDER": res_order})

    def get_rss_overedition_order(self, rtype: str, rssid: int) -> int:
        """
        查询当前订阅的过滤优先级
        """
        with self.session() as db:
            if rtype == MediaType.MOVIE:
                res = db.query(SubscribeMovies.FILTER_ORDER).filter(SubscribeMovies.ID == int(rssid)).first()
            else:
                res = db.query(SubscribeTvs.FILTER_ORDER).filter(SubscribeTvs.ID == int(rssid)).first()
            if res and res[0]:
                return int(res[0])
            return 0

    def is_exists_rss_movie(self, title: str, year: str | None = None) -> bool:
        """
        判断RSS电影是否存在
        """
        if not title:
            return False
        with self.session() as db:
            if year is not None:
                count = (
                    db.query(SubscribeMovies)
                    .filter(SubscribeMovies.NAME == title, SubscribeMovies.YEAR == str(year))
                    .count()
                )
            else:
                count = db.query(SubscribeMovies).filter(SubscribeMovies.NAME == title).count()
            return count > 0

    def insert_rss_movie(
        self,
        media_info: MediaInfo,
        state: str = SubscribeState.PENDING.value,
        rss_sites: list | None = None,
        search_sites: list | None = None,
        over_edition: int = 0,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: int | str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        filter_free: bool | None = None,
        save_path: str | None = None,
        download_setting: int = -1,
        fuzzy_match: int = 0,
        desc: str | None = None,
        note: str | None = None,
        keyword: str | None = None,
        user_id: int | None = None,
        identity_id: str | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        content_profile: str | None = None,
        provider: str | None = None,
        metadata_ref: str | None = None,
        metadata_policy: str | None = None,
        naming_profile: str | None = None,
    ) -> int:
        """
        新增RSS电影（user_id 为订阅归属用户，None 为系统/插件创建）
        """
        if search_sites is None:
            search_sites = []
        if rss_sites is None:
            rss_sites = []
        over_edition = over_edition or 0
        fuzzy_match = fuzzy_match or 0
        download_setting = download_setting or -1
        filter_restype = filter_restype or ""
        filter_pix = filter_pix or ""
        filter_rule = int(filter_rule) if filter_rule else 0
        filter_team = filter_team or ""
        filter_include = filter_include or ""
        filter_exclude = filter_exclude or ""
        save_path = save_path or ""
        note = note or ""
        keyword = keyword or (media_info.title if media_info else "")
        desc = _trim_desc(desc)
        if not media_info:
            return -1
        if not media_info.title:
            return -1
        identity_id = _require_subscription_identity(
            identity_id=identity_id,
            anchor_provider=anchor_provider,
            anchor_external_id=anchor_external_id,
            media_info=media_info,
            media_type=MediaType.MOVIE.value,
            content_profile=content_profile,
        )

        with self.session() as db:
            # 重复判定按归属用户维度；有 provider 锚点时按锚点去重，避免同名不同来源互相覆盖
            if anchor_provider and anchor_external_id:
                dup_query = db.query(SubscribeMovies).filter(
                    SubscribeMovies.ANCHOR_PROVIDER == anchor_provider,
                    SubscribeMovies.ANCHOR_EXTERNAL_ID == anchor_external_id,
                )
                if content_profile:
                    dup_query = dup_query.filter(SubscribeMovies.CONTENT_PROFILE == content_profile)
            else:
                dup_query = db.query(SubscribeMovies).filter(SubscribeMovies.NAME == media_info.title)
                if media_info.year is not None:
                    dup_query = dup_query.filter(SubscribeMovies.YEAR == str(media_info.year))
            if user_id is not None:
                dup_query = dup_query.filter(SubscribeMovies.USER_ID == user_id)
            if dup_query.count() > 0:
                return 9

            try:
                movie = SubscribeMovies(
                    NAME=media_info.title,
                    YEAR=media_info.year,
                    TMDBID=media_info.tmdb_id or None,
                    IMAGE=media_info.get_poster_image(),
                    RSS_SITES=JsonUtils.dumps(rss_sites),
                    SEARCH_SITES=JsonUtils.dumps(search_sites),
                    OVER_EDITION=over_edition,
                    FILTER_ORDER=0,
                    FILTER_RESTYPE=filter_restype,
                    FILTER_PIX=filter_pix,
                    FILTER_RULE=filter_rule,
                    FILTER_TEAM=filter_team,
                    FILTER_INCLUDE=filter_include,
                    FILTER_EXCLUDE=filter_exclude,
                    FILTER_FREE=None if filter_free is None else int(filter_free),
                    SAVE_PATH=save_path,
                    DOWNLOAD_SETTING=download_setting,
                    FUZZY_MATCH=fuzzy_match,
                    STATE=state,
                    DESC=_trim_desc(desc),
                    NOTE=note,
                    KEYWORD=keyword,
                    ADD_DATE=time.strftime("%Y-%m-%d %H:%M:%S"),
                    USER_ID=user_id,
                    IDENTITY_ID=identity_id,
                    ANCHOR_PROVIDER=anchor_provider,
                    ANCHOR_EXTERNAL_ID=anchor_external_id,
                    CONTENT_PROFILE=content_profile,
                    PROVIDER=provider,
                    METADATA_REF=metadata_ref,
                    METADATA_POLICY=metadata_policy,
                    NAMING_PROFILE=naming_profile,
                )
                db.add(movie)
                db.flush()
                return movie.ID
            except IntegrityError:
                return 9

    def update_rss_movie(self, rssid: int, user: UserContext | None = None, **kwargs: str | int | list | None) -> int:
        """
        更新RSS电影订阅信息（根据rssid；user 非空且非超管时校验归属，越权为无操作）
        """
        if not rssid:
            return -1
        update_fields = {}
        field_map = {
            "name": "NAME",
            "year": "YEAR",
            "tmdbid": "TMDBID",
            "image": "IMAGE",
            "rss_sites": "RSS_SITES",
            "search_sites": "SEARCH_SITES",
            "over_edition": "OVER_EDITION",
            "filter_restype": "FILTER_RESTYPE",
            "filter_pix": "FILTER_PIX",
            "filter_rule": "FILTER_RULE",
            "filter_team": "FILTER_TEAM",
            "filter_include": "FILTER_INCLUDE",
            "filter_exclude": "FILTER_EXCLUDE",
            "filter_free": "FILTER_FREE",
            "save_path": "SAVE_PATH",
            "download_setting": "DOWNLOAD_SETTING",
            "fuzzy_match": "FUZZY_MATCH",
            "state": "STATE",
            "desc": "DESC",
            "note": "NOTE",
            "keyword": "KEYWORD",
            "identity_id": "IDENTITY_ID",
            "anchor_provider": "ANCHOR_PROVIDER",
            "anchor_external_id": "ANCHOR_EXTERNAL_ID",
            "content_profile": "CONTENT_PROFILE",
            "provider": "PROVIDER",
            "metadata_ref": "METADATA_REF",
            "metadata_policy": "METADATA_POLICY",
            "naming_profile": "NAMING_PROFILE",
        }
        for k, v in kwargs.items():
            col = field_map.get(k)
            if col is None:
                continue
            if v is None:
                # None = 不更新该字段，保留原值
                continue
            if k in ("rss_sites", "search_sites") and isinstance(v, list):
                update_fields[col] = JsonUtils.dumps(v)
            elif k == "filter_free":
                update_fields[col] = None if v is None else (1 if v else 0)
            elif col == "DESC":
                update_fields[col] = _trim_desc(v if isinstance(v, str) else str(v))
            elif k == "season":
                update_fields[col] = _normalize_tv_season(v)
            else:
                update_fields[col] = v
        if not update_fields:
            return 0
        with self.session() as db:
            query = db.query(SubscribeMovies).filter(SubscribeMovies.ID == int(rssid))
            if user is not None and not user.is_superadmin:
                query = query.filter(SubscribeMovies.USER_ID == user.user_id)
            query.update(update_fields)
        return 0

    def delete_rss_movie(
        self,
        title: str | None = None,
        year: str | None = None,
        rssid: int | None = None,
        tmdbid: str | None = None,
        user: UserContext | None = None,
    ) -> int:
        """
        删除RSS电影（user 非空且非超管时校验归属，越权为无操作），返回删除行数
        """
        if not title and not rssid:
            return 0
        with self.session() as db:
            if rssid:
                query = db.query(SubscribeMovies).filter(SubscribeMovies.ID == int(rssid))
                if user is not None and not user.is_superadmin:
                    query = query.filter(SubscribeMovies.USER_ID == user.user_id)
                movie = query.first()
                if movie:
                    title_filter = movie.NAME if movie.NAME else ""
                    year_filter = str(movie.YEAR) if movie.YEAR else ""
                    if title_filter:
                        db.query(SubscribeTorrents).filter(
                            SubscribeTorrents.TITLE == title_filter,
                            SubscribeTorrents.YEAR == year_filter,
                        ).delete()
                    db.delete(movie)
                    return 1
                return 0
            query = db.query(SubscribeMovies)
            if tmdbid:
                query = query.filter(SubscribeMovies.TMDBID == tmdbid)
            else:
                query = query.filter(SubscribeMovies.NAME == title, SubscribeMovies.YEAR == str(year))
            if user is not None and not user.is_superadmin:
                query = query.filter(SubscribeMovies.USER_ID == user.user_id)
            rows = query.all()
            for movie in rows:
                db.delete(movie)
            return len(rows)

    def update_rss_movie_state(
        self,
        title: str | None = None,
        year: str | None = None,
        rssid: int | None = None,
        state: str = SubscribeState.RUNNING.value,
    ) -> None:
        """
        更新电影订阅状态
        """
        if not title and not rssid:
            return
        with self.session() as db:
            if rssid:
                db.query(SubscribeMovies).filter(SubscribeMovies.ID == int(rssid)).update({"STATE": state})
            else:
                db.query(SubscribeMovies).filter(
                    SubscribeMovies.NAME == title, SubscribeMovies.YEAR == str(year)
                ).update({"STATE": state})

    # ==================== RSS TV Shows ====================

    def get_rss_tvs(
        self, state: str | None = None, rssid: int | None = None, user: UserContext | None = None
    ) -> list[SubscribeTvs]:
        """
        查询订阅电视剧信息（user=None 为系统上下文不过滤；否则按数据归属过滤）
        """
        with self.session() as db:
            query = db.query(SubscribeTvs)
            if rssid:
                query = query.filter(SubscribeTvs.ID == int(rssid))
            elif state:
                query = query.filter(SubscribeTvs.STATE == state)
            if user is not None:
                query = apply_owner_scope(query, SubscribeTvs, user)
            return query.all()

    def find_tv_owner_user_id(self, tmdbid: str | None, season: str | None = None) -> int | None:
        """按 TMDB（+季）反查 TV 订阅归属用户（历史被清理后转移通知仍可定向）."""
        if not tmdbid:
            return None
        with self.session() as db:
            query = db.query(SubscribeTvs.USER_ID).filter(SubscribeTvs.TMDBID == str(tmdbid))
            if season:
                query = query.filter(SubscribeTvs.SEASON == str(season))
            row = query.order_by(SubscribeTvs.ID.desc()).first()
            value = row[0] if row else None
            return int(value) if value is not None else None

    def get_movie_subscription_hint(
        self,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        keyword: str | None = None,
        identity_id: str | None = None,
    ) -> dict:
        """按身份/锚点/名称取订阅海报与画像，供下载、转移阶段复用."""
        conditions = []
        identity = str(identity_id or "").strip()
        if identity:
            conditions.append(SubscribeMovies.IDENTITY_ID == identity)
        provider = str(anchor_provider or "").strip()
        external = str(anchor_external_id or "").strip()
        if provider and external:
            conditions.append(
                and_(
                    SubscribeMovies.ANCHOR_PROVIDER == provider,
                    SubscribeMovies.ANCHOR_EXTERNAL_ID == external,
                )
            )
        text = str(keyword or "").strip()
        if not conditions and not text:
            return {}
        with self.session() as db:
            row = None
            # 身份/锚点精确优先，避免同名不同内容串图。
            if conditions:
                row = db.query(SubscribeMovies).filter(or_(*conditions)).order_by(SubscribeMovies.ID.desc()).first()
            if row is None and text:
                row = (
                    db.query(SubscribeMovies)
                    .filter(or_(SubscribeMovies.NAME == text, SubscribeMovies.KEYWORD == text))
                    .order_by(SubscribeMovies.ID.desc())
                    .first()
                )
            if row is None:
                return {}
            return {
                "image": row.IMAGE or "",
                "content_profile": row.CONTENT_PROFILE or "",
                "anchor_provider": row.ANCHOR_PROVIDER or "",
                "anchor_external_id": row.ANCHOR_EXTERNAL_ID or "",
                "provider": row.PROVIDER or "",
                "metadata_ref": row.METADATA_REF or "",
                "identity_id": row.IDENTITY_ID or "",
                "tmdbid": row.TMDBID or "",
            }

    def find_movie_owner_user_id(self, tmdbid: str | None) -> int | None:
        """按 TMDB 反查电影订阅归属用户."""
        if not tmdbid:
            return None
        with self.session() as db:
            row = (
                db.query(SubscribeMovies.USER_ID)
                .filter(SubscribeMovies.TMDBID == str(tmdbid))
                .order_by(SubscribeMovies.ID.desc())
                .first()
            )
            value = row[0] if row else None
            return int(value) if value is not None else None

    def find_owner_by_anchor(self, provider: str | None, external_id: str | None, mtype: MediaType) -> int | None:
        """按豆瓣/Bangumi 等锚点反查订阅归属用户."""
        if not provider or not external_id:
            return None
        model = SubscribeMovies if mtype == MediaType.MOVIE else SubscribeTvs
        with self.session() as db:
            row = (
                db.query(model.USER_ID)
                .filter(
                    model.ANCHOR_PROVIDER == str(provider),
                    model.ANCHOR_EXTERNAL_ID == str(external_id),
                )
                .order_by(model.ID.desc())
                .first()
            )
            value = row[0] if row else None
            return int(value) if value is not None else None

    def get_rss_tv_sites(self, rssid: int | None) -> SubscribeTvs | str:
        """
        获取订阅电视剧站点
        """
        if not rssid:
            return ""
        with self.session() as db:
            ret = db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid)).first()
            if ret:
                return ret
            return ""

    def update_rss_tv_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, total: int, lack: int, image: str, desc: str, note: str
    ) -> None:
        """
        更新订阅电视剧的TMDB信息
        """
        if not tmdbid:
            return
        with self.session() as db:
            db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rid)).update(
                {
                    "TMDBID": tmdbid,
                    "NAME": title,
                    "YEAR": year,
                    "TOTAL": total,
                    "LACK": lack,
                    "IMAGE": image,
                    "DESC": _trim_desc(desc),
                    "NOTE": note,
                }
            )

    def update_rss_tv_desc(self, rid: int, desc: str) -> None:
        """
        更新订阅电视剧的DESC
        """
        with self.session() as db:
            db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rid)).update({"DESC": _trim_desc(desc)})

    def is_exists_rss_tv(self, title: str, year: str | None = None, season: str | None = None) -> bool:
        """
        判断RSS电视剧是否存在
        """
        if not title:
            return False
        with self.session() as db:
            if season:
                count = (
                    db.query(SubscribeTvs)
                    .filter(SubscribeTvs.NAME == title, SubscribeTvs.YEAR == str(year), SubscribeTvs.SEASON == season)
                    .count()
                )
            else:
                count = (
                    db.query(SubscribeTvs).filter(SubscribeTvs.NAME == title, SubscribeTvs.YEAR == str(year)).count()
                )
            return count > 0

    def insert_rss_tv(
        self,
        media_info: MediaInfo,
        total: int,
        lack: int = 0,
        state: str = SubscribeState.PENDING.value,
        rss_sites: list | None = None,
        search_sites: list | None = None,
        over_edition: int = 0,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: int | str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        filter_free: bool | None = None,
        save_path: str | None = None,
        download_setting: int = -1,
        total_ep: int | str | None = None,
        current_ep: int | str | None = None,
        fuzzy_match: int = 0,
        desc: str | None = None,
        note: str | None = None,
        keyword: str | None = None,
        rssid: int | None = None,
        user_id: int | None = None,
        identity_id: str | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        content_profile: str | None = None,
        provider: str | None = None,
        metadata_ref: str | None = None,
        metadata_policy: str | None = None,
        naming_profile: str | None = None,
    ) -> int:
        """
        新增RSS电视剧（rssid 不为空时跳过 is_exists 检查，用于编辑替换场景；user_id 为订阅归属用户）
        """
        if search_sites is None:
            search_sites = []
        if rss_sites is None:
            rss_sites = []
        over_edition = over_edition or 0
        fuzzy_match = fuzzy_match or 0
        download_setting = download_setting or -1
        filter_restype = filter_restype or ""
        filter_pix = filter_pix or ""
        filter_rule = int(filter_rule) if filter_rule else 0
        filter_team = filter_team or ""
        filter_include = filter_include or ""
        filter_exclude = filter_exclude or ""
        save_path = save_path or ""
        note = note or ""
        keyword = keyword or (media_info.title if media_info else "")
        total_ep = int(total_ep) if total_ep else 0
        current_ep = int(current_ep) if current_ep else 0
        desc = _trim_desc(desc)
        if not media_info:
            return -1
        if not media_info.title:
            return -1
        identity_id = _require_subscription_identity(
            identity_id=identity_id,
            anchor_provider=anchor_provider,
            anchor_external_id=anchor_external_id,
            media_info=media_info,
            media_type=getattr(getattr(media_info, "type", None), "value", "tv") or "tv",
            content_profile=content_profile,
        )
        if fuzzy_match and media_info.begin_season is None:
            season_str = ""
        else:
            season_str = _normalize_tv_season(media_info.get_season_string())

        with self.session() as db:
            if not rssid:
                # 重复判定按归属用户维度；有 provider 锚点时优先按锚点去重
                if anchor_provider and anchor_external_id:
                    dup_query = db.query(SubscribeTvs).filter(
                        SubscribeTvs.ANCHOR_PROVIDER == anchor_provider,
                        SubscribeTvs.ANCHOR_EXTERNAL_ID == anchor_external_id,
                    )
                    if content_profile:
                        dup_query = dup_query.filter(SubscribeTvs.CONTENT_PROFILE == content_profile)
                    if season_str:
                        dup_query = dup_query.filter(SubscribeTvs.SEASON == season_str)
                else:
                    dup_query = db.query(SubscribeTvs).filter(
                        SubscribeTvs.NAME == media_info.title,
                        SubscribeTvs.YEAR == str(media_info.year),
                    )
                    if season_str:
                        dup_query = dup_query.filter(SubscribeTvs.SEASON == season_str)
                if user_id is not None:
                    dup_query = dup_query.filter(SubscribeTvs.USER_ID == user_id)
                if dup_query.count() > 0:
                    return 9

            try:
                tv = SubscribeTvs(
                    NAME=media_info.title,
                    YEAR=media_info.year,
                    SEASON=season_str,
                    TMDBID=media_info.tmdb_id or None,
                    IMAGE=media_info.get_poster_image(),
                    RSS_SITES=JsonUtils.dumps(rss_sites),
                    SEARCH_SITES=JsonUtils.dumps(search_sites),
                    OVER_EDITION=over_edition,
                    FILTER_ORDER=0,
                    FILTER_RESTYPE=filter_restype,
                    FILTER_PIX=filter_pix,
                    FILTER_RULE=filter_rule,
                    FILTER_TEAM=filter_team,
                    FILTER_INCLUDE=filter_include,
                    FILTER_EXCLUDE=filter_exclude,
                    FILTER_FREE=None if filter_free is None else int(filter_free),
                    SAVE_PATH=save_path,
                    DOWNLOAD_SETTING=download_setting,
                    FUZZY_MATCH=fuzzy_match,
                    TOTAL_EP=total_ep,
                    CURRENT_EP=current_ep,
                    TOTAL=total,
                    LACK=lack,
                    STATE=state,
                    DESC=_trim_desc(desc),
                    NOTE=note,
                    KEYWORD=keyword,
                    ADD_DATE=time.strftime("%Y-%m-%d %H:%M:%S"),
                    USER_ID=user_id,
                    IDENTITY_ID=identity_id,
                    ANCHOR_PROVIDER=anchor_provider,
                    ANCHOR_EXTERNAL_ID=anchor_external_id,
                    CONTENT_PROFILE=content_profile,
                    PROVIDER=provider,
                    METADATA_REF=metadata_ref,
                    METADATA_POLICY=metadata_policy,
                    NAMING_PROFILE=naming_profile,
                )
                db.add(tv)
                db.flush()
                return tv.ID
            except IntegrityError:
                return 9

    def update_rss_tv(self, rssid: int, user: UserContext | None = None, **kwargs: str | int | list | None) -> int:
        """
        更新RSS电视剧订阅信息（根据rssid；user 非空且非超管时校验归属，越权为无操作）
        """
        if not rssid:
            return -1
        update_fields = {}
        field_map = {
            "name": "NAME",
            "year": "YEAR",
            "season": "SEASON",
            "tmdbid": "TMDBID",
            "image": "IMAGE",
            "rss_sites": "RSS_SITES",
            "search_sites": "SEARCH_SITES",
            "over_edition": "OVER_EDITION",
            "filter_restype": "FILTER_RESTYPE",
            "filter_pix": "FILTER_PIX",
            "filter_rule": "FILTER_RULE",
            "filter_team": "FILTER_TEAM",
            "filter_include": "FILTER_INCLUDE",
            "filter_exclude": "FILTER_EXCLUDE",
            "filter_free": "FILTER_FREE",
            "save_path": "SAVE_PATH",
            "download_setting": "DOWNLOAD_SETTING",
            "fuzzy_match": "FUZZY_MATCH",
            "total_ep": "TOTAL_EP",
            "current_ep": "CURRENT_EP",
            "total": "TOTAL",
            "lack": "LACK",
            "state": "STATE",
            "desc": "DESC",
            "note": "NOTE",
            "keyword": "KEYWORD",
            "identity_id": "IDENTITY_ID",
            "anchor_provider": "ANCHOR_PROVIDER",
            "anchor_external_id": "ANCHOR_EXTERNAL_ID",
            "content_profile": "CONTENT_PROFILE",
            "provider": "PROVIDER",
            "metadata_ref": "METADATA_REF",
            "metadata_policy": "METADATA_POLICY",
            "naming_profile": "NAMING_PROFILE",
        }
        for k, v in kwargs.items():
            col = field_map.get(k)
            if col is None:
                continue
            if v is None:
                # None = 不更新该字段，保留原值（避免编辑时意外清空站点/集数等配置）
                continue
            if k in ("rss_sites", "search_sites") and isinstance(v, list):
                update_fields[col] = JsonUtils.dumps(v)
            elif k == "filter_free":
                update_fields[col] = None if v is None else (1 if v else 0)
            elif col == "DESC":
                update_fields[col] = _trim_desc(v if isinstance(v, str) else str(v))
            elif k == "season":
                update_fields[col] = _normalize_tv_season(v)
            else:
                update_fields[col] = v
        if not update_fields:
            return 0
        # 开始集数变更时，同步重置持久化的缺失集列表与 LACK，
        # 否则下一轮轮询仍按旧列表处理，update_rss_tv_lack 会把 CURRENT_EP 推回旧位置
        sync_episodes: list[int] | None = None
        if "CURRENT_EP" in update_fields:
            cur = update_fields.get("CURRENT_EP")
            total_num = update_fields.get("TOTAL") or update_fields.get("TOTAL_EP")
            if isinstance(cur, int) and isinstance(total_num, int) and 0 < cur <= total_num:
                sync_episodes = list(range(cur, total_num + 1))
            else:
                sync_episodes = []
            update_fields["LACK"] = len(sync_episodes)
        with self.session() as db:
            if sync_episodes is not None:
                episodes_str = ",".join(str(e) for e in sync_episodes)
                ep_filter = cast(SubscribeTvEpisodes.RSSID, Integer) == int(rssid)
                if db.query(SubscribeTvEpisodes).filter(ep_filter).count() > 0:
                    db.query(SubscribeTvEpisodes).filter(ep_filter).update({"EPISODES": episodes_str})
                else:
                    db.add(SubscribeTvEpisodes(RSSID=rssid, EPISODES=episodes_str))
            query = db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid))
            if user is not None and not user.is_superadmin:
                query = query.filter(SubscribeTvs.USER_ID == user.user_id)
            query.update(update_fields)
        return 0

    def update_rss_tv_lack(
        self,
        title: str | None = None,
        year: str | None = None,
        season: str | None = None,
        rssid: int | None = None,
        lack_episodes: list | None = None,
    ) -> None:
        """
        更新电视剧缺失的集数
        """
        if not title and not rssid:
            return
        if not lack_episodes:
            lack = 0
            episodes: list[str] = []
            new_current_ep: int | None = None
        else:
            lack = len(lack_episodes)
            episodes = [str(epi) for epi in lack_episodes]
            # current_ep 语义 = 首个待下载集 → 缺失集最小值（转移/刷新后同步推进）
            nums = [int(e) for e in lack_episodes if str(e).isdigit()]
            new_current_ep = min(nums) if nums else None
        with self.session() as db:
            if rssid:
                # 内联 update_rss_tv_episodes，确保与 LACK 更新在同一事务
                if (
                    db.query(SubscribeTvEpisodes).filter(cast(SubscribeTvEpisodes.RSSID, Integer) == int(rssid)).count()
                    > 0
                ):
                    db.query(SubscribeTvEpisodes).filter(cast(SubscribeTvEpisodes.RSSID, Integer) == int(rssid)).update(
                        {"EPISODES": ",".join(episodes)}
                    )
                else:
                    db.add(SubscribeTvEpisodes(RSSID=rssid, EPISODES=",".join(episodes)))
                update_fields: dict = {"LACK": lack}
                if new_current_ep is not None:
                    update_fields["CURRENT_EP"] = new_current_ep
                db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid)).update(update_fields)
            else:
                update_fields = {"LACK": lack}
                if new_current_ep is not None:
                    update_fields["CURRENT_EP"] = new_current_ep
                db.query(SubscribeTvs).filter(
                    SubscribeTvs.NAME == title, SubscribeTvs.YEAR == str(year), SubscribeTvs.SEASON == season
                ).update(update_fields)

    def update_rss_tv_total(self, rssid: int, total_ep: int, lack_episodes: list | None = None) -> None:
        """更新电视剧总集数（TMDB 集数增加时同步），同时可选更新缺失集"""
        if not rssid:
            return
        lack = len(lack_episodes) if lack_episodes else 0
        episodes_str = ",".join(str(e) for e in lack_episodes) if lack_episodes else ""
        with self.session() as db:
            db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid)).update(
                {"TOTAL_EP": total_ep, "TOTAL": total_ep, "LACK": lack}
            )
            if rssid:
                existing = db.query(SubscribeTvEpisodes).filter(SubscribeTvEpisodes.RSSID == int(rssid)).first()
                if existing:
                    existing.EPISODES = episodes_str
                else:
                    db.add(SubscribeTvEpisodes(RSSID=str(rssid), EPISODES=episodes_str))

    def delete_rss_tv(
        self,
        title: str | None = None,
        season: str | None = None,
        rssid: int | None = None,
        tmdbid: str | None = None,
        user: UserContext | None = None,
    ) -> int:
        """
        删除RSS电视剧（user 非空且非超管时校验归属，越权为无操作），返回删除行数
        """
        if not title and not rssid:
            return 0
        with self.session() as db:

            def _scope(query):
                if user is not None and not user.is_superadmin:
                    query = query.filter(SubscribeTvs.USER_ID == user.user_id)
                return query

            if not rssid:
                # 内联查找，确保后续删除在同一事务上下文，并先按归属收敛
                if tmdbid:
                    query = _scope(db.query(SubscribeTvs.ID).filter(SubscribeTvs.TMDBID == tmdbid))
                    if season:
                        query = query.filter(SubscribeTvs.SEASON == season)
                    ret = query.first()
                    if ret:
                        rssid = ret[0]
                if not rssid:
                    query = _scope(db.query(SubscribeTvs).filter(SubscribeTvs.NAME == title))
                    if season:
                        query = query.filter(SubscribeTvs.SEASON == str(season))
                    items = query.all()
                    if items:
                        if tmdbid:
                            for item in items:
                                if not item.TMDBID or str(tmdbid) == item.TMDBID:
                                    rssid = item.ID
                                    break
                        else:
                            rssid = items[0].ID
            if rssid:
                query = db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid))
                if user is not None and not user.is_superadmin:
                    query = query.filter(SubscribeTvs.USER_ID == user.user_id)
                tv = query.first()
                if tv:
                    title_filter = tv.NAME if tv.NAME else ""
                    year_filter = str(tv.YEAR) if tv.YEAR else ""
                    season_filter = str(tv.SEASON) if tv.SEASON else ""
                    if title_filter:
                        db.query(SubscribeTorrents).filter(
                            SubscribeTorrents.TITLE == title_filter,
                            SubscribeTorrents.YEAR == year_filter,
                            SubscribeTorrents.SEASON == season_filter,
                        ).delete()
                    db.query(SubscribeTvEpisodes).filter(
                        cast(SubscribeTvEpisodes.RSSID, Integer) == int(rssid)
                    ).delete()
                    db.delete(tv)
                    return 1
            return 0

    def update_rss_tv_state(
        self,
        title: str | None = None,
        year: str | None = None,
        season: str | None = None,
        rssid: int | None = None,
        state: str = SubscribeState.RUNNING.value,
    ) -> None:
        """
        更新电视剧订阅状态
        """
        if not title and not rssid:
            return
        with self.session() as db:
            if rssid:
                db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rssid)).update({"STATE": state})
            else:
                db.query(SubscribeTvs).filter(
                    SubscribeTvs.NAME == title, SubscribeTvs.YEAR == str(year), SubscribeTvs.SEASON == season
                ).update({"STATE": state})

    # ==================== RSS TV Episodes ====================

    def is_exists_rss_tv_episodes(self, rid: int | None) -> bool:
        """
        判断RSS电视剧剧集是否存在
        """
        if not rid:
            return False
        with self.session() as db:
            count = db.query(SubscribeTvEpisodes).filter(cast(SubscribeTvEpisodes.RSSID, Integer) == int(rid)).count()
            return count > 0

    def update_rss_tv_episodes(self, rid: int | None, episodes: list | None) -> None:
        """
        插入或更新电视剧订阅缺失剧集
        """
        if not rid:
            return
        if not episodes:
            episodes = []
        else:
            episodes = [str(epi) for epi in episodes]
        with self.session() as db:
            subscription = db.query(SubscribeTvs).filter(SubscribeTvs.ID == int(rid)).first()
            scope = _subscription_scope(subscription)
            existing = (
                db.query(SubscribeTvEpisodes).filter(cast(SubscribeTvEpisodes.RSSID, Integer) == int(rid)).first()
            )
            if existing:
                existing.EPISODES = ",".join(episodes)
                for key, value in scope.items():
                    if value is not None:
                        setattr(existing, key, value)
            else:
                db.add(SubscribeTvEpisodes(RSSID=rid, EPISODES=",".join(episodes), **scope))

    def get_rss_tv_episodes(self, rid: int | None) -> list[int] | None:
        """
        查询电视剧订阅缺失剧集
        """
        if not rid:
            return []
        with self.session() as db:
            ret = db.query(SubscribeTvEpisodes.EPISODES).filter(cast(SubscribeTvEpisodes.RSSID, Integer) == rid).first()
            if ret:
                return [int(epi) for epi in str(ret[0]).split(",")]
            return None

    def delete_rss_tv_episodes(self, rid: int | None) -> None:
        """
        删除电视剧订阅缺失剧集
        """
        if not rid:
            return
        with self.session() as db:
            db.query(SubscribeTvEpisodes).filter(cast(SubscribeTvEpisodes.RSSID, Integer) == int(rid)).delete()

    def truncate_rss_episodes(self) -> None:
        """
        清空 RSS 剧集记录（仅清理已完成/失效的订阅关联记录，保护活跃订阅进度）
        """
        with self.session() as db:
            active_ids = {
                row[0]
                for row in db.query(SubscribeTvs.ID)
                .filter(
                    SubscribeTvs.STATE.in_(
                        [SubscribeState.RUNNING.value, SubscribeState.PENDING.value, SubscribeState.SEARCHING.value]
                    )
                )
                .all()
            }
            query = db.query(SubscribeTvEpisodes)
            if active_ids:
                query = query.filter(~cast(SubscribeTvEpisodes.RSSID, Integer).in_(active_ids))
            query.delete(synchronize_session=False)

    # ==================== RSS History ====================

    def get_rss_history(
        self,
        rtype: str | None = None,
        rid: int | None = None,
        user: UserContext | None = None,
        content_profile: str | None = None,
    ) -> list[SubscribeHistory]:
        """
        查询RSS历史（user=None 为系统上下文不过滤；否则按数据归属过滤）
        """
        with self.session() as db:
            query = db.query(SubscribeHistory)
            if rid:
                query = query.filter(SubscribeHistory.ID == int(rid))
            elif rtype:
                query = query.filter(SubscribeHistory.TYPE == rtype)
            if content_profile:
                if content_profile in ("default", "core"):
                    query = query.filter(
                        or_(
                            SubscribeHistory.CONTENT_PROFILE.is_(None),
                            SubscribeHistory.CONTENT_PROFILE == "",
                            SubscribeHistory.CONTENT_PROFILE == "default",
                        )
                    )
                else:
                    query = query.filter(SubscribeHistory.CONTENT_PROFILE == content_profile)
            if user is not None:
                query = apply_owner_scope(query, SubscribeHistory, user)
            return query.order_by(SubscribeHistory.FINISH_TIME.desc()).all()

    def get_rss_history_id(self, rtype: str | None, title: str, year: str | None = None, tmdbid: str | None = None):
        """按 TMDB/标题查询已完成的订阅历史 ID（用于展示"订阅完成"状态）."""
        if not title:
            return None
        with self.session() as db:
            query = db.query(SubscribeHistory.ID)
            if rtype:
                query = query.filter(SubscribeHistory.TYPE == rtype)
            if tmdbid:
                ret = query.filter(SubscribeHistory.TMDBID == str(tmdbid)).first()
                if ret:
                    return ret[0]
            ret = query.filter(SubscribeHistory.NAME == title)
            if year:
                ret = ret.filter(SubscribeHistory.YEAR == str(year))
            row = ret.first()
            if row:
                return row[0]
            return self._fuzzy_subscribe_id(db, SubscribeHistory, title, year)

    def is_exists_rss_history(self, rssid: int | None) -> bool:
        """
        判断RSS历史是否存在
        """
        if not rssid:
            return False
        with self.session() as db:
            count = db.query(SubscribeHistory).filter(cast(SubscribeHistory.RSSID, Integer) == rssid).count()
            return count > 0

    def check_rss_history(self, type_str: str, name: str, year: str, season: str) -> bool:
        """
        检查RSS历史是否存在
        """
        with self.session() as db:
            count = (
                db.query(SubscribeHistory)
                .filter(
                    SubscribeHistory.TYPE == type_str,
                    SubscribeHistory.NAME == name,
                    SubscribeHistory.YEAR == year,
                    SubscribeHistory.SEASON == season,
                )
                .count()
            )
            return count > 0

    def insert_rss_history(
        self,
        rssid: int,
        rtype: str,
        name: str,
        year: str,
        tmdbid: str,
        image: str,
        desc: str,
        season: str | None = None,
        total: str | None = None,
        start: str | None = None,
        note: str = "",
        user_id: int | None = None,
        *,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        identity_id: str | None = None,
        content_profile: str | None = None,
        provider: str | None = None,
        metadata_ref: str | None = None,
        metadata_policy: str | None = None,
        naming_profile: str | None = None,
    ) -> None:
        """
        登记RSS历史（user_id 为归属用户）
        """
        # SEASON/TOTAL/START 为 NOT NULL：电影等无季/集信息时兜底为空串/0，避免约束失败
        season = season or ""
        total = "0" if total is None else str(total)
        start = "0" if start is None else str(start)
        scope = _history_scope(
            tmdbid,
            rtype,
            anchor_provider=anchor_provider,
            anchor_external_id=anchor_external_id,
            identity_id=identity_id,
            content_profile=content_profile,
            provider=provider,
            metadata_ref=metadata_ref,
            metadata_policy=metadata_policy,
            naming_profile=naming_profile,
        )
        with self.session() as db:
            if db.query(SubscribeHistory).filter(cast(SubscribeHistory.RSSID, Integer) == rssid).count() > 0:
                return
            db.add(
                SubscribeHistory(
                    TYPE=rtype,
                    RSSID=rssid,
                    NAME=name,
                    YEAR=year,
                    TMDBID=tmdbid,
                    SEASON=season,
                    IMAGE=image,
                    DESC=_trim_desc(desc),
                    TOTAL=total,
                    START=start,
                    NOTE=note,
                    FINISH_TIME=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                    USER_ID=user_id,
                    **scope,
                )
            )

    def upsert_rss_history(
        self,
        rssid: int,
        rtype: str,
        name: str,
        year: str,
        tmdbid: str,
        image: str,
        desc: str,
        season: str | None = None,
        total: str | None = None,
        start: str | None = None,
        note: str = "",
        user_id: int | None = None,
        *,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        identity_id: str | None = None,
        content_profile: str | None = None,
        provider: str | None = None,
        metadata_ref: str | None = None,
        metadata_policy: str | None = None,
        naming_profile: str | None = None,
    ) -> None:
        """
        登记或更新RSS历史：按媒体维度去重，同一 TMDB ID + 季的记录只保留一条
        """
        # SEASON/TOTAL/START 为 NOT NULL：电影等无季/集信息时兜底为空串/0，避免约束失败
        season = season or ""
        total = "0" if total is None else str(total)
        start = "0" if start is None else str(start)
        scope = _history_scope(
            tmdbid,
            rtype,
            anchor_provider=anchor_provider,
            anchor_external_id=anchor_external_id,
            identity_id=identity_id,
            content_profile=content_profile,
            provider=provider,
            metadata_ref=metadata_ref,
            metadata_policy=metadata_policy,
            naming_profile=naming_profile,
        )
        with self.session() as db:
            # 防御：同一 rssid 已完成过则跳过
            if db.query(SubscribeHistory).filter(cast(SubscribeHistory.RSSID, Integer) == rssid).count() > 0:
                return

            query = db.query(SubscribeHistory).filter(
                SubscribeHistory.TYPE == rtype,
            )
            if user_id is not None:
                query = query.filter(SubscribeHistory.USER_ID == user_id)
            if season:
                query = query.filter(SubscribeHistory.SEASON == season)
            else:
                query = query.filter(
                    or_(
                        SubscribeHistory.SEASON == None,  # noqa: E711
                        SubscribeHistory.SEASON == "",
                    )
                )
            if tmdbid:
                query = query.filter(SubscribeHistory.TMDBID == tmdbid)
            elif anchor_external_id:
                # 多数据源下同一番号可能来自不同 provider，按锚点去重而不是标题。
                query = query.filter(SubscribeHistory.ANCHOR_EXTERNAL_ID == anchor_external_id)
                if content_profile:
                    query = query.filter(SubscribeHistory.CONTENT_PROFILE == content_profile)
            elif identity_id:
                query = query.filter(SubscribeHistory.IDENTITY_ID == identity_id)
            else:
                query = query.filter(
                    SubscribeHistory.NAME == name,
                    SubscribeHistory.YEAR == year,
                )

            existing = query.first()
            finish_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
            if existing:
                existing.RSSID = str(rssid or "")
                existing.IMAGE = image
                existing.DESC = _trim_desc(desc)
                existing.TOTAL = int(total or 0)
                existing.START = int(start or 0)
                existing.NOTE = note
                existing.FINISH_TIME = finish_time
                for key, value in scope.items():
                    if value is not None:
                        setattr(existing, key, value)
            else:
                db.add(
                    SubscribeHistory(
                        TYPE=rtype,
                        RSSID=rssid,
                        NAME=name,
                        YEAR=year,
                        TMDBID=tmdbid,
                        SEASON=season,
                        IMAGE=image,
                        DESC=_trim_desc(desc),
                        TOTAL=total,
                        START=start,
                        NOTE=note,
                        FINISH_TIME=finish_time,
                        USER_ID=user_id,
                        **scope,
                    )
                )

    def delete_rss_history(self, rssid: int | None) -> None:
        """
        删除RSS历史
        """
        if not rssid:
            return
        with self.session() as db:
            db.query(SubscribeHistory).filter(SubscribeHistory.ID == int(rssid)).delete()

    # ==================== RSS Torrents ====================

    def get_rss_torrent_by_enclosure(self, enclosure: str) -> SubscribeTorrents | None:
        """根据 enclosure 获取 RSS 种子记录"""
        if not enclosure:
            return None
        with self.session() as db:
            return db.query(SubscribeTorrents).filter(SubscribeTorrents.ENCLOSURE == enclosure).first()

    def get_rss_torrent_by_name(self, torrent_name: str) -> SubscribeTorrents | None:
        """根据 torrent_name 获取 RSS 种子记录"""
        if not torrent_name:
            return None
        with self.session() as db:
            return db.query(SubscribeTorrents).filter(SubscribeTorrents.TORRENT_NAME == torrent_name).first()

    def insert_rss_torrent(
        self,
        torrent_name: str,
        enclosure: str,
        type_: str,
        title: str,
        year: str,
        season: str,
        episode: str,
        *,
        identity_id: str | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        content_profile: str | None = None,
    ) -> None:
        """插入 RSS 种子记录"""
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        with self.session() as db:
            db.add(
                SubscribeTorrents(
                    TORRENT_NAME=torrent_name,
                    ENCLOSURE=enclosure,
                    TYPE=type_,
                    TITLE=title,
                    YEAR=year,
                    SEASON=season,
                    EPISODE=episode,
                    IDENTITY_ID=identity_id,
                    ANCHOR_PROVIDER=anchor_provider,
                    ANCHOR_EXTERNAL_ID=anchor_external_id,
                    CONTENT_PROFILE=content_profile,
                )
            )

    def simple_insert_rss_torrent(self, title: str, enclosure: str) -> None:
        """简式插入 RSS 种子记录"""
        if enclosure and enclosure.startswith("magnet:"):
            enclosure = enclosure.split("&")[0]
        elif enclosure and len(enclosure) > 4000:
            enclosure = enclosure[:4000]
        with self.session() as db:
            db.add(
                SubscribeTorrents(
                    TORRENT_NAME=title,
                    ENCLOSURE=enclosure,
                )
            )

    def simple_delete_rss_torrent(self, title: str, enclosure: str | None = None) -> None:
        """删除 RSS 种子记录"""
        with self.session() as db:
            if enclosure:
                db.query(SubscribeTorrents).filter(
                    SubscribeTorrents.TORRENT_NAME == title,
                    SubscribeTorrents.ENCLOSURE == enclosure,
                ).delete()
            else:
                db.query(SubscribeTorrents).filter(SubscribeTorrents.TORRENT_NAME == title).delete()

    def truncate_rss_torrents(self) -> None:
        """清空 RSS 种子记录"""
        with self.session() as db:
            db.query(SubscribeTorrents).delete()
