# -*- coding: utf-8 -*-
"""
DownloadStrategies - 批量下载策略

将 batch_download 中的策略逻辑提取为独立类：
- MovieDownloadStrategy：电影下载策略
- SeasonPackStrategy：整季包下载策略
- EpisodeStrategy：单集下载策略

所有策略均不持有状态，作为纯逻辑类提供静态/类方法，
便于单元测试和独立演进。
"""
import os
from typing import List, Tuple, Dict, Optional

import log
from app.utils import Torrent
from app.utils.types import MediaType


class MovieDownloadStrategy:
    """
    电影下载策略
    """

    @staticmethod
    def download_movies(download_list: list,
                        download_callback,
                        get_download_url_callback) -> list:
        """
        下载所有电影
        :param download_list: 候选资源列表
        :param download_callback: 实际下载函数，签名为 (item, torrent_file, tag, is_paused) -> (downloader_id, download_id, msg)
        :param get_download_url_callback: 获取下载链接函数，签名为 (page_url) -> url
        :return: 已下载项目列表
        """
        return_items = []
        for item in download_list:
            if item.type == MediaType.MOVIE:
                if not item.enclosure:
                    item.enclosure = get_download_url_callback(item.page_url)
                _downloader_id, did, msg = download_callback(item)
                if did:
                    if item not in return_items:
                        return_items.append(item)
                else:
                    log.error(f"【Downloader】下载失败: {item.title}, 错误: {msg}")
        return return_items


class SeasonPackStrategy:
    """
    电视剧整季包下载策略
    """

    @staticmethod
    def find_season_packs(download_list: list,
                          need_seasons: dict,
                          need_tvs: dict,
                          get_download_url_callback,
                          download_callback,
                          get_torrent_episodes_callback) -> Tuple[list, dict, dict]:
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
                item_season = item.get_season_list()
                if item.get_episode_list():
                    continue
                if need_tmdbid != item.tmdb_id:
                    continue
                if not item.enclosure:
                    item.enclosure = get_download_url_callback(item.page_url)
                if set(item_season).issubset(set(need_season)):
                    if len(item_season) == 1:
                        # 只有一季的可能是命名错误，需要打开种子鉴别
                        total_eps = SeasonPackStrategy._get_season_episodes(need_tvs, need_tmdbid, item_season[0])
                        torrent_episodes, torrent_path = get_torrent_episodes_callback(
                            item.enclosure, item.page_url
                        )
                        # 如果种子实际集数大于等于总集数（或种子无集数信息但total_eps为0），则下载
                        if torrent_episodes and len(torrent_episodes) >= total_eps:
                            _, download_id, _ = download_callback(item, torrent_file=torrent_path)
                        elif not torrent_episodes and total_eps == 0:
                            # 无法判断集数时保守跳过
                            log.info(
                                f"【Downloader】种子 {item.org_string} 未含集数信息，跳过")
                            continue
                        elif not torrent_episodes:
                            log.info(
                                f"【Downloader】种子 {item.org_string} 未含集数信息，解析文件数为 0")
                            continue
                        else:
                            continue
                    else:
                        _, download_id, _ = download_callback(item)
                    if download_id:
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
    def build_need_seasons(need_tvs: dict) -> dict:
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
    def download_episodes(download_list: list,
                          need_tvs: dict,
                          get_download_url_callback,
                          download_callback,
                          get_torrent_episodes_callback,
                          set_files_status_callback,
                          start_torrents_callback,
                          return_items: list) -> Tuple[list, dict]:
        """
        按单集匹配下载
        :param download_list: 候选资源列表
        :param need_tvs: 缺失季集信息
        :param get_download_url_callback: 获取下载链接函数
        :param download_callback: 实际下载函数
        :param get_torrent_episodes_callback: 解析种子集数函数
        :param set_files_status_callback: 设置文件下载状态函数，签名为 (tid, need_episodes, downloader_id) -> selected_episodes
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
                total_episodes = tv.get("total_episodes")
                # 缺失整季的转化为缺失集
                if not need_episodes:
                    need_episodes = list(range(1, total_episodes + 1))
                for item in download_list:
                    if item.type == MediaType.MOVIE:
                        continue
                    if item.tmdb_id != need_tmdbid:
                        continue
                    if item in return_items:
                        continue
                    # 只处理单季含集的种子
                    item_season = item.get_season_list()
                    if len(item_season) != 1 or item_season[0] != need_season:
                        continue
                    item_episodes = item.get_episode_list()
                    if not item_episodes:
                        if not item.enclosure:
                            item.enclosure = get_download_url_callback(item.page_url)
                        if item.enclosure.startswith('magnet'):
                            continue
                        torrent_episodes, torrent_path = get_torrent_episodes_callback(
                            item.enclosure, item.page_url
                        )
                        if not torrent_episodes:
                            continue
                        item_episodes = torrent_episodes
                    # 为需要集的子集则下载
                    if set(item_episodes).issubset(set(need_episodes)):
                        _, download_id, _ = download_callback(item)
                        if download_id:
                            need_episodes = EpisodeStrategy._update_episodes(
                                need_tvs, need_tmdbid, need_episodes, item_episodes
                            )
                index += 1
        return return_items, need_tvs

    @staticmethod
    def download_from_season_pack(download_list: list,
                                  need_tvs: dict,
                                  get_download_url_callback,
                                  download_callback,
                                  get_torrent_episodes_callback,
                                  set_files_status_callback,
                                  start_torrents_callback,
                                  return_items: list) -> Tuple[list, dict]:
        """
        从整季包中选取需要的集数下载（仅支持QB/TR）
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
                if not need_episodes:
                    index += 1
                    continue
                for item in download_list:
                    if item.type == MediaType.MOVIE:
                        continue
                    if item in return_items:
                        continue
                    if not need_episodes:
                        break
                    # 选中单季整季的或单季包括需要的所有集的
                    item_season = item.get_season_list()
                    item_episodes = item.get_episode_list()
                    if item.tmdb_id != need_tmdbid:
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
                    # 检查种子看是否有需要的集
                    torrent_episodes, torrent_path = get_torrent_episodes_callback(
                        item.enclosure, item.page_url
                    )
                    selected_episodes = set(torrent_episodes).intersection(set(need_episodes))
                    if not selected_episodes:
                        log.info("【Downloader】%s 没有需要的集，跳过..." % item.org_string)
                        continue
                    # 添加下载并暂停
                    downloader_id, download_id, _ = download_callback(
                        item, torrent_file=torrent_path, is_paused=True
                    )
                    if not download_id:
                        continue
                    # 更新仍需集数
                    need_episodes = EpisodeStrategy._update_episodes(
                        need_tvs, need_tmdbid, need_episodes, list(selected_episodes)
                    )
                    # 设置任务只下载想要的文件
                    log.info("【Downloader】从 %s 中选取集：%s" % (item.org_string, selected_episodes))
                    set_files_status_callback(
                        tid=download_id,
                        need_episodes=list(selected_episodes),
                        downloader_id=downloader_id
                    )
                    # 重新开始任务
                    log.info("【Downloader】%s 开始下载 " % item.org_string)
                    start_torrents_callback(ids=download_id, downloader_id=downloader_id)
                    # 记录下载项
                    if item not in return_items:
                        return_items.append(item)
                index += 1
        return return_items, need_tvs

    @staticmethod
    def _update_episodes(need_tvs, tmdbid, need, current):
        """更新 need_tvs 集数"""
        need = list(set(need).difference(set(current)))
        # 直接更新该 tmdbid 下所有条目的 episodes（简化逻辑，与原始行为一致）
        if need:
            for tv in need_tvs.get(tmdbid, []):
                if tv.get("episodes") is not None:
                    tv["episodes"] = need
        else:
            # 如果该 tmdbid 下所有条目都空了，移除
            to_remove = []
            for tv in need_tvs.get(tmdbid, []):
                if tv.get("episodes") is not None and not tv.get("episodes"):
                    to_remove.append(tv)
            for tv in to_remove:
                need_tvs[tmdbid].remove(tv)
            if not need_tvs.get(tmdbid):
                need_tvs.pop(tmdbid, None)
        return need
