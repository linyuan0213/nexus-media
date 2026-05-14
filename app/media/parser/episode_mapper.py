"""
集数映射器 — 全自动将解析出的季集映射到 TMDB 标准季集

触发条件（同时满足）：
  1. TMDB 上该剧正常季数 < Parser 解析出的季号
  2. 获取到的总集数 > 典型单季集数（>26）

映射逻辑：
  1. 获取 TMDB 全部 episodes（排除 Specials）
  2. 按 episode_number 排序，根据 air_date 间隔推断季分界
  3. 间隔 > 90 天视为新季开始
  4. 每个 block 对应 Parser 的一个季
  5. 返回映射后的 TMDB season/episode

普通电视剧（如 Breaking Bad S03E05）：
  TMDB 有 S01-S05，Parser 季号 3 <= 5 → 不触发映射

动漫合并季（如 Re:Zero S04E01）：
  TMDB 只有 S01，Parser 季号 4 > 1 → 触发映射
  推断出4个季块后 → 映射到 S01 对应集
"""

from datetime import datetime

import log
from app.core.constants import (
    EPISODE_MAPPER_MIN_BLOCK_LENGTH,
    EPISODE_MAPPER_MIN_TOTAL_EPISODES,
    EPISODE_MAPPER_SEASON_GAP_DAYS,
    EPISODE_MAPPER_SEASON_GAP_FORCE_DAYS,
)
from app.media.lookup.tmdb_lookup import TmdbLookup
from app.utils.types import MediaType


class EpisodeMapper:
    """全自动集数映射器"""

    def __init__(self, tmdb_lookup: TmdbLookup | None = None):
        self._tmdb = tmdb_lookup
        # 缓存: tmdb_id -> [(block_season, start_ep, end_ep), ...]
        self._blocks: dict[int, list[tuple[int, int, int]]] = {}

    def _fetch_blocks(self, tmdb_id: int) -> list[tuple[int, int, int]] | None:
        """从 TMDB 获取 episodes，按 air_date 推断季分界"""
        if tmdb_id in self._blocks:
            return self._blocks[tmdb_id]
        if not self._tmdb:
            return None

        try:
            tv_info = self._tmdb.get_tmdb_info(MediaType.TV, tmdb_id)
            if not tv_info:
                return None

            seasons = tv_info.get("seasons") or []
            normal_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
            if not normal_seasons:
                return None

            max_tmdb_season = max(s.get("season_number", 0) for s in normal_seasons)
            total_episodes = sum(s.get("episode_count", 0) for s in normal_seasons)

            # 总集数不够多，不是合并季
            if total_episodes < EPISODE_MAPPER_MIN_TOTAL_EPISODES:
                return None

            # 收集所有 episodes
            all_eps = []
            for season in normal_seasons:
                sn = season.get("season_number")
                eps = self._tmdb.season.get_episodes(tmdb_id, sn)
                for ep in eps:
                    ep["_tmdb_season"] = sn
                all_eps.extend(eps)

            if len(all_eps) < 2:
                return None

            all_eps = sorted(all_eps, key=lambda e: (e.get("_tmdb_season", 0), e.get("episode_number", 0)))

            # 推断季分界
            # 策略：
            #   1. 间隔 > EPISODE_MAPPER_SEASON_GAP_FORCE_DAYS (180天) → 强制分季
            #   2. 间隔 > EPISODE_MAPPER_SEASON_GAP_DAYS (90天) 且当前 block 已 >= EPISODE_MAPPER_MIN_BLOCK_LENGTH → 分季
            #   3. 否则 → 不分季（视为季内分割放送）
            blocks = []
            cur_season = 1
            start_ep = all_eps[0].get("episode_number", 1)
            block_start_idx = 0

            for i in range(1, len(all_eps)):
                prev = all_eps[i - 1]
                curr = all_eps[i]
                prev_date = _parse_date(prev.get("air_date"))
                curr_date = _parse_date(curr.get("air_date"))

                gap = None
                if prev_date and curr_date:
                    gap = (curr_date - prev_date).days

                should_split = False
                if gap:
                    if gap > EPISODE_MAPPER_SEASON_GAP_FORCE_DAYS:
                        should_split = True
                    elif gap > EPISODE_MAPPER_SEASON_GAP_DAYS:
                        current_length = i - block_start_idx
                        if current_length >= EPISODE_MAPPER_MIN_BLOCK_LENGTH:
                            should_split = True

                if should_split:
                    blocks.append((cur_season, start_ep, prev.get("episode_number", start_ep)))
                    cur_season += 1
                    start_ep = curr.get("episode_number", start_ep + 1)
                    block_start_idx = i

            blocks.append((cur_season, start_ep, all_eps[-1].get("episode_number", start_ep)))

            # 如果推断出的季数 <= TMDB 实际季数，说明不是合并季
            if len(blocks) <= max_tmdb_season:
                return None

            self._blocks[tmdb_id] = blocks
            log.info(f"【EpisodeMapper】TMDB {tmdb_id} 推断季结构: {blocks}")
            return blocks

        except Exception as e:
            log.warn(f"【EpisodeMapper】推断失败: {e}")
            return None

    def map(self, tmdb_id: int, source_season: int | None, source_episode: int | None) -> tuple[int, int] | None:
        """
        将 Parser 解析的季集映射到 TMDB 标准季集

        Returns:
            (target_season, target_episode) 或 None（无需映射/失败）
        """
        if not source_season or not source_episode or source_season < 1:
            return None

        blocks = self._fetch_blocks(tmdb_id)
        if not blocks:
            return None

        if source_season > len(blocks):
            log.warn(f"【EpisodeMapper】源季号 {source_season} > 推断季数 {len(blocks)}")
            return None

        _, start_ep, end_ep = blocks[source_season - 1]
        target_ep = start_ep + source_episode - 1
        if target_ep > end_ep:
            log.warn(f"【EpisodeMapper】映射后集号 {target_ep} 超出范围 (E{start_ep}-E{end_ep})")
            return None

        log.info(f"【EpisodeMapper】TMDB:{tmdb_id} S{source_season:02d}E{source_episode:02d} → S01E{target_ep:02d}")
        return 1, target_ep

    def map_auto(self, tmdb_id: int, source_season: int | None, source_episode: int | None) -> tuple[int, int] | None:
        """
        自动选择映射策略

        - season > 1: 合并季映射（如 Re:Zero S04E04）
        - season is None: 绝对集号映射（如 Slime E72）
        - season == 1: 无需映射

        合并季映射失败时，仅当失败原因是 episode 超出推断 block 范围
        才回退到绝对集号映射（如 S02 - 46 中的 46 是绝对集号）。
        如果 TMDB 已有该季（无需映射），直接返回 None。
        """
        if not source_episode or source_episode < 1:
            return None
        if source_season and source_season > 1:
            result = self.map(tmdb_id, source_season, source_episode)
            if result:
                return result
            # map 返回 None，需要判断是"无需映射"还是"episode 超出范围"
            # 如果 _blocks 缓存存在且 source_season 在 block 范围内，
            # 说明是 episode 超出范围，回退到绝对集号
            blocks = self._blocks.get(tmdb_id)
            if blocks and source_season <= len(blocks):
                log.info(f"【EpisodeMapper】合并季映射失败（episode 超出范围），回退到绝对集号映射: E{source_episode}")
                return self.map_absolute(tmdb_id, source_episode)
            # TMDB 已有该季，无需映射
            return None
        if not source_season:
            return self.map_absolute(tmdb_id, source_episode)
        return None

    def map_batch(self, items: list[dict]) -> list[tuple[int, int] | None]:
        """
        批量映射 — 相同 tmdb_id 共享缓存，不同 tmdb_id 并发查询

        Args:
            items: [{"tmdb_id": int, "season": int, "episode": int}, ...]

        Returns:
            [(target_season, target_episode) 或 None, ...]
        """
        if not items:
            return []

        from concurrent.futures import ThreadPoolExecutor

        # 按 tmdb_id 去重，只查未缓存的（合并季缓存）
        tmdb_ids_blocks = {
            item["tmdb_id"]
            for item in items
            if item.get("tmdb_id") and item["tmdb_id"] not in self._blocks and item.get("season") and item["season"] > 1
        }

        # 按 tmdb_id 去重，只查未缓存的（绝对集号缓存）
        tmdb_ids_abs = {
            item["tmdb_id"]
            for item in items
            if item.get("tmdb_id") and f"abs:{item['tmdb_id']}" not in self._blocks and not item.get("season")
        }

        # 并发查询多个不同 tmdb_id
        if tmdb_ids_blocks:
            with ThreadPoolExecutor(max_workers=min(len(tmdb_ids_blocks), 5)) as executor:
                list(executor.map(self._fetch_blocks, tmdb_ids_blocks))

        if tmdb_ids_abs:
            with ThreadPoolExecutor(max_workers=min(len(tmdb_ids_abs), 5)) as executor:
                list(executor.map(lambda tid: self.map_absolute(tid, 1), tmdb_ids_abs))

        # 批量计算映射结果
        results = []
        for item in items:
            result = self.map_auto(item.get("tmdb_id"), item.get("season"), item.get("episode"))
            results.append(result)
        return results

    def map_absolute(self, tmdb_id: int, absolute_episode: int) -> tuple[int, int] | None:
        """
        将绝对集号映射到 TMDB 标准季集

        适用场景：标题中只有绝对集号（如 "Title - 72"），无季号信息
        TMDB 有多季时，按各季 episode_count 累加计算归属

        Returns:
            (target_season, target_episode) 或 None（失败/超出范围）
        """
        if not absolute_episode or absolute_episode < 1:
            return None
        if not self._tmdb:
            return None

        cache_key = f"abs:{tmdb_id}"
        seasons = self._blocks.get(cache_key)

        try:
            if not seasons:
                tv_info = self._tmdb.get_tmdb_info(MediaType.TV, tmdb_id)
                if not tv_info:
                    return None
                raw = [s for s in tv_info.get("seasons", []) if s.get("season_number", 0) > 0]
                if not raw:
                    return None
                seasons = sorted(raw, key=lambda s: s.get("season_number", 0))
                self._blocks[cache_key] = seasons

            total = 0
            for season in seasons:
                sn = season.get("season_number")
                count = season.get("episode_count", 0)
                start = total + 1
                end = total + count
                total += count
                if start <= absolute_episode <= end:
                    log.info(
                        f"【EpisodeMapper】TMDB:{tmdb_id} 绝对E{absolute_episode} → S{sn:02d}E{absolute_episode - start + 1:02d}"
                    )
                    return sn, absolute_episode - start + 1

            log.warn(f"【EpisodeMapper】绝对集号 {absolute_episode} 超出范围 (1-{total})")
            return None

        except Exception as e:
            log.warn(f"【EpisodeMapper】绝对集号映射失败: {e}")
            return None

    def invalidate(self, tmdb_id: int):
        self._blocks.pop(tmdb_id, None)
        self._blocks.pop(f"abs:{tmdb_id}", None)


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
