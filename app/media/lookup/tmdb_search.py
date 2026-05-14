from concurrent.futures import ThreadPoolExecutor, as_completed

from lxml import etree

import log
from app.infrastructure.external.tmdbv3api import TMDbException
from app.media.lookup.tmdb_client import TmdbClient, compare_tmdb_names
from app.media.lookup.tmdb_detail import TmdbDetail
from app.utils import RequestUtils, StringUtils
from app.utils.types import MediaType


class TmdbSearch:
    """TMDB 搜索封装"""

    def __init__(self, client: TmdbClient):
        self.client = client

    def search_movie(self, name, year=None):
        try:
            params = {"query": name}
            if year:
                params["year"] = year
            movies = self.client.search.movies(params)
            blacklist = [str(item.TMDB_ID) for item in self.client.get_blacklist()]
            if movies and blacklist:
                movies = [m for m in movies if not (m.get('id') and str(m.get('id')) in blacklist)]
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return None
        if not movies:
            return {}
        # 第一轮：优先匹配 original_title 完全相等
        for movie in movies:
            if not movie.get('release_date'):
                continue
            year_matched = not year or movie.get('release_date', '')[:4] == str(year)
            if not year_matched:
                continue
            original = movie.get('original_title')
            if original and StringUtils.handler_special_chars(original).strip().upper() == StringUtils.handler_special_chars(name).strip().upper():
                return movie
        # 第二轮：模糊匹配 title / original_title
        for movie in movies:
            if not movie.get('release_date'):
                continue
            year_matched = not year or movie.get('release_date', '')[:4] == str(year)
            if not year_matched:
                continue
            if (compare_tmdb_names(name, movie.get('title')) or
                compare_tmdb_names(name, movie.get('original_title'))):
                return movie
        return self._fuzzy_match_movie(name, year, movies)

    def _fuzzy_match_movie(self, name, year, movies):
        candidates = [m for m in movies[:5] if not year or m.get('release_date', '')[:4] == str(year)]
        if not candidates:
            return {}
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(candidates), 5)) as executor:
            future_to_movie = {
                executor.submit(lambda m: (m, self._fetch_allnames(MediaType.MOVIE, m.get("id"))), m): m
                for m in candidates
            }
            for future in as_completed(future_to_movie):
                movie = future_to_movie[future]
                try:
                    results[movie.get("id")] = future.result()
                except Exception as err:
                    log.error(f"【Meta】获取电影详情出错: {err}")
        for movie in candidates:
            res = results.get(movie.get("id"))
            if res:
                _, (info, names) = res
                if compare_tmdb_names(name, names):
                    return info
        return {}

    def search_tv(self, name, year=None, season_number=None, episode=None):
        try:
            params = {"query": name}
            if year:
                params["first_air_date_year"] = year
            tvs = self.client.search.tv_shows(params)
            blacklist = [str(item.TMDB_ID) for item in self.client.get_blacklist()]
            if tvs and blacklist:
                tvs = [t for t in tvs if not (t.get('id') and str(t.get('id')) in blacklist)]
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return None
        if not tvs:
            return {}

        def _episode_valid(tv_info):
            """验证作品集数是否足够容纳目标集号（高集号动漫专用）"""
            if not episode or episode <= 50:
                return True
            detail = self._get_detail(tv_info.get('id'), MediaType.TV)
            ep_count = detail.get('number_of_episodes', 0) if detail else 0
            if ep_count < episode:
                log.debug(f"【Meta】{tv_info.get('name')} 集数({ep_count})不足({episode})，跳过")
                return False
            return True

        # 第一轮：收集所有精确匹配项，优先返回 anime（genre_ids 含 16）
        exact_matches = []
        for tv in tvs:
            if not tv.get('first_air_date'):
                continue
            year_matched = not year or tv.get('first_air_date', '')[:4] == str(year)
            if not year_matched:
                continue
            original = tv.get('original_name')
            is_exact = original and StringUtils.handler_special_chars(original).strip().upper() == StringUtils.handler_special_chars(name).strip().upper()
            is_fuzzy = compare_tmdb_names(name, tv.get('name')) or compare_tmdb_names(name, tv.get('original_name'))
            if is_exact or is_fuzzy:
                if season_number and not self._tv_has_season(tv.get('id'), season_number):
                    continue
                if _episode_valid(tv):
                    exact_matches.append(tv)
        if exact_matches:
            # 优先返回 anime（genre_ids 包含 16 = Animation）
            for tv in exact_matches:
                if 16 in (tv.get('genre_ids') or []):
                    return tv
            return exact_matches[0]
        return self._fuzzy_match_tv(name, year, tvs, season_number, episode)

    def _fuzzy_match_tv(self, name, year, tvs, season_number=None, episode=None):
        candidates = [t for t in tvs[:5] if not year or t.get('first_air_date', '')[:4] == str(year)]
        if not candidates:
            return {}
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(candidates), 5)) as executor:
            future_to_tv = {
                executor.submit(lambda t: (t, self._fetch_allnames(MediaType.TV, t.get("id"))), t): t
                for t in candidates
            }
            for future in as_completed(future_to_tv):
                tv = future_to_tv[future]
                try:
                    results[tv.get("id")] = future.result()
                except Exception as err:
                    log.error(f"【Meta】获取剧集详情出错: {err}")
        fuzzy_matches = []
        for tv in candidates:
            res = results.get(tv.get("id"))
            if res:
                _, (info, names) = res
                if compare_tmdb_names(name, names):
                    if season_number and not self._tv_has_season(tv.get('id'), season_number):
                        continue
                    if episode and episode > 50 and info:
                        ep_count = info.get('number_of_episodes', 0)
                        if ep_count < episode:
                            log.debug(f"【Meta】{info.get('name')} 集数({ep_count})不足({episode})，跳过")
                            continue
                    fuzzy_matches.append(info)
        if fuzzy_matches:
            for info in fuzzy_matches:
                if 16 in (info.get('genre_ids') or []):
                    return info
            return fuzzy_matches[0]
        return {}

    def _tv_has_season(self, tmdb_id, season_number):
        """检查 TV 是否有指定的季"""
        try:
            tv_info = self._get_detail(tmdb_id, MediaType.TV)
            if not tv_info:
                return False
            seasons = tv_info.get("seasons") or []
            return any(
                s.get("season_number") == int(season_number) and s.get("episode_count", 0) > 0
                for s in seasons
            )
        except Exception:
            return False

    def search_tv_by_season(self, name, media_year, season_number, episode=None):
        def _season_match(tv_info, season_year):
            if not tv_info:
                return False
            try:
                seasons = tv_info.get("seasons") or []
                return any(
                    s.get("air_date", "")[:4] == str(season_year)
                    and s.get("season_number") == int(season_number)
                    for s in seasons
                )
            except Exception as e:
                log.error(f"【Meta】连接TMDB出错：{e}")
                return False

        def _episode_valid(tv_info):
            if not episode or episode <= 50:
                return True
            ep_count = tv_info.get('number_of_episodes', 0) if tv_info else 0
            if ep_count < episode:
                log.debug(f"【Meta】{tv_info.get('name')} 集数({ep_count})不足({episode})，跳过")
                return False
            return True

        try:
            tvs = self.client.search.tv_shows({"query": name})
            blacklist = [str(item.TMDB_ID) for item in self.client.get_blacklist()]
            if tvs and blacklist:
                tvs = [t for t in tvs if not (t.get('id') and str(t.get('id')) in blacklist)]
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return None
        if not tvs:
            return {}
        for tv in tvs:
            if (compare_tmdb_names(name, tv.get('name')) or
                compare_tmdb_names(name, tv.get('original_name'))) and \
               tv.get('first_air_date', '')[:4] == str(media_year):
                detail = self._get_detail(tv.get('id'), MediaType.TV)
                if _episode_valid(detail):
                    return tv
        candidates = tvs[:5]
        if not candidates:
            return {}
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(candidates), 5)) as executor:
            future_to_tv = {
                executor.submit(lambda t: (t, self._fetch_allnames(MediaType.TV, t.get("id"))), t): t
                for t in candidates
            }
            for future in as_completed(future_to_tv):
                tv = future_to_tv[future]
                try:
                    results[tv.get("id")] = future.result()
                except Exception as err:
                    log.error(f"【Meta】获取剧集详情出错: {err}")
        for tv in candidates:
            res = results.get(tv.get("id"))
            if res:
                _, (info, names) = res
                if compare_tmdb_names(name, names) and _season_match(info, media_year) and _episode_valid(info):
                    return info
        return {}

    def search_multi(self, name):
        try:
            multis = self.client.search.multi({"query": name}) or []
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return None
        if not multis:
            return {}
        tv_matches = []
        for multi in multis:
            if multi.get("media_type") == "movie":
                if (compare_tmdb_names(name, multi.get('title')) or
                    compare_tmdb_names(name, multi.get('original_title'))):
                    return multi
            elif multi.get("media_type") == "tv":
                if (compare_tmdb_names(name, multi.get('name')) or
                    compare_tmdb_names(name, multi.get('original_name'))):
                    tv_matches.append(multi)
        if tv_matches:
            for tv in tv_matches:
                if 16 in (tv.get('genre_ids') or []):
                    return tv
            return tv_matches[0]
        for multi in multis[:5]:
            if multi.get("media_type") == "movie":
                movie_info, names = self._fetch_allnames(MediaType.MOVIE, multi.get("id"))
                if compare_tmdb_names(name, names):
                    return movie_info
            elif multi.get("media_type") == "tv":
                tv_info, names = self._fetch_allnames(MediaType.TV, multi.get("id"))
                if compare_tmdb_names(name, names):
                    tv_matches.append(tv_info)
        if tv_matches:
            for tv in tv_matches:
                if 16 in (tv.get('genre_ids') or []):
                    return tv
            return tv_matches[0]
        return {}

    def search_multi_infos(self, name):
        """查询所有匹配的 movie/tv 结果（用于列表展示，不做名称匹配）"""
        if not name:
            return []
        try:
            multis = self.client.search.multi({"query": name}) or []
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return []
        ret_infos = []
        for multi in multis:
            if multi.get("media_type") in ["movie", "tv"]:
                multi['media_type'] = MediaType.MOVIE if multi.get("media_type") == "movie" else MediaType.TV
                ret_infos.append(multi)
        return ret_infos

    def search_movie_infos(self, name, year=None):
        """查询所有匹配的电影结果（用于列表展示）"""
        if not name:
            return []
        try:
            params = {"query": name}
            if year:
                params["year"] = year
            movies = self.client.search.movies(params) or []
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return []
        ret_infos = []
        for movie in movies:
            movie['media_type'] = MediaType.MOVIE
            ret_infos.append(movie)
        return ret_infos

    def search_tv_infos(self, name, year=None):
        """查询所有匹配的电视剧结果（用于列表展示）"""
        if not name:
            return []
        try:
            params = {"query": name}
            if year:
                params["first_air_date_year"] = year
            tvs = self.client.search.tv_shows(params) or []
        except (TMDbException, Exception) as err:
            log.error(f"【Meta】连接TMDB出错：{str(err)}")
            return []
        ret_infos = []
        for tv in tvs:
            tv['media_type'] = MediaType.TV
            ret_infos.append(tv)
        return ret_infos

    def search_web(self, name, mtype: MediaType):
        if not name or StringUtils.is_chinese(name):
            return None
        log.info(f"【Meta】正在从TheDbMovie网站查询：{name}...")
        tmdb_url = f"https://www.themoviedb.org/search?query={name}"
        res = RequestUtils(timeout=5).get_res(url=tmdb_url)
        if not res or res.status_code != 200 or not res.text:
            return None
        try:
            html = etree.HTML(res.text)
            xpath = ("//a[@data-id and @data-media-type='tv']/@href"
                     if mtype == MediaType.TV
                     else "//a[@data-id]/@href")
            tmdb_links = [
                link for link in html.xpath(xpath)
                if link and (link.startswith("/tv") or link.startswith("/movie"))
            ]
            if len(tmdb_links) != 1:
                log.info(f"【Meta】{name} TMDB网站返回{'数据过多' if tmdb_links else '无'}结果")
                return None
            media_type = MediaType.TV if tmdb_links[0].startswith("/tv") else MediaType.MOVIE
            tmdbid = tmdb_links[0].split("/")[-1]
            tmdbinfo = self._get_detail(tmdbid, media_type)
            if not tmdbinfo or (mtype == MediaType.TV and tmdbinfo.get('media_type') != MediaType.TV):
                return None
            log.info(
                f"【Meta】{name} 从WEB识别到 {'电影' if media_type == MediaType.MOVIE else '电视剧'}："
                f"TMDBID={tmdbinfo.get('id')}, "
                f"名称={tmdbinfo.get('title' if media_type == MediaType.MOVIE else 'name')}, "
                f"日期={tmdbinfo.get('release_date' if media_type == MediaType.MOVIE else 'first_air_date')}"
            )
            return tmdbinfo
        except Exception as err:
            log.error(f"【Meta】TMDB网站查询出错：{str(err)}")
            return None

    def _fetch_allnames(self, mtype, tmdb_id):
        if not mtype or not tmdb_id:
            return {}, []
        ret_names = []
        tmdb_info = self._get_detail(tmdb_id, mtype)
        if not tmdb_info:
            return tmdb_info, []
        if mtype == MediaType.MOVIE:
            for alt in tmdb_info.get("alternative_titles", {}).get("titles", []):
                title = alt.get("title")
                if title and title not in ret_names:
                    ret_names.append(title)
            for tr in tmdb_info.get("translations", {}).get("translations", []):
                title = tr.get("data", {}).get("title")
                if title and title not in ret_names:
                    ret_names.append(title)
        else:
            for alt in tmdb_info.get("alternative_titles", {}).get("results", []):
                name = alt.get("title")
                if name and name not in ret_names:
                    ret_names.append(name)
            for tr in tmdb_info.get("translations", {}).get("translations", []):
                name = tr.get("data", {}).get("name")
                if name and name not in ret_names:
                    ret_names.append(name)
        return tmdb_info, ret_names

    def _get_detail(self, tmdbid, mtype):
        return TmdbDetail(self.client).get_detail(tmdbid, mtype)
