"""站点数据统计消息格式测试."""

from app.sites.site_userinfo import SiteUserInfo


class TestBuildStatsMessageRows:
    def test_compact_rows_with_totals(self):
        rows, inc_up, inc_dl = SiteUserInfo._build_stats_message_rows(
            [("观众", 1024 * 1024, 0), ("M-Team", 0, 0), ("憨憨", 2048, 4096), ("高清杜比", 0, 1024)]
        )
        assert inc_up == 1024 * 1024 + 2048
        assert inc_dl == 4096 + 1024
        assert rows[0].startswith("共 3 个站点")
        assert rows[1] == ""
        assert rows[2].startswith("1. 观众")
        assert "⬆️ 1.0M" in rows[2]
        assert "⬇️ -" in rows[2]  # 下载为 0 时占位，保持列对齐
        assert rows[3].startswith("2. 憨憨")
        assert "⬆️ 2.0K" in rows[3] and "⬇️ 4.0K" in rows[3]
        assert rows[4].startswith("3. 高清杜比")
        assert "⬆️ -" in rows[4] and "⬇️ 1.0K" in rows[4]

        # 中英混排站点名按显示宽度对齐：箭头起始列宽一致
        def arrow_prefix_width(row: str) -> int:
            return SiteUserInfo._display_width(row.split("⬆️")[0])

        widths = {arrow_prefix_width(rows[i]) for i in (2, 3, 4)}
        assert len(widths) == 1
        # 不再使用 em-dash 分隔线，且每站一行
        assert all("————" not in row for row in rows)
        assert len(rows) == 5

    def test_no_activity_returns_empty(self):
        rows, inc_up, inc_dl = SiteUserInfo._build_stats_message_rows([("A", 0, 0)])
        assert rows == []
        assert inc_up == 0
        assert inc_dl == 0
