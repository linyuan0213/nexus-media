"""
完整真实场景测试：Re:Zero 第四季集数映射（修复 Parser 后）
"""

import os
import sys
from unittest.mock import MagicMock

from app.media.lookup.tmdb_lookup import TmdbLookup
from app.media.models import MediaInfo
from app.media.parser.episode_mapper import EpisodeMapper
from app.media.parser.regex import RegexParser

sys.modules["log"] = MagicMock()

os.environ["NASTOOL_CONFIG"] = "/home/linyuan/python/config/config.yaml"


def test_rezero_full_scenario():
    title = "[晚街与灯][Re：从零开始的异世界生活 第四季 / Re:Zero kara Hajimeru Isekai Seikatsu 4th Season][04 - 总第70][WebRip][1080P_AVC_AAC][简日双语内嵌]"

    print("=" * 70)
    print("真实场景测试：Re:Zero 第四季（修复 Parser 后）")
    print("=" * 70)
    print(f"\n原标题:\n  {title}")

    # 1. Parser 解析
    parser = RegexParser()
    parsed = parser.parse(title)

    print("\n【Step 1: Parser 解析结果】")
    print(f"  中文名: {parsed.title_cn}")
    print(f"  英文名: {parsed.title_en}")
    print(f"  类型: {parsed.type}")
    print(f"  季: {parsed.season}")
    print(f"  集: {parsed.episode}")
    print(f"  年份: {parsed.year}")

    assert parsed.season == 4, f"Expected season=4, got {parsed.season}"
    assert parsed.episode == 4, f"Expected episode=4, got {parsed.episode}"
    print("  ✓ Parser 正确解析出 season=4, episode=4")

    # 2. TMDB 查询
    print("\n【Step 2: TMDB 查询】")
    lookup = TmdbLookup()
    result = lookup.lookup(parsed, hint_type=None, strict=False, language="zh")

    assert result is not None, "TMDB 应找到匹配结果"
    print(f"  TMDB ID: {result.tmdb_id}")
    print(f"  标题: {result.title}")
    print(f"  类型: {result.media_type}")

    # 3. EpisodeMapper 映射
    print("\n【Step 3: EpisodeMapper 自动映射】")
    mapper = EpisodeMapper(lookup)
    mapped = mapper.map(result.tmdb_id, parsed.season, parsed.episode)

    assert mapped is not None, "EpisodeMapper 应返回映射结果"
    target_season, target_episode = mapped
    print(f"  S{parsed.season:02d}E{parsed.episode:02d} → S{target_season:02d}E{target_episode:02d}")

    # 4. 组装完整 MediaInfo
    print("\n【Step 4: 最终 MediaInfo】")
    info = MediaInfo.from_parser(parsed)
    info.tmdb_id = result.tmdb_id
    info.title = result.title
    if mapped:
        info.begin_season = mapped[0]
        info.begin_episode = mapped[1]

    print(f"  标题: {info.title}")
    print(f"  TMDB ID: {info.tmdb_id}")
    print("  原始: S04E04 (总第70集)")
    print(f"  映射后: S{info.begin_season:02d}E{info.begin_episode:02d}")

    # 验证：S04E04 应该映射到 S01E70
    assert info.begin_season == 1, f"Expected mapped season=1, got {info.begin_season}"
    assert info.begin_episode == 70, f"Expected mapped episode=70, got {info.begin_episode}"
    print("  ✓ 映射验证通过: S04E04 → S01E70")

    print("\n" + "=" * 70)
    print("测试全部通过！")
    print("=" * 70)


if __name__ == "__main__":
    test_rezero_full_scenario()
