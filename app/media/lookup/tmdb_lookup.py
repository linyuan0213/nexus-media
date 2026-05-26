import log
from app.helper.image_proxy_helper import ImageProxyHelper
from app.media.lookup.base import BaseLookup, LookupResult
from app.media.lookup.tmdb_client import TmdbClient
from app.media.lookup.tmdb_detail import TmdbDetail
from app.media.lookup.tmdb_discover import TmdbDiscover
from app.media.lookup.tmdb_person import TmdbPerson
from app.media.lookup.tmdb_search import TmdbSearch
from app.media.lookup.tmdb_season import TmdbSeason
from app.utils import StringUtils
from app.utils.types import MediaType


class TmdbLookup(BaseLookup):
    """TMDB 查询器 — 组合所有子模块"""

    def __init__(self):
        self.client = TmdbClient()
        self.search = TmdbSearch(self.client)
        self.detail = TmdbDetail(self.client)
        self.season = TmdbSeason(self.client)
        self.person = TmdbPerson(self.client)
        self.discover = TmdbDiscover(self.client)

    def lookup(
        self, parsed, hint_type: MediaType | None = None, strict: bool | None = None, language: str | None = None
    ) -> LookupResult | None:
        if not parsed.title_en and not parsed.title_cn:
            return None
        if language:
            self.client.set_language(language or "")
        search_type = hint_type or parsed.type or MediaType.UNKNOWN

        # 优先使用中文名搜索（中文搜索结果通常更精确，避免外传/主系列混淆）
        result = None
        if parsed.title_cn:
            result = self._lookup_tmdb(
                name=parsed.title_cn,
                search_type=search_type,
                first_year=parsed.year,
                media_year=parsed.year,
                season_number=parsed.season,
                episode=parsed.episode,
                strict=strict,
            )
        # 中文名搜索失败时，使用英文名搜索
        if not result and parsed.title_en:
            result = self._lookup_tmdb(
                name=parsed.title_en,
                search_type=search_type,
                first_year=parsed.year,
                media_year=parsed.year,
                season_number=parsed.season,
                episode=parsed.episode,
                strict=strict,
            )
        if not result:
            if language:
                self.client.set_language()
            return None
        if not result.get("genres"):
            result = self.detail.get_detail(result.get("id"), result.get("media_type", search_type))
        if language:
            self.client.set_language()
        return self._to_lookup_result(result)

    def _lookup_tmdb(
        self,
        name,
        search_type,
        first_year=None,
        media_year=None,
        season_number=None,
        episode=None,
        strict: bool | None = None,
    ):
        info = None
        # 1. 按指定类型搜索
        if search_type == MediaType.MOVIE:
            year_range = [first_year]
            if first_year:
                year_range.append(str(int(first_year) - 1))
            for year in year_range:
                log.debug(f"【Meta】正在识别{search_type.value}：{name}, 年份={year} ...")
                info = self.search.search_movie(name, year)
                if info:
                    info["media_type"] = MediaType.MOVIE
                    log.info(
                        "【Meta】{} 识别到 电影：TMDBID={}, 名称={}, 上映日期={}".format(
                            name, info.get("id"), info.get("title"), info.get("release_date")
                        )
                    )
                    return info
        else:
            if media_year and season_number:
                log.debug(
                    f"【Meta】正在识别{search_type.value}：{name}, 季集={season_number}, 季集年份={media_year} ..."
                )
                info = self.search.search_tv_by_season(name, media_year, season_number, episode)
                if info:
                    return info
            log.debug(f"【Meta】正在识别{search_type.value}：{name}, 年份={StringUtils.xstr(first_year)} ...")
            info = self.search.search_tv(name, first_year, season_number, episode)
            if info:
                info["media_type"] = MediaType.TV
                log.info(
                    "【Meta】{} 识别到 电视剧：TMDBID={}, 名称={}, 首播日期={}".format(
                        name, info.get("id"), info.get("name"), info.get("first_air_date")
                    )
                )
                return info
            # TV 查不到时，去掉年份再查（仅非严格模式）
            if not info and first_year and not strict:
                log.debug(f"【Meta】正在识别{search_type.value}：{name}, 去掉年份再查 ...")
                info = self.search.search_tv(name, None, season_number, episode)
                if info:
                    info["media_type"] = MediaType.TV
                    log.info(
                        "【Meta】{} 识别到 电视剧：TMDBID={}, 名称={}, 首播日期={}".format(
                            name, info.get("id"), info.get("name"), info.get("first_air_date")
                        )
                    )
                    return info

        # 2. Fallback: 多类型搜索
        if not info:
            log.debug(f"【Meta】正在识别：{name}, 多类型搜索 ...")
            info = self.search.search_multi(name)
            if info:
                info["media_type"] = (
                    MediaType.MOVIE if info.get("media_type") in ["movie", MediaType.MOVIE] else MediaType.TV
                )
                log.info("【Meta】{} 识别到 {}：TMDBID={}".format(name, info.get("media_type").value, info.get("id")))
                return info

        # 3. Fallback: 互换类型搜索（去掉年份）
        if not info and search_type != MediaType.UNKNOWN:
            log.debug(f"【Meta】正在识别：{name}, 互换类型搜索 ...")
            if search_type == MediaType.MOVIE:
                info = self.search.search_tv(name, None)
                if info:
                    info["media_type"] = MediaType.TV
                    return info
            else:
                info = self.search.search_movie(name, None)
                if info:
                    info["media_type"] = MediaType.MOVIE
                    return info

        if not info:
            log.info(
                "【Meta】{} 以年份 {} 在TMDB中未找到{}信息!".format(
                    name, StringUtils.xstr(first_year), search_type.value if search_type else ""
                )
            )
        return info or {}

    def _to_lookup_result(self, info: dict) -> LookupResult | None:
        if not info:
            return None
        external_ids = info.get("external_ids", {})
        if external_ids and not isinstance(external_ids, dict):
            try:
                external_ids = dict(external_ids)
            except Exception:
                external_ids = {}
        return LookupResult(
            tmdb_id=info.get("id", 0),
            title=info.get("title") or info.get("name"),
            original_title=info.get("original_title") or info.get("original_name"),
            media_type=info.get("media_type"),
            year=info.get("release_date", "")[:4] if info.get("release_date") else info.get("first_air_date", "")[:4],
            overview=info.get("overview"),
            poster_path=ImageProxyHelper.get_tmdbimage_url(info.get("poster_path")),
            backdrop_path=ImageProxyHelper.get_tmdbimage_url(info.get("backdrop_path")),
            vote_average=round(float(info.get("vote_average", 0)), 1),
            genres=info.get("genres", []),
            external_ids=external_ids,
        )

    # ---------- 代理方法 ----------

    def get_tmdb_info(self, mtype, tmdbid, language=None, append_to_response=None, chinese=True):
        if language:
            self.client.set_language(language or "")
        result = self.detail.get_detail(tmdbid, mtype, append_to_response=append_to_response)
        if language:
            self.client.set_language()
        return result

    def get_tmdb_tv_seasons(self, tv_info):
        return self.season.get_seasons(tv_info)

    def get_tmdb_tv_seasons_byid(self, tmdbid):
        return self.season.get_seasons_byid(tmdbid)

    def get_tmdb_season_episodes(self, tmdbid, season):
        return self.season.get_episodes(tmdbid, season)

    def get_tmdb_backdrop(self, mtype, tmdbid):
        return self.detail.get_backdrop(mtype, tmdbid)

    def get_tmdb_backdrops(self, tmdbinfo, original=True):
        return self.detail.get_backdrops(tmdbinfo, original)

    def search_tmdb_person(self, name):
        return self.person.search(name)

    def get_tmdbperson_chinese_name(self, person_id=None, person_info=None):
        return self.person.get_chinese_name(person_id, person_info)

    def get_tmdbperson_aka_names(self, person_id):
        return self.person.get_aka_names(person_id)

    def get_movie_similar(self, tmdbid, page=1):
        return self.discover.get_movie_similar(tmdbid, page)

    def get_movie_recommendations(self, tmdbid, page=1):
        return self.discover.get_movie_recommendations(tmdbid, page)

    def get_tv_similar(self, tmdbid, page=1):
        return self.discover.get_tv_similar(tmdbid, page)

    def get_tv_recommendations(self, tmdbid, page=1):
        return self.discover.get_tv_recommendations(tmdbid, page)

    def get_tmdb_discover(self, mtype, params=None, page=1):
        return self.discover.discover(mtype, params, page)

    def get_tmdb_en_title(self, media_info):
        en_info = self.detail.get_detail(media_info.tmdb_id, media_info.type)
        if en_info:
            return en_info.get("title") if media_info.type == MediaType.MOVIE else en_info.get("name")
        return None

    def get_tmdb_zhtw_title(self, media_info):
        zhtw_info = self.detail.get_detail(media_info.tmdb_id, media_info.type)
        if zhtw_info:
            return zhtw_info.get("title") if media_info.type == MediaType.MOVIE else zhtw_info.get("name")
        return None

    def get_tmdbid_by_imdbid(self, imdbid):
        if not self.client.find:
            return None
        try:
            result = self.client.find.find_by_imdbid(imdbid) or {}
            if result:
                if result.get("movie_results"):
                    return result["movie_results"][0].get("id")
                elif result.get("tv_results"):
                    return result["tv_results"][0].get("id")
        except Exception as err:
            print(str(err))
        return None

    def get_random_discover_backdrop(self):
        return self.discover.get_random_backdrop()

    def get_tmdb_infos(self, title, year=None, mtype=None, language=None, page=1):
        if not self.client.tmdb:
            log.error("【Meta】TMDB API Key 未设置！")
            return []
        if not title:
            return []
        self.client.set_language(language or "")
        if not mtype and not year:
            results = self.search.search_multi_infos(title)
        else:
            if not mtype:
                results = list(
                    set(self.search.search_movie_infos(title, year)).union(
                        set(self.search.search_tv_infos(title, year))
                    )
                )
                results = sorted(
                    results,
                    key=lambda x: x.get("release_date") or x.get("first_air_date") or "0000-00-00",
                    reverse=True,
                )
            elif mtype == MediaType.MOVIE:
                results = self.search.search_movie_infos(title, year)
            else:
                results = self.search.search_tv_infos(title, year)
        self.client.set_language()
        return results[(page - 1) * 20 : page * 20]

    def get_tmdb_tv_season_detail(self, tmdbid, season):
        return self.detail.get_season_detail(tmdbid, season)

    def get_tmdb_hot_movies(self, page):
        return self.discover.get_tmdb_hot_movies(page)

    def get_tmdb_hot_tvs(self, page):
        return self.discover.get_tmdb_hot_tvs(page)

    def get_tmdb_new_movies(self, page):
        return self.discover.get_tmdb_new_movies(page)

    def get_tmdb_new_tvs(self, page):
        return self.discover.get_tmdb_new_tvs(page)

    def get_tmdb_upcoming_movies(self, page):
        return self.discover.get_tmdb_upcoming_movies(page)

    def get_tmdb_trending_all_week(self, page=1):
        return self.discover.get_tmdb_trending_all_week(page)

    def get_tmdb_cats(self, mtype, tmdbid):
        try:
            if mtype == MediaType.MOVIE:
                if not self.client.movie:
                    return []
                return self._dict_media_casts(self.client.movie.credits(tmdbid).get("cast"))
            else:
                if not self.client.tv:
                    return []
                return self._dict_media_casts(self.client.tv.credits(tmdbid).get("cast"))
        except Exception as err:
            print(str(err))
        return []

    def get_tmdb_genres_names(self, tmdbinfo):
        if not tmdbinfo:
            return ""
        genres = tmdbinfo.get("genres") or []
        genres_list = [genre.get("name") for genre in genres]
        return ", ".join(genres_list) if genres_list else ""

    def get_tmdb_genres(self, mtype):
        if not self.client.genre:
            return []
        try:
            if mtype == MediaType.MOVIE:
                return self.client.genre.movie_list()
            else:
                return self.client.genre.tv_list()
        except Exception as err:
            print(str(err))
        return []

    def get_tmdb_production_company_names(self, tmdbinfo):
        if not tmdbinfo:
            return ""
        companies = tmdbinfo.get("production_companies") or []
        companies_list = [company.get("name") for company in companies]
        return ", ".join(companies_list) if companies_list else ""

    def get_tmdb_crews(self, tmdbinfo, nums=None):
        if not tmdbinfo:
            return ""
        crews = tmdbinfo.get("credits", {}).get("crew") or []
        result = [{crew.get("name"): crew.get("job")} for crew in crews]
        if nums:
            return result[:nums]
        return result

    def get_tmdb_season_episodes_num(self, tv_info, season):
        if not tv_info:
            return 0
        seasons = tv_info.get("seasons")
        if not seasons:
            return 0
        for sea in seasons:
            if sea.get("season_number") == int(season):
                return int(sea.get("episode_count"))
        return 0

    def get_tmdb_directors_actors(self, tmdbinfo):
        if not tmdbinfo:
            return [], []
        _credits = tmdbinfo.get("credits")
        if not _credits:
            return [], []
        directors = []
        actors = []
        for cast in self._dict_media_casts(_credits.get("cast")):
            if cast.get("known_for_department") == "Acting":
                actors.append(cast)
        for crew in self._dict_media_crews(_credits.get("crew")):
            if crew.get("job") == "Director":
                directors.append(crew)
        return directors, actors

    def get_episode_title(self, media_info, language=None):
        if media_info.type == MediaType.MOVIE:
            return None
        self.client.set_language(language or "")
        if media_info.tmdb_id:
            if not media_info.begin_episode:
                self.client.set_language()
                return None
            episodes = self.get_tmdb_season_episodes(tmdbid=media_info.tmdb_id, season=int(media_info.get_season_seq()))
            self.client.set_language()
            for episode in episodes:
                if episode.get("episode_number") == media_info.begin_episode:
                    return episode.get("name")
        self.client.set_language()
        return None

    def get_episode_images(self, tv_id, season_id, episode_id, orginal=False):
        if not self.client.tv:
            return ""
        try:
            episode = self.client.tv.episode(tv_id, season_id, episode_id)  # type: ignore[attr-defined]
            if episode:
                still_path = episode.get("still_path")
                if still_path:
                    return ImageProxyHelper.get_tmdbimage_url(still_path, prefix="original" if orginal else "w500")
        except Exception as e:
            print(str(e))
        return ""

    def get_tmdb_factinfo(self, media_info):
        if not media_info or not media_info.tmdb_info:
            return ""
        tmdbinfo = media_info.tmdb_info
        media_type = media_info.type
        if media_type == MediaType.MOVIE:
            title = tmdbinfo.get("title", "")
            release_date = tmdbinfo.get("release_date", "")
            year = release_date[:4] if release_date else ""
            runtime = tmdbinfo.get("runtime", 0)
            runtime_str = f"{runtime} 分钟" if runtime else ""
            genres = self.get_tmdb_genres_names(tmdbinfo)
            countries = self.get_tmdb_production_country_names(tmdbinfo)
            companies = self.get_tmdb_production_company_names(tmdbinfo)
            parts = [f"{title} ({year})", genres, countries, companies, runtime_str]
            return " | ".join(filter(None, parts))
        else:
            name = tmdbinfo.get("name", "")
            first_air_date = tmdbinfo.get("first_air_date", "")
            year = first_air_date[:4] if first_air_date else ""
            number_of_episodes = tmdbinfo.get("number_of_episodes", 0)
            number_of_seasons = tmdbinfo.get("number_of_seasons", 0)
            episode_str = f"{number_of_episodes} 集 / {number_of_seasons} 季" if number_of_episodes else ""
            genres = self.get_tmdb_genres_names(tmdbinfo)
            countries = self.get_tmdb_production_country_names(tmdbinfo)
            companies = self.get_tmdb_production_company_names(tmdbinfo)
            parts = [f"{name} ({year})", genres, countries, companies, episode_str]
            return " | ".join(filter(None, parts))

    def get_tmdb_production_country_names(self, tmdbinfo):
        if not tmdbinfo:
            return ""
        countries = tmdbinfo.get("production_countries") or []
        countries_list = [country.get("name") for country in countries]
        return ", ".join(countries_list) if countries_list else ""

    def get_tmdb_discover_movies_pages(self, params=None):
        if not self.client.discover:
            return 0
        try:
            return self.client.discover.discover_movies_pages(params=params)
        except Exception as e:
            print(str(e))
        return 0

    def get_person_medias(self, personid, mtype=None, page=1):
        if not self.client.person:
            return []
        try:
            if mtype == MediaType.MOVIE:
                movies = self.client.person.movie_credits(person_id=personid) or []
                return self._dict_tmdbinfos(movies, mtype)
            elif mtype:
                tvs = self.client.person.tv_credits(person_id=personid) or []
                return self._dict_tmdbinfos(tvs, mtype)
            else:
                medias = self.client.person.combined_credits(person_id=personid) or []
                return self._dict_tmdbinfos(medias)
        except Exception as err:
            print(str(err))
        return []

    @staticmethod
    def merge_media_info(target, source):
        if not target or not source:
            return target
        target.title = source.title or target.title
        target.tmdb_id = source.tmdb_id or target.tmdb_id
        target.tmdb_info = source.tmdb_info or target.tmdb_info
        target.type = source.type or target.type
        target.year = source.year or target.year
        return target

    @staticmethod
    def get_detail_url(mtype, tmdbid):
        if not tmdbid:
            return ""
        if mtype == MediaType.MOVIE:
            return f"https://www.themoviedb.org/movie/{tmdbid}"
        return f"https://www.themoviedb.org/tv/{tmdbid}"

    @staticmethod
    def _dict_media_crews(crews):
        return [
            {
                "id": crew.get("id"),
                "gender": crew.get("gender"),
                "known_for_department": crew.get("known_for_department"),
                "name": crew.get("name"),
                "original_name": crew.get("original_name"),
                "popularity": crew.get("popularity"),
                "image": ImageProxyHelper.get_tmdbimage_url(crew.get("profile_path"), prefix="h632"),
                "credit_id": crew.get("credit_id"),
                "department": crew.get("department"),
                "job": crew.get("job"),
                "profile": "https://www.themoviedb.org/person/{}".format(crew.get("id")),
            }
            for crew in crews or []
        ]

    @staticmethod
    def _dict_media_casts(casts):
        return [
            {
                "id": cast.get("id"),
                "gender": cast.get("gender"),
                "known_for_department": cast.get("known_for_department"),
                "name": cast.get("name"),
                "original_name": cast.get("original_name"),
                "popularity": cast.get("popularity"),
                "image": ImageProxyHelper.get_tmdbimage_url(cast.get("profile_path"), prefix="h632"),
                "cast_id": cast.get("cast_id"),
                "role": cast.get("character"),
                "credit_id": cast.get("credit_id"),
                "order": cast.get("order"),
                "profile": "https://www.themoviedb.org/person/{}".format(cast.get("id")),
            }
            for cast in casts or []
        ]

    @staticmethod
    def _dict_tmdbinfos(infos, mtype=None):
        if not infos:
            return []
        ret_infos = []
        for info in infos:
            tmdbid = info.get("id")
            vote = round(float(info.get("vote_average")), 1) if info.get("vote_average") else 0
            image = ImageProxyHelper.get_tmdbimage_url(info.get("poster_path"))
            overview = info.get("overview")
            if mtype:
                media_type = mtype.value
                year = (
                    info.get("release_date")[0:4]
                    if info.get("release_date") and mtype == MediaType.MOVIE
                    else info.get("first_air_date")[0:4]
                    if info.get("first_air_date")
                    else ""
                )
                typestr = "MOV" if mtype == MediaType.MOVIE else "TV"
                title = info.get("title") if mtype == MediaType.MOVIE else info.get("name")
            else:
                media_type = MediaType.MOVIE.value if info.get("media_type") == "movie" else MediaType.TV.value
                year = (
                    info.get("release_date")[0:4]
                    if info.get("release_date") and info.get("media_type") == "movie"
                    else info.get("first_air_date")[0:4]
                    if info.get("first_air_date")
                    else ""
                )
                typestr = "MOV" if info.get("media_type") == "movie" else "TV"
                title = info.get("title") if info.get("media_type") == "movie" else info.get("name")
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
                }
            )
        return ret_infos
