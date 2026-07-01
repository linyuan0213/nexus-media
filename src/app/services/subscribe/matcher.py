"""Subscribe matcher — 判断种子是否命中用户订阅清单."""

import re

from app.db.repositories.config_repo_adapter import FilterGroupRepositoryAdapter, FilterRuleRepositoryAdapter
from app.domain.mediatypes import MediaType
from app.indexer.core.filter_engine import IndexerFilterEngine
from app.sites.site_cache import SiteCache
from app.sites.siteconf import SiteConf


class SubscribeMatcher:
    """订阅匹配器.

    匹配流程：
    1. 根据媒体类型（电影/电视剧）选择对应的订阅清单
    2. 按 tmdbid / 名称 / 年份 / 季号 做精确/模糊匹配
    3. 匹配成功后应用过滤规则（质量/分辨率/制作组/包含排除等）
    """

    def __init__(self, site_conf: SiteConf | None = None, filter_engine=None, site_cache: SiteCache | None = None):
        self._filter = filter_engine or IndexerFilterEngine()
        self._site_cache = site_cache
        self._site_conf = site_conf or SiteConf(site_engine=None)

    def match(
        self,
        media_info,
        rss_movies,
        rss_tvs,
        site_id,
        site_filter_rule,
        site_cookie,
        site_parse,
        site_ua,
        site_headers,
        site_proxy,
        site_api_key=None,
        site_bearer_token=None,
    ):
        """判断种子是否命中订阅.

        :param media_info: 已识别的种子媒体信息
        :param rss_movies: 电影订阅清单 {rid: info}
        :param rss_tvs: 电视剧订阅清单 {rid: info}
        :return: (match_flag, match_msg_list, match_rss_info)
        """
        match_flag = False
        match_msg = []
        match_rss_info = {}
        upload_volume_factor = None
        download_volume_factor = None
        hit_and_run = False

        # ---------- 匹配电影 ----------
        if media_info.type == MediaType.MOVIE and rss_movies:
            for _rid, rss_info in rss_movies.items():
                rss_sites = rss_info.get("rss_sites")
                if rss_sites and media_info.site not in rss_sites:
                    continue

                name = rss_info.get("name")
                year = rss_info.get("year")
                tmdbid = rss_info.get("tmdbid")
                fuzzy_match = rss_info.get("fuzzy_match")

                if not fuzzy_match:
                    if tmdbid and not tmdbid.startswith("DB:"):
                        if str(media_info.tmdb_id) != str(tmdbid):
                            continue
                    else:
                        if year and str(media_info.year) not in [str(year), str(int(year) + 1), str(int(year) - 1)]:
                            continue
                        if name != media_info.title:
                            continue
                else:
                    if year and str(year) != str(media_info.year):
                        continue
                    search_title = f"{media_info.rev_string} {media_info.title} {media_info.year}"
                    if not re.search(name, search_title, re.I) and name not in search_title:
                        continue

                match_flag = True
                match_rss_info = rss_info
                break

        # ---------- 匹配电视剧 ----------
        elif rss_tvs:
            for _rid, rss_info in rss_tvs.items():
                rss_sites = rss_info.get("rss_sites")
                if rss_sites and media_info.site not in rss_sites:
                    continue

                name = rss_info.get("name")
                year = rss_info.get("year")
                season = rss_info.get("season")
                tmdbid = rss_info.get("tmdbid")
                fuzzy_match = rss_info.get("fuzzy_match")

                if not fuzzy_match:
                    if tmdbid and not tmdbid.startswith("DB:"):
                        if str(media_info.tmdb_id) != str(tmdbid):
                            continue
                    else:
                        if year and str(year) != str(media_info.year):
                            continue
                        if name != media_info.title:
                            continue
                    if season and season != media_info.get_season_string():
                        continue
                else:
                    if season and season != "S00" and season != media_info.get_season_string():
                        continue
                    if year and str(year) != str(media_info.year):
                        continue
                    search_title = f"{media_info.rev_string} {media_info.title} {media_info.year}"
                    if not re.search(name, search_title, re.I) and name not in search_title:
                        continue

                match_flag = True
                match_rss_info = rss_info
                break

        # ---------- 匹配成功，应用过滤规则 ----------
        if not match_flag:
            match_msg.append(
                f"{media_info.org_string} 识别为 {media_info.get_title_string()} "
                f"{media_info.get_season_episode_string()} 不在订阅范围"
            )
            return False, match_msg, match_rss_info

        # 站点 Free 检测
        if site_parse and self._site_cache:
            if self._site_cache.check_ratelimit(site_id):
                match_msg.append("触发站点流控")
                return False, match_msg, match_rss_info

            torrent_attr = self._site_conf.check_torrent_attr(
                torrent_url=media_info.page_url,
                cookie=site_cookie,
                api_key=site_api_key,
                bearer_token=site_bearer_token,
                ua=site_ua,
                headers=site_headers,
                proxy=site_proxy,
            )
            if torrent_attr.get("2xfree"):
                download_volume_factor = 0.0
                upload_volume_factor = 2.0
            elif torrent_attr.get("free"):
                download_volume_factor = 0.0
                upload_volume_factor = 1.0
            else:
                upload_volume_factor = 1.0
                download_volume_factor = 1.0
            if torrent_attr.get("hr"):
                hit_and_run = True
            media_info.set_torrent_info(
                upload_volume_factor=upload_volume_factor,
                download_volume_factor=download_volume_factor,
                hit_and_run=hit_and_run,
            )

        # 过滤规则
        filter_rule = match_rss_info.get("filter_rule") or site_filter_rule
        filter_dict = {
            "restype": match_rss_info.get("filter_restype"),
            "pix": match_rss_info.get("filter_pix"),
            "team": match_rss_info.get("filter_team"),
            "rule": filter_rule,
            "include": match_rss_info.get("filter_include"),
            "exclude": match_rss_info.get("filter_exclude"),
        }

        group_repo = FilterGroupRepositoryAdapter()
        rule_repo = FilterRuleRepositoryAdapter()

        # 基础条件过滤
        match_filter_flag, res_order, match_filter_msg = self._filter.check_torrent_filter(
            meta_info=media_info,
            filter_args=filter_dict,
            uploadvolumefactor=upload_volume_factor,
            downloadvolumefactor=download_volume_factor,
        )

        if match_filter_flag and filter_rule:
            # 站点规则过滤
            group = group_repo.get_by_id(int(filter_rule)) if str(filter_rule).isdigit() else None
            if group:
                rulegroup_info = group.to_dict()
                entities = rule_repo.get_by_group(group.id)
                filters_list = []
                for e in entities:
                    include_str = e.include or ""
                    exclude_str = e.exclude or ""
                    filters_list.append(
                        {
                            "include": [x.strip() for x in include_str.split(",") if x.strip()]
                            if include_str
                            else None,
                            "exclude": [x.strip() for x in exclude_str.split(",") if x.strip()]
                            if exclude_str
                            else None,
                            "size": None,
                            "free": e.note,
                            "pri": e.priority,
                        }
                    )
                match_filter_flag, res_order, rule_name = self._filter.check_rules(
                    media_info, rulegroup_info, filters_list
                )
                if not match_filter_flag:
                    match_filter_msg = f"{media_info.org_string} 不符合过滤规则 {rule_name} 要求"

        if not match_filter_flag:
            match_msg.append(match_filter_msg)
            return False, match_msg, match_rss_info

        match_msg.append(
            f"{media_info.org_string} 识别为 {media_info.get_title_string()} "
            f"{media_info.get_season_episode_string()} 匹配订阅成功"
        )
        match_msg.append(f"种子描述：{media_info.subtitle}")
        match_rss_info.update(
            {
                "res_order": res_order,
                "filter_rule": filter_rule,
                "upload_volume_factor": upload_volume_factor,
                "download_volume_factor": download_volume_factor,
            }
        )

        return True, match_msg, match_rss_info
