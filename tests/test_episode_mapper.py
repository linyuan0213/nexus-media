# -*- coding: utf-8 -*-
"""
EpisodeMapper 单元测试
"""
import sys
from datetime import datetime
from unittest.mock import MagicMock

sys.modules['log'] = MagicMock()

from app.media.parser.episode_mapper import EpisodeMapper, _parse_date


class TestParseDate:
    def test_valid_date(self):
        assert _parse_date("2024-01-15") == datetime(2024, 1, 15)

    def test_invalid_date(self):
        assert _parse_date("invalid") is None

    def test_none(self):
        assert _parse_date(None) is None


class TestEpisodeMapper:
    def _mock_tmdb(self, seasons, episodes):
        """创建模拟的 TMDB lookup"""
        tmdb = MagicMock()
        tmdb.get_tmdb_info.return_value = {"seasons": seasons}
        tmdb.season.get_episodes.return_value = episodes
        return tmdb

    def test_no_mapping_needed_normal_tv(self):
        """普通电视剧：TMDB 季数 >= Parser 季数，无需映射"""
        seasons = [
            {"season_number": 1, "episode_count": 10},
            {"season_number": 2, "episode_count": 10},
            {"season_number": 3, "episode_count": 10},
        ]
        episodes = [{"episode_number": i, "air_date": "2024-01-%02d" % i} for i in range(1, 11)]
        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        # Parser S02E05，TMDB 有 S02，无需映射
        result = mapper.map(12345, 2, 5)
        assert result is None

    def test_merged_season_mapping(self):
        """合并季：TMDB 只有 S01，Parser 解析出 S04E02"""
        seasons = [
            {"season_number": 1, "episode_count": 91},
        ]
        # 模拟4个季块，每季约20-25集
        # 分季逻辑：间隔 >90天 且 当前block已有20+集 才分季
        episodes = []
        for i in range(1, 92):
            if i <= 25:
                # Block 1: 2021-01-01 ~ 2021-01-25
                date = "2021-01-%02d" % i
            elif i <= 50:
                # Block 2: 2021-05-01 ~ 2021-05-25 (gap = 95 days)
                date = "2021-05-%02d" % (i - 25)
            elif i <= 70:
                # Block 3: 2021-09-01 ~ 2021-09-20 (gap = 99 days, length=20)
                date = "2021-09-%02d" % (i - 50)
            else:
                # Block 4: 2022-01-01 ~ 2022-01-21 (gap = 103 days, length=21)
                date = "2022-01-%02d" % (i - 70)
            episodes.append({"episode_number": i, "air_date": date})

        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        # 第4季第2集应该映射到 S01 的某集
        result = mapper.map(12345, 4, 2)
        assert result is not None
        target_season, target_ep = result
        assert target_season == 1
        # 第4季从 E71 开始，第2集 = E72
        assert target_ep == 72

    def test_single_season_no_mapping(self):
        """单季正常剧集（<30集），不触发映射"""
        seasons = [
            {"season_number": 1, "episode_count": 12},
        ]
        episodes = [{"episode_number": i, "air_date": "2024-01-%02d" % i} for i in range(1, 13)]
        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        result = mapper.map(12345, 1, 5)
        assert result is None

    def test_out_of_range_season(self):
        """Parser 季号超出推断范围"""
        seasons = [
            {"season_number": 1, "episode_count": 50},
        ]
        episodes = []
        for i in range(1, 51):
            if i <= 25:
                date = "2024-01-%02d" % i
            else:
                date = "2024-06-%02d" % (i - 25)
            episodes.append({"episode_number": i, "air_date": date})

        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        # 只有2个季块，请求第5季
        result = mapper.map(12345, 5, 1)
        assert result is None

    def test_out_of_range_episode(self):
        """映射后集号超出该季范围"""
        seasons = [
            {"season_number": 1, "episode_count": 50},
        ]
        episodes = []
        for i in range(1, 51):
            if i <= 25:
                date = "2024-01-%02d" % i
            else:
                date = "2024-06-%02d" % (i - 25)
            episodes.append({"episode_number": i, "air_date": date})

        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        # 第2季只有 E26-E50（25集），请求第30集
        result = mapper.map(12345, 2, 30)
        assert result is None

    def test_map_auto_fallback_to_absolute(self):
        """map_auto: 合并季映射失败时回退到绝对集号映射

        场景：S02 - 46，但 46 是绝对集号（从第一季开始累计）
        - 合并季映射：season=2, episode=46，但 block 2 只有 25 集 → 失败
        - 回退到绝对集号：E46 对应 S01E46 → 成功
        """
        seasons = [
            {"season_number": 1, "episode_count": 50},
        ]
        episodes = []
        for i in range(1, 51):
            if i <= 25:
                date = "2024-01-%02d" % i
            else:
                date = "2024-06-%02d" % (i - 25)
            episodes.append({"episode_number": i, "air_date": date})

        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        # Parser 解析出 season=2, episode=46，但 46 超出 block 2 的范围 (26-50)
        result = mapper.map_auto(12345, 2, 46)
        assert result is not None
        target_season, target_ep = result
        assert target_season == 1
        assert target_ep == 46  # E46 仍在 S01 范围内

    def test_cache_invalidation(self):
        """缓存失效"""
        seasons = [
            {"season_number": 1, "episode_count": 50},
        ]
        episodes = []
        for i in range(1, 51):
            if i <= 25:
                date = "2024-01-%02d" % i
            else:
                date = "2024-06-%02d" % (i - 25)
            episodes.append({"episode_number": i, "air_date": date})

        tmdb = self._mock_tmdb(seasons, episodes)
        mapper = EpisodeMapper(tmdb)

        # 第一次查询，缓存结果
        mapper.map(12345, 2, 1)
        assert 12345 in mapper._blocks

        # 失效缓存
        mapper.invalidate(12345)
        assert 12345 not in mapper._blocks
