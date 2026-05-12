from typing import Optional

from pydantic import BaseModel

from app.utils.types import MediaType


class LookupResult(BaseModel):
    """外部数据库查询结果"""

    tmdb_id: int = 0
    title: Optional[str] = None
    original_title: Optional[str] = None
    media_type: Optional[MediaType] = None
    year: Optional[str] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: float = 0.0
    genres: list = []
    external_ids: dict = {}


class BaseLookup:
    """查询器基类"""

    def lookup(self, parsed, hint_type: MediaType = None) -> Optional[LookupResult]:
        raise NotImplementedError
