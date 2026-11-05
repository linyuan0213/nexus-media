"""
DownloadStrategies - 批量下载策略

将 batch_download 中的策略逻辑提取为独立类：
- MovieDownloadStrategy：电影下载策略
- SeasonPackStrategy：整季包下载策略
- EpisodeStrategy：单集下载策略

所有策略均不持有状态，作为纯逻辑类提供静态/类方法，
便于单元测试和独立演进。
"""

import contextlib

import log
from app.domain.media_ref import identity_keys_match, media_identity_key
from app.domain.mediatypes import MediaType

_DOWNLOAD_FAILED_FLAG = "_download_failed"


def is_download_failed(item) -> bool:
    """候选是否已在本轮下载失败（失败后不再重复选中，自动落到下一个候选）."""
    return bool(getattr(item, _DOWNLOAD_FAILED_FLAG, False))


def mark_download_failed(item) -> None:
    """标记候选本轮下载失败，供后续策略阶段跳过."""
    with contextlib.suppress(Exception):
        setattr(item, _DOWNLOAD_FAILED_FLAG, True)


class MovieDownloadStrategy:
    """
    电影下载策略
    """

    @staticmethod
    def download_movies(download_list: list, download_callback, get_download_url_callback) -> list:
        """
        下载所有电影
        :param download_list: 候选资源列表
        :param download_callback: 实际下载函数，签名为
        (item, torrent_file, tag, is_paused) -> (downloader_id, download_id, msg)
        :param get_download_url_callback: 获取下载链接函数，签名为 (page_url) -> url
        :return: 已下载项目列表
        """
        return_items = []
        downloaded_names: set[str] = set()
        for item in download_list:
            if item.type != MediaType.MOVIE or is_download_failed(item):
                continue
            # 同一电影已成功下载一个候选即停止，失败则继续尝试下一个候选
            movie_title = (
                item.get_title_string() if hasattr(item, "get_title_string") else (getattr(item, "title", "") or "")
            )
            # 同一电影只下载一个候选：身份相同即可，年份/标题不同不能当成不同电影
            movie_key = media_identity_key(item)
            movie_name = movie_key or movie_title
            if movie_name in downloaded_names:
                continue
            if not item.enclosure:
                item.enclosure = get_download_url_callback(item.page_url)
            site = str(getattr(item, "site", "") or "未知站点")
            _downloader_id, did, msg = download_callback(item)
            if did:
                downloaded_names.add(movie_name)
                if item not in return_items:
                    return_items.append(item)
                log.info(f"[Downloader]候选下载成功: {movie_title} @ {site}")
            else:
                mark_download_failed(item)
                log.warn(f"[Downloader]候选下载失败: {movie_title} @ {site}，继续尝试下一候选：{msg}")
        return return_items


class SeasonPackStrategy:
    """
    电视剧整季包下载策略
    """

    @staticmethod
    def find_season_packs(
        download_list: list,
        need_seasons: dict,
        need_tvs: dict,
        get_download_url_callback,
        download_callback,
        get_torrent_episodes_callback,
    ) -> tuple[list, dict, dict]:
        """
        查找并下载整季包含的种子
        :param download_list: 候选资源列表
        :param need_seasons: {tmdbid: [season_numbers]}
        :param need_tvs: 原始缺失季集信息
        :param get_download_url_callback: 获取下载链接函数
        :param download_callback: 实际下载函数
        :param get_torrent_episodes_callback: 解析种子集数函数，签名为 (url, page_url) -> (episodes, torrent_path)
        :return: (已下载项目列表, 更新后的 need_seasons, 更新后的 need_tvs)
        """
        return_items = []
        for need_tmdbid, need_season in list(need_seasons.items()):
            for item in download_list:
                if item.type == MediaType.MOVIE:
                    continue
                if is_download_failed(item):
                    continue
                item_season = item.get_season_list()
                if item.get_episode_list():
                    continue
                if not identity_keys_match(need_tmdbid, media_identity_key(item)):
                    continue
                if not item.enclosure:
                    item.enclosure = get_download_url_callback(item.page_url)
                if set(item_season).issubset(set(need_season)):
                    if len(item_season) == 1:
                        # 只有一季的可能是命名错误，需打开种子核对实际集号覆盖，
                        # 避免“标题 S01、内容仅单集”被当作整季而误判完成
                        total_eps = SeasonPackStrategy._get_season_episodes(need_tvs, need_tmdbid, item_season[0])
                        torrent_episodes, torrent_path = get_torrent_episodes_callback(item.enclosure, item.page_url)
                        covered = set(torrent_episodes or [])
                        if not covered:
                            log.info(f"[Downloader]种子 {item.org_string} 未含集数信息，跳过（无法确认覆盖）")
                            continue
                        # 总集数已知：覆盖需达到该季总集数；未知：至少需多集，
                        # 以排除“标题 S01、内容仅单集”的误标，同时避免总集数未知时永远不下载
                        coverage_ok = len(covered) >= total_eps if total_eps else len(covered) >= 2
                        if not coverage_ok:
                            log.info(
                                f"[Downloader]种子 {item.org_string} 无法确认覆盖该季"
                                f"（实际 {len(covered)} 集，总集数={total_eps}），跳过"
                            )
                            continue
                        _, download_id, _ = download_callback(item, torrent_file=torrent_path)
                    else:
                        # 多季包：非磁力需核对实际集数覆盖，避免标题含多季但内容不全时误判完成；
                        # 磁力无法预解析文件清单，保持原整包下载路径
                        if (item.enclosure or "").startswith("magnet:"):
                            _, download_id, _ = download_callback(item)
                        else:
                            req_eps = sum(
                                SeasonPackStrategy._get_season_episodes(need_tvs, need_tmdbid, s) for s in item_season
                            )
                            torrent_episodes, torrent_path = get_torrent_episodes_callback(
                                item.enclosure, item.page_url
                            )
                            covered = set(torrent_episodes or [])
                            if not covered:
                                log.info(f"[Downloader]种子 {item.org_string} 未含集数信息，跳过（无法确认覆盖）")
                                continue
                            coverage_ok = len(covered) >= req_eps if req_eps else len(covered) >= 2
                            if not coverage_ok:
                                log.info(
                                    f"[Downloader]种子 {item.org_string} 无法确认覆盖整包"
                                    f"（实际 {len(covered)} 集，需求 {req_eps} 集），跳过"
                                )
                                continue
                            _, download_id, _ = download_callback(item, torrent_file=torrent_path)
                    if download_id:
                        if item not in return_items:
                            return_items.append(item)
                        need_season = list(set(need_season).difference(set(item_season)))
                        for cur in item_season:
                            for nt in list(need_tvs.get(need_tmdbid, [])):
                                if cur == nt.get("season") or (cur == 1 and not nt.get("season")):
                                    need_tvs[need_tmdbid].remove(nt)
                        if not need_tvs.get(need_tmdbid):
                            need_tvs.pop(need_tmdbid, None)
                        need_seasons[need_tmdbid] = need_season
            if not need_season:
                need_seasons.pop(need_tmdbid, None)
        return return_items, need_seasons, need_tvs

    @staticmethod
    def build_need_seasons(need_tvs: dict | None) -> dict:
        """从 need_tvs 中提取整季缺失的季数"""
        need_seasons = {}
        if not need_tvs:
            return need_seasons
        for need_tmdbid, need_tv in need_tvs.items():
            for tv in need_tv:
                if not tv:
                    continue
                if not tv.get("episodes"):
                    if not need_seasons.get(need_tmdbid):
                        need_seasons[need_tmdbid] = []
                    need_seasons[need_tmdbid].append(tv.get("season") or 1)
        return need_seasons

    @staticmethod
    def _get_season_episodes(need_tvs, tmdbid, season):
        """获取指定季的总集数"""
        if not need_tvs.get(tmdbid):
            return 0
        for nt in need_tvs.get(tmdbid):
            if season == nt.get("season"):
                return nt.get("total_episodes") or 0
        return 0


class EpisodeStrategy:
    """
    电视剧单集/部分集下载策略
    """

    @staticmethod
    def download_episodes(
        download_list: list,
        need_tvs: dict,
        get_download_url_callback,
        download_callback,
        get_torrent_episodes_callback,
        _set_files_status_callback,
        _start_torrents_callback,
        return_items: list,
    ) -> tuple[list, dict]:
        """
        按单集匹配下载
        :param download_list: 候选资源列表
        :param need_tvs: 缺失季集信息
        :param get_download_url_callback: 获取下载链接函数
        :param download_callback: 实际下载函数
        :param get_torrent_episodes_callback: 解析种子集数函数
        :param set_files_status_callback: 设置文件下载状态函数，签名为
        (tid, need_episodes, downloader_id) -> selected_episodes
        :param start_torrents_callback: 开始任务函数，签名为 (ids, downloader_id)
        :param return_items: 已下载项目列表（会追加）
        :return: (更新后的 return_items, 更新后的 need_tvs)
        """
        if not need_tvs:
            return return_items, need_tvs

        need_tv_list = list(need_tvs)
        for need_tmdbid in need_tv_list:
            need_tv = need_tvs.get(need_tmdbid)
            if not need_tv:
                continue
            index = 0
            for tv in list(need_tv):
                need_season = tv.get("season") or 1
                need_episodes = tv.get("episodes")
                total_episodes = tv.get("total_episodes") or 0
                # 缺失整季的转化为缺失集
                if not need_episodes:
                    need_episodes = list(range(1, total_episodes + 1))
                for item in download_list:
                    if item.type == MediaType.MOVIE:
                        continue
                    if not identity_keys_match(need_tmdbid, media_identity_key(item)):
                        continue
                    if item in return_items or is_download_failed(item):
                        continue
                    # 只处理单季含集的种子
                    item_season = item.get_season_list()
                    if len(item_season) != 1 or item_season[0] != need_season:
                        continue
                    item_episodes = item.get_episode_list()
                    if not item_episodes:
                        if not item.enclosure:
                            item.enclosure = get_download_url_callback(item.page_url)
                        if item.enclosure.startswith("magnet"):
                            continue
                        torrent_episodes, torrent_path = get_torrent_episodes_callback(item.enclosure, item.page_url)
                        if not torrent_episodes:
                            continue
                        item_episodes = torrent_episodes
                    # 为需要集的子集则下载
                    if set(item_episodes).issubset(set(need_episodes)):
                        _, download_id, _ = download_callback(item)
                        if download_id:
                            if item not in return_items:
                                return_items.append(item)
                            need_episodes = EpisodeStrategy._update_episodes(
                                need_tvs, need_tmdbid, need_episodes, item_episodes, need_season
                            )
                index += 1
        return return_items, need_tvs

    @staticmethod
    def download_from_season_pack(
        download_list: list,
        need_tvs: dict,
        get_download_url_callback,
        download_callback,
        get_torrent_episodes_callback,
        set_files_status_callback,
        start_torrents_callback,
        return_items: list,
        get_torrent_episodes_by_tid_callback=None,
        remove_torrents_callback=None,
    ) -> tuple[list, dict]:
        """
        从整季包中选取需要的集数下载（仅支持QB/TR）
        :return: (更新后的 return_items, 更新后的 need_tvs)
        """
        if not need_tvs:
            return return_items, need_tvs

        def _rollback(download_id, downloader_id):
            """原子回滚：删除已暂停加入但未成功启动的任务"""
            if remove_torrents_callback and download_id:
                try:
                    remove_torrents_callback(download_id, downloader_id)
                except Exception as e:  # noqa: BLE001
                    log.warn(f"[Downloader]回滚删除任务失败：{e}")

        need_tv_list = list(need_tvs)
        for need_tmdbid in need_tv_list:
            need_tv = need_tvs.get(need_tmdbid)
            if not need_tv:
                continue
            index = 0
            for tv in list(need_tv):
                need_season = tv.get("season") or 1
                need_episodes = tv.get("episodes")
                if not need_episodes:
                    index += 1
                    continue
                for item in download_list:
                    if item.type == MediaType.MOVIE:
                        continue
                    if item in return_items or is_download_failed(item):
                        continue
                    if not need_episodes:
                        break
                    # 选中单季整季的或单季包括需要的所有集的
                    item_season = item.get_season_list()
                    item_episodes = item.get_episode_list()
                    if not identity_keys_match(need_tmdbid, media_identity_key(item)):
                        continue
                    if not item_episodes:
                        # 无集数信息但属于单季整季的也考虑
                        pass
                    elif not set(item_episodes).intersection(set(need_episodes)):
                        continue
                    if len(item_season) != 1 or item_season[0] != need_season:
                        continue

                    if not item.enclosure:
                        item.enclosure = get_download_url_callback(item.page_url)
                    is_magnet = (item.enclosure or "").startswith("magnet:")

                    if is_magnet:
                        # 磁力原子化：暂停加入 → 读取文件清单筛选取需 → 开始；任一步失败即回滚删除任务
                        downloader_id, download_id, _ = download_callback(item, torrent_file=None, is_paused=True)
                        if not download_id:
                            continue
                        try:
                            torrent_episodes = (
                                get_torrent_episodes_by_tid_callback(download_id, downloader_id, item.page_url)
                                if get_torrent_episodes_by_tid_callback
                                else []
                            )
                            if torrent_episodes:
                                selected_episodes = set(torrent_episodes).intersection(set(need_episodes))
                                if not selected_episodes:
                                    log.info(f"[Downloader]{item.org_string} 磁力包内没有需要的集，回滚")
                                    _rollback(download_id, downloader_id)
                                    continue
                                need_episodes = EpisodeStrategy._update_episodes(
                                    need_tvs, need_tmdbid, need_episodes, list(selected_episodes), need_season
                                )
                                log.info(f"[Downloader]从 {item.org_string} 中选取集：{selected_episodes}")
                                set_files_status_callback(
                                    tid=download_id, need_episodes=list(selected_episodes), downloader_id=downloader_id
                                )
                            else:
                                # 无法解析文件清单：仍按整包下载，但不清空缺失（避免单集包当整季完成）；
                                # 实际覆盖由转移后按落盘文件核定（subscribe/handlers）。
                                log.warn(
                                    f"[Downloader]{item.org_string} 磁力未解析出文件清单，"
                                    f"按整包下载，保留缺失待转移后核定"
                                )
                            log.info(f"[Downloader]{item.org_string} 开始下载 ")
                            start_torrents_callback(ids=download_id, downloader_id=downloader_id)
                            if item not in return_items:
                                return_items.append(item)
                        except Exception as e:  # noqa: BLE001
                            log.error(f"[Downloader]{item.org_string} 磁力整季包处理失败，回滚：{e}")
                            _rollback(download_id, downloader_id)
                        continue

                    # 非磁力：解析种子集数 → 暂停加入 → 设置需集 → 开始（失败回滚）
                    torrent_episodes, torrent_path = get_torrent_episodes_callback(item.enclosure, item.page_url)
                    selected_episodes = set(torrent_episodes).intersection(set(need_episodes))
                    if not selected_episodes:
                        log.info(f"[Downloader]{item.org_string} 没有需要的集，跳过...")
                        continue
                    downloader_id, download_id, _ = download_callback(item, torrent_file=torrent_path, is_paused=True)
                    if not download_id:
                        continue
                    try:
                        need_episodes = EpisodeStrategy._update_episodes(
                            need_tvs, need_tmdbid, need_episodes, list(selected_episodes), need_season
                        )
                        log.info(f"[Downloader]从 {item.org_string} 中选取集：{selected_episodes}")
                        set_files_status_callback(
                            tid=download_id, need_episodes=list(selected_episodes), downloader_id=downloader_id
                        )
                        log.info(f"[Downloader]{item.org_string} 开始下载 ")
                        start_torrents_callback(ids=download_id, downloader_id=downloader_id)
                        if item not in return_items:
                            return_items.append(item)
                    except Exception as e:  # noqa: BLE001
                        log.error(f"[Downloader]{item.org_string} 整季包处理失败，回滚：{e}")
                        _rollback(download_id, downloader_id)
                index += 1
        return return_items, need_tvs

    @staticmethod
    def _update_episodes(need_tvs, tmdbid, need, current, season=1):
        """更新 need_tvs 中指定季的集数"""
        need = list(set(need).difference(set(current)))
        tv_list = need_tvs.get(tmdbid, [])
        if not tv_list:
            return need

        # 按季定位目标条目，避免下标因整季包删除等操作发生错位
        target_index = None
        for i, tv in enumerate(tv_list):
            if tv.get("season") == season:
                target_index = i
                break

        if target_index is None:
            return need

        if need:
            tv_list[target_index]["episodes"] = need
        else:
            tv_list.pop(target_index)
            if not tv_list:
                need_tvs.pop(tmdbid, None)
        return need
