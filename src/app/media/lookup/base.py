from pydantic import BaseModel

from app.domain.mediatypes import MediaType


class LookupResult(BaseModel):
    """外部数据库查询结果"""

    tmdb_id: int | str = 0
    title: str | None = None
    original_title: str | None = None
    media_type: MediaType | None = None
    year: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    vote_average: float = 0.0
    genres: list = []
    external_ids: dict = {}


class BaseLookup:
    """查询器基类"""

    def lookup(self, parsed, hint_type: MediaType | None = None) -> LookupResult | None:
        raise NotImplementedError
