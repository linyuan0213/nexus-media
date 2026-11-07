import random

import log
from app.domain.media_types import (
    ProviderMediaType,
    external_protocol_type,
    external_protocol_value,
    provider_media_type_of,
)
from app.infrastructure.image_proxy import ImageProxy
from app.media.lookup.tmdb_client import TmdbClient


class TmdbDiscover:
    """TMDB 推荐/发现"""

    def __init__(self, client: TmdbClient):
        self.client = client

    def get_movie_similar(self, tmdbid, page=1):
        if not self.client.movie:
            return []
        try:
            movies = self.client.movie.similar(movie_id=tmdbid, page=page) or []
            return self._dict_infos(movies, ProviderMediaType.MOVIE)
        except Exception as e:
            log.warn(f"[TmdbDiscover]获取相似电影失败: {e}")
            return []

    def get_movie_recommendations(self, tmdbid, page=1):
        if not self.client.movie:
            return []
        try:
            movies = self.client.movie.recommendations(movie_id=tmdbid, page=page) or []
            return self._dict_infos(movies, ProviderMediaType.MOVIE)
        except Exception as e:
            log.warn(f"[TmdbDiscover]获取电影推荐失败: {e}")
            return []

    def get_tv_similar(self, tmdbid, page=1):
        if not self.client.tv:
            return []
        try:
            tvs = self.client.tv.similar(tv_id=tmdbid, page=page) or []
            return self._dict_infos(tvs, ProviderMediaType.SERIES)
        except Exception as e:
            log.warn(f"[TmdbDiscover]获取相似电视剧失败: {e}")
            return []

    def get_tv_recommendations(self, tmdbid, page=1):
        if not self.client.tv:
            return []
        try:
            tvs = self.client.tv.recommendations(tv_id=tmdbid, page=page) or []
            return self._dict_infos(tvs, ProviderMediaType.SERIES)
        except Exception as e:
            log.warn(f"[TmdbDiscover]获取电视剧推荐失败: {e}")
            return []

    def discover(self, mtype, params=None, page=1):
        if not self.client.discover:
            return []
        provider_type = external_protocol_type(provider_media_type_of(mtype))
        try:
            if provider_type == ProviderMediaType.MOVIE:
                movies = self.client.discover.discover_movies(params=params, page=page)
                return self._dict_infos(infos=movies, mtype=provider_type, poster_filter=True)
            if provider_type == ProviderMediaType.SERIES:
                tvs = self.client.discover.discover_tv_shows(params=params, page=page)
                return self._dict_infos(infos=tvs, mtype=provider_type, poster_filter=True)
        except Exception as e:
            log.warn(f"[TmdbDiscover]发现内容失败: {e}")
        return []

    def get_tmdb_hot_movies(self, page):
        cached = self.client.redis_cache.get_trending("tmdb", "movie", "popular", page)
        if cached:
            log.debug(f"[Meta]从缓存获取热门电影，第 {page} 页")
            return cached
        if not self.client.movie:
            return []
        result = self._dict_infos(self.client.movie.popular(page), ProviderMediaType.MOVIE)
        if result:
            self.client.redis_cache.set_trending("tmdb", "movie", "popular", page, result)
        return result

    def get_tmdb_hot_tvs(self, page):
        cached = self.client.redis_cache.get_trending("tmdb", "tv", "popular", page)
        if cached:
            log.debug(f"[Meta]从缓存获取热门电视剧，第 {page} 页")
            return cached
        if not self.client.tv:
            return []
        result = self._dict_infos(self.client.tv.popular(page), ProviderMediaType.SERIES)
        if result:
            self.client.redis_cache.set_trending("tmdb", "tv", "popular", page, result)
        return result

    def get_tmdb_new_movies(self, page):
        cached = self.client.redis_cache.get_trending("tmdb", "movie", "now_playing", page)
        if cached:
            log.debug(f"[Meta]从缓存获取最新电影，第 {page} 页")
            return cached
        if not self.client.movie:
            return []
        try:
            result = self._dict_infos(self.client.movie.now_playing(page), ProviderMediaType.MOVIE)
        except Exception as e:
            log.warn(f"[TmdbDiscover]获取最新电影失败: {e}")
            return []
        if result:
            self.client.redis_cache.set_trending("tmdb", "movie", "now_playing", page, result)
        return result

    def get_tmdb_new_tvs(self, page):
        cached = self.client.redis_cache.get_trending("tmdb", "tv", "on_the_air", page)
        if cached:
            log.debug(f"[Meta]从缓存获取最新电视剧，第 {page} 页")
            return cached
        if not self.client.tv:
            return []
        try:
            result = self._dict_infos(self.client.tv.on_the_air(page), ProviderMediaType.SERIES)
        except Exception as e:
            log.warn(f"[TmdbDiscover]获取最新电视剧失败: {e}")
            return []
        if result:
            self.client.redis_cache.set_trending("tmdb", "tv", "on_the_air", page, result)
        return result

    def get_tmdb_upcoming_movies(self, page):
        cached = self.client.redis_cache.get_trending("tmdb", "movie", "upcoming", page)
        if cached:
            log.debug(f"[Meta]从缓存获取即将上映电影，第 {page} 页")
            return cached
        if not self.client.movie:
            return []
        result = self._dict_infos(self.client.movie.upcoming(page), ProviderMediaType.MOVIE)
        if result:
            self.client.redis_cache.set_trending("tmdb", "movie", "upcoming", page, result)
        return result

    def get_tmdb_trending_all_week(self, page=1):
        cached = self.client.redis_cache.get_trending("tmdb", "all", "week", page)
        if cached:
            log.debug(f"[Meta]从缓存获取本周趋势，第 {page} 页")
            return cached
        if not self.client.trending:
            return []
        result = self._dict_infos(self.client.trending.all_week(page=page))
        if result:
            self.client.redis_cache.set_trending("tmdb", "all", "week", page, result)
        return result

    def get_random_backdrop(self):
        if not self.client.discover:
            return "", "", ""
        try:
            medias = self.client.discover.discover_movies(params={"sort_by": "popularity.desc"})
            if medias:
                media = random.choice(medias)
                img_url = (
                    ImageProxy.get_tmdbimage_url(media.get("backdrop_path"), prefix="original")
                    if media.get("backdrop_path")
                    else ""
                )
                img_title = media.get("title", "")
                img_link = f"https://www.themoviedb.org/movie/{media.get('id')}" if media.get("id") else ""
                return img_url, img_title, img_link
        except Exception as err:
            log.warn(f"[TmdbDiscover]获取随机背景失败: {err}")
        return "", "", ""

    @staticmethod
    def _dict_infos(infos, mtype=None, poster_filter=False):
        if not infos:
            return []
        ret_infos = []
        for info in infos:
            tmdbid = info.get("id")
            vote = round(float(info.get("vote_average")), 1) if info.get("vote_average") else 0
            image = ImageProxy.get_tmdbimage_url(info.get("poster_path"))
            if poster_filter and not image:
                continue
            overview = info.get("overview")
            provider_type = provider_media_type_of(mtype or info.get("media_type"))
            is_movie = provider_type == ProviderMediaType.MOVIE
            media_type = provider_type.value
            year = (
                info.get("release_date")[0:4]
                if info.get("release_date") and is_movie
                else info.get("first_air_date")[0:4]
                if info.get("first_air_date")
                else ""
            )
            typestr = external_protocol_value(provider_type)
            title = info.get("title") if is_movie else info.get("name")
            ret_infos.append(
                {
                    "id": tmdbid,
                    "orgid": tmdbid,
                    "tmdbid": tmdbid,
                    "title": title,
                    "type": typestr,
                    "media_type": media_type,
                    "year": year,
                    "vote": vote,
                    "image": image,
                    "overview": overview,
                    "genre_ids": info.get("genre_ids") or [],
                    "origin_country": info.get("origin_country") or [],
                    "original_language": info.get("original_language") or "",
                }
            )
        return ret_infos
