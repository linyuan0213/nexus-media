from app.helper.image_proxy_helper import ImageProxyHelper
from app.media.lookup.tmdb_client import TmdbClient
from app.media.lookup.tmdb_detail import TmdbDetail


class TmdbSeason:
    """TMDB 季/集查询"""

    def __init__(self, client: TmdbClient):
        self.client = client
        self.detail = TmdbDetail(client)

    def get_seasons(self, tv_info):
        if not tv_info:
            return []
        ret_info = []
        for info in tv_info.get("seasons") or []:
            if not info.get("season_number"):
                continue
            ret_info.append(
                {
                    "air_date": info.get("air_date"),
                    "episode_count": info.get("episode_count"),
                    "id": info.get("id"),
                    "name": info.get("name"),
                    "overview": info.get("overview"),
                    "poster_path": ImageProxyHelper.get_tmdbimage_url(info.get("poster_path"))
                    if info.get("poster_path")
                    else "",
                    "season_number": info.get("season_number"),
                }
            )
        ret_info.reverse()
        return ret_info

    def get_seasons_byid(self, tmdbid):
        if not tmdbid:
            return []
        return self.get_seasons(tv_info=self.detail._get_tv_detail(tmdbid))

    def get_episodes(self, tmdbid, season: int):
        if not tmdbid:
            return []
        season_info = self.detail.get_season_detail(tmdbid=tmdbid, season=season)
        if not season_info:
            return []
        ret_info = []
        for info in season_info.get("episodes") or []:
            ret_info.append(
                {
                    "air_date": info.get("air_date"),
                    "episode_number": info.get("episode_number"),
                    "id": info.get("id"),
                    "name": info.get("name"),
                    "overview": info.get("overview"),
                    "production_code": info.get("production_code"),
                    "runtime": info.get("runtime"),
                    "season_number": info.get("season_number"),
                    "show_id": info.get("show_id"),
                    "still_path": ImageProxyHelper.get_tmdbimage_url(info.get("still_path"))
                    if info.get("still_path")
                    else "",
                    "vote_average": info.get("vote_average"),
                }
            )
        ret_info.reverse()
        return ret_info
