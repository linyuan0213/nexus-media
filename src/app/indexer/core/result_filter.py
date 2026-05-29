"""
结果过滤器

提供搜索结果的两阶段过滤：
1. local_filter：基于 meta_info 的本地轻量级过滤（无 TMDB 依赖）
2. match_filter：基于 TMDB 识别结果的匹配过滤

不依赖服务层，规则数据通过仓库层直接查询。
"""

import log
from app.di import container
from app.indexer.core.batch_identifier import BatchIdentifier
from app.indexer.core.models import FilterStats, SearchCandidate
from app.infrastructure.cache_system import get_cache_manager
from app.media import meta_info
from app.utils import StringUtils
from app.utils.types import MediaType


class ResultFilter:
    """
    结果过滤器

    内部通过 IndexerFilterEngine 进行纯逻辑计算，
    规则数据通过 FilterGroupRepositoryAdapter / FilterRuleRepositoryAdapter 从仓库层获取。
    """

    def __init__(self, media=None):
        self._engine = container.indexer_filter_engine()
        self._media = media or container.media_service()
        self._group_repo = container.filter_group_repo()
        self._rule_repo = container.filter_rule_repo()
        self._rule_cache = {}

    def _get_rules(self, rulegroup_id=None):
        """
        从仓库层获取规则组和规则列表，带本地缓存

        :return: (rulegroup_info: dict, filters: list)
        """
        cache_key = rulegroup_id if rulegroup_id is not None else "__default__"
        if cache_key in self._rule_cache:
            return self._rule_cache[cache_key]

        if rulegroup_id:
            group = self._group_repo.get_by_id(int(rulegroup_id))
        else:
            groups = self._group_repo.get_all()
            group = None
            for g in groups:
                if g.default:
                    group = g
                    break

        if not group:
            rulegroup_info = {"name": "未配置"}
            filters = []
        else:
            rulegroup_info = group.to_dict()
            entities = self._rule_repo.get_by_group(group.id)
            filters = []
            for e in entities:
                include_str = e.include or ""
                exclude_str = e.exclude or ""
                filters.append(
                    {
                        "include": [x.strip() for x in include_str.splitlines() if x.strip()] if include_str else None,
                        "exclude": [x.strip() for x in exclude_str.splitlines() if x.strip()] if exclude_str else None,
                        "size": None,
                        "free": e.note,
                        "pri": e.priority,
                    }
                )

        self._rule_cache[cache_key] = (rulegroup_info, filters)
        log.info(
            f"【ResultFilter】加载规则组: {rulegroup_info.get('name')} (ID={rulegroup_info.get('id')}), 规则数: {len(filters)}"
        )
        return rulegroup_info, filters

    def _check_full_filter(self, meta_info, filter_args, uploadvolumefactor, downloadvolumefactor):
        """
        完整过滤：基础条件 + 规则

        :return: (是否通过, 优先级, 信息)
        """
        match_flag, res_order, match_msg = self._engine.check_torrent_filter(
            meta_info=meta_info,
            filter_args=filter_args,
            uploadvolumefactor=uploadvolumefactor,
            downloadvolumefactor=downloadvolumefactor,
        )
        if not match_flag:
            return match_flag, res_order, match_msg

        rulegroup_id = filter_args.get("rule")
        rulegroup_info, filters = self._get_rules(rulegroup_id)
        match_flag, res_order, rule_name = self._engine.check_rules(meta_info, rulegroup_info, filters)
        if not match_flag:
            msg = (
                f"{meta_info.org_string} 大小：{StringUtils.str_filesize(meta_info.size)} "
                f"促销：{meta_info.get_volume_factor_string()} "
                f"不符合过滤规则 {rule_name} 要求"
            )
            return match_flag, res_order, msg

        return True, res_order, ""

    @staticmethod
    def quick_name_match(meta_info, match_media):
        """
        快速名称匹配：不调用 TMDB，仅通过名称判断是否可能匹配
        """
        if not meta_info or not match_media:
            return False

        def _norm(name):
            if not name:
                return ""
            return StringUtils.handler_special_chars(str(name)).upper().strip()  # type: ignore[union-attr]

        match_names = {
            _norm(match_media.title),
            _norm(match_media.cn_name),
            _norm(match_media.en_name),
            _norm(match_media.original_title),
        }
        match_names.discard("")

        meta_names = {
            _norm(meta_info.title),
            _norm(meta_info.cn_name),
            _norm(meta_info.en_name),
        }
        meta_names.discard("")

        if not match_names or not meta_names:
            return False

        if meta_names & match_names:
            return True

        for mn in meta_names:
            if len(mn) < 3:
                continue
            for mmn in match_names:
                if len(mmn) < 3:
                    continue
                if mn in mmn or mmn in mn:
                    return True

        return False

    @staticmethod
    def _type_compatible(a, b):
        if a == b:
            return True
        return bool(a in (MediaType.TV, MediaType.ANIME) and b in (MediaType.TV, MediaType.ANIME))

    def local_filter(self, result_array, filter_args, match_media=None):
        """
        第一阶段：本地轻量级过滤

        :param result_array: 原始结果列表，每个元素为 dict，需包含站点元信息字段
        :return: (candidates, direct_results, stats)
        """
        candidates = []
        direct_results = []
        stats = FilterStats()

        for item in result_array:
            torrent_name = item.get("title")
            description = item.get("description")
            if not torrent_name:
                stats.index_error += 1
                continue

            enclosure = item.get("enclosure")
            size = item.get("size")
            seeders = item.get("seeders")
            peers = item.get("peers")
            page_url = item.get("page_url")
            uploadvolumefactor = (
                round(float(item.get("uploadvolumefactor")), 1) if item.get("uploadvolumefactor") is not None else 1.0
            )
            downloadvolumefactor = (
                round(float(item.get("downloadvolumefactor")), 1)
                if item.get("downloadvolumefactor") is not None
                else 1.0
            )
            imdbid = item.get("imdbid")
            labels = item.get("labels")
            indexer_name = item.get("_indexer_name", "")
            indexer_order = item.get("_indexer_order", 0)
            indexer_public = item.get("_indexer_public", False)

            if filter_args.get("seeders") and not indexer_public and str(seeders) == "0":
                log.info(f"【ResultFilter】{torrent_name} 做种数为0")
                stats.index_rule_fail += 1
                continue

            mi = meta_info(title=torrent_name, subtitle=f"{labels} {description}")
            if not mi.get_name():
                log.info(f"【ResultFilter】{torrent_name} 无法识别到名称")
                stats.index_match_fail += 1
                continue

            mi.set_torrent_info(
                size=size,
                imdbid=imdbid,
                upload_volume_factor=uploadvolumefactor,
                download_volume_factor=downloadvolumefactor,
                labels=labels,
            )

            if mi.type == MediaType.TV and filter_args.get("type") == MediaType.MOVIE:
                log.info(
                    f"【ResultFilter】{torrent_name} 是 {mi.type.value}，不匹配类型：{filter_args.get('type').value}"
                )
                stats.index_rule_fail += 1
                continue

            match_flag, res_order, match_msg = self._check_full_filter(
                meta_info=mi,
                filter_args=filter_args,
                uploadvolumefactor=uploadvolumefactor,
                downloadvolumefactor=downloadvolumefactor,
            )
            if not match_flag:
                log.info(f"【ResultFilter】{match_msg}")
                stats.index_rule_fail += 1
                continue

            if not match_media:
                media_info = mi
                media_info.set_torrent_info(
                    site=indexer_name,
                    site_order=indexer_order,
                    enclosure=enclosure,
                    res_order=res_order,
                    filter_rule=filter_args.get("rule"),
                    size=size,
                    seeders=seeders,
                    peers=peers,
                    description=description,
                    page_url=page_url,
                    upload_volume_factor=uploadvolumefactor,
                    download_volume_factor=downloadvolumefactor,
                )
                if media_info not in direct_results:
                    stats.index_sucess += 1
                    direct_results.append(media_info)
                else:
                    stats.index_rule_fail += 1
                continue

            if mi.imdb_id and match_media.imdb_id and str(mi.imdb_id) == str(match_media.imdb_id):
                candidates.append(
                    SearchCandidate(
                        item=item,
                        meta_info=mi,
                        res_order=res_order,
                        skip_tmdb=True,
                        media_info=self._media.merge_media_info(mi, match_media),
                        indexer_name=indexer_name,
                        indexer_order=indexer_order,
                        indexer_public=indexer_public,
                    )
                )
                continue

            if self.quick_name_match(mi, match_media):
                log.debug(f"【ResultFilter】{torrent_name} 快速名称匹配成功，跳过TMDB查询")
                candidates.append(
                    SearchCandidate(
                        item=item,
                        meta_info=mi,
                        res_order=res_order,
                        skip_tmdb=True,
                        media_info=self._media.merge_media_info(mi, match_media),
                        indexer_name=indexer_name,
                        indexer_order=indexer_order,
                        indexer_public=indexer_public,
                    )
                )
                continue

            candidates.append(
                SearchCandidate(
                    item=item,
                    meta_info=mi,
                    res_order=res_order,
                    skip_tmdb=False,
                    media_info=None,
                    indexer_name=indexer_name,
                    indexer_order=indexer_order,
                    indexer_public=indexer_public,
                )
            )

        return candidates, direct_results, stats

    def match_filter(self, candidates, match_media, filter_args):
        """
        第三阶段：TMDB 匹配及后续过滤

        :return: (matched_results, stats)
        """
        ret_array = []
        stats = FilterStats()
        media_ident_cache = get_cache_manager().get_or_create("media_ident", "memory", maxsize=2000, ttl=3600)

        for cand in candidates:
            item = cand.item
            meta_info = cand.meta_info
            res_order = cand.res_order
            torrent_name = item.get("title")
            description = item.get("description")
            size = item.get("size")
            seeders = item.get("seeders")
            peers = item.get("peers")
            page_url = item.get("page_url")
            uploadvolumefactor = (
                round(float(item.get("uploadvolumefactor")), 1) if item.get("uploadvolumefactor") is not None else 1.0
            )
            downloadvolumefactor = (
                round(float(item.get("downloadvolumefactor")), 1)
                if item.get("downloadvolumefactor") is not None
                else 1.0
            )
            enclosure = item.get("enclosure")
            cache_key = BatchIdentifier.build_cache_key(meta_info, torrent_name)
            indexer_name = cand.indexer_name
            indexer_order = cand.indexer_order

            if cand.skip_tmdb:
                media_info = cand.media_info
            elif not cache_key:
                log.warn(f"【ResultFilter】{torrent_name} 无法构建缓存键")
                stats.index_error += 1
                continue
            else:
                media_info = media_ident_cache.get(cache_key)
                if media_info is not None:
                    log.debug(f"【ResultFilter】从缓存获取媒体信息: {cache_key}")
                else:
                    media_info = None

                if not media_info:
                    log.warn(f"【ResultFilter】{cache_key} 识别媒体信息出错！")
                    stats.index_error += 1
                    continue

                if not media_info.tmdb_info:
                    if match_media and self._type_compatible(meta_info.type, match_media.type):
                        log.info(
                            f"【ResultFilter】{cache_key} 未匹配到TMDB，回退使用搜索媒体信息: {match_media.get_name()}"
                        )
                        media_info = self._media.merge_media_info(media_info, match_media)
                    else:
                        log.info(f"【ResultFilter】{cache_key} 识别为 {media_info.get_name()} 未匹配到媒体信息")
                        stats.index_match_fail += 1
                        continue
                elif str(media_info.tmdb_id) != str(match_media.tmdb_id):
                    media_type_str = media_info.type.value if media_info.type else "Unknown"
                    match_type_str = match_media.type.value if match_media.type else "Unknown"
                    log.info(
                        f"【ResultFilter】{cache_key} 识别为 "
                        f"{media_type_str}/{media_info.get_title_string()}/{media_info.tmdb_id} "
                        f"与 {match_type_str}/{match_media.get_title_string()}/{match_media.tmdb_id} 不匹配"
                    )
                    stats.index_match_fail += 1
                    continue
                else:
                    media_info = self._media.merge_media_info(media_info, match_media)

            # 恢复原始标题：缓存中的 MediaInfo.from_parser 不含 org_string
            if not media_info.org_string:
                media_info.org_string = meta_info.org_string

            if filter_args.get("type"):
                if (filter_args.get("type") == MediaType.TV and media_info.type == MediaType.MOVIE) or (
                    filter_args.get("type") == MediaType.MOVIE and media_info.type == MediaType.TV
                ):
                    display_name = cache_key if not cand.skip_tmdb else torrent_name
                    log.info(
                        f"【ResultFilter】{display_name} 是 {media_info.type.value}/"
                        f"{media_info.tmdb_id}，不是 {filter_args.get('type').value}"
                    )
                    stats.index_rule_fail += 1
                    continue

            display_name = cache_key if not cand.skip_tmdb else torrent_name
            if match_media.over_edition:
                if media_info.type != MediaType.MOVIE and media_info.get_episode_list():
                    log.info(
                        f"【ResultFilter】"
                        f"{media_info.get_title_string()}{media_info.get_season_string()} "
                        f"正在洗版，过滤掉季集不完整的资源：{display_name} {description}"
                    )
                    continue
                if match_media.res_order and int(res_order) <= int(match_media.res_order):
                    log.info(
                        f"【ResultFilter】"
                        f"{media_info.get_title_string()}{media_info.get_season_string()} "
                        f"正在洗版，已洗版优先级：{100 - int(match_media.res_order)}，"
                        f"当前资源优先级：{100 - int(res_order)}，"
                        f"跳过低优先级或同优先级资源：{display_name}"
                    )
                    continue

            if not self._engine.is_torrent_match_sey(
                media_info, filter_args.get("season"), filter_args.get("episode"), filter_args.get("year")
            ):
                media_type_str = media_info.type.value if media_info.type else "Unknown"
                log.info(
                    f"【ResultFilter】{display_name} 识别为 {media_type_str}/"
                    f"{media_info.get_title_string()}/{media_info.get_season_episode_string()} 不匹配季/集/年份"
                )
                stats.index_match_fail += 1
                continue

            log.info(
                f"【ResultFilter】{display_name} {description} 识别为 {media_info.get_title_string()} "
                f"{media_info.get_season_episode_string()} 匹配成功"
            )
            media_info.set_torrent_info(
                site=indexer_name,
                site_order=indexer_order,
                enclosure=enclosure,
                res_order=res_order,
                filter_rule=filter_args.get("rule"),
                size=size,
                seeders=seeders,
                peers=peers,
                description=description,
                page_url=page_url,
                upload_volume_factor=uploadvolumefactor,
                download_volume_factor=downloadvolumefactor,
            )
            if media_info not in ret_array:
                stats.index_sucess += 1
                ret_array.append(media_info)
            else:
                stats.index_rule_fail += 1

        return ret_array, stats
