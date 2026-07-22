"""Scraper 配置热加载回归测试.

修复前：Scraper 单例只在启动时读取一次 UserScraperConf，
运行期保存刮削配置后 gen_scraper_files 仍使用旧的空配置导致跳过刮削。
修复后：gen_scraper_files 每次调用前重新读取配置。
"""

from unittest.mock import MagicMock

from app.media.scraper import Scraper


def _build_scraper(scraper_conf):
    system_config = MagicMock()
    system_config.get.return_value = scraper_conf
    media_service = MagicMock()
    scraper = Scraper(media_service=media_service, system_config=system_config)
    return scraper, system_config


class TestScraperConfigHotReload:
    """验证运行期配置变更对 gen_scraper_files 生效."""

    def test_config_change_after_init_takes_effect(self):
        """创建时配置为空，保存配置后再次刮削应读取到新配置."""
        scraper, system_config = _build_scraper(None)
        assert scraper._scraper_nfo == {}

        media = MagicMock()
        media.tmdb_info = {"id": 1}
        # 配置为空时应跳过（不调用刮削内部逻辑）
        scraper._scrape_movie = MagicMock()
        scraper._scrape_tv = MagicMock()
        scraper.gen_scraper_files(media=media, dir_path="/tmp", file_name="f", file_ext=".mkv")
        scraper._scrape_tv.assert_not_called()
        scraper._scrape_movie.assert_not_called()

        # 运行期保存配置
        system_config.get.return_value = {
            "scraper_nfo": {"tv": {"basic": True}},
            "scraper_pic": {},
        }
        # 再次调用应读取到新配置并继续执行到 _scrape_tv
        media.type = MagicMock()
        from app.domain.mediatypes import MediaType

        media.type = MediaType.TV
        scraper._scrape_tv = MagicMock()
        scraper.gen_scraper_files(media=media, dir_path="/tmp", file_name="f", file_ext=".mkv")
        scraper._scrape_tv.assert_called_once()

    def test_empty_config_still_skips(self):
        """配置始终为空时仍应跳过刮削."""
        scraper, _ = _build_scraper(None)
        scraper._scrape_movie = MagicMock()
        scraper._scrape_tv = MagicMock()
        media = MagicMock()
        media.tmdb_info = {"id": 1}
        scraper.gen_scraper_files(media=media, dir_path="/tmp", file_name="f", file_ext=".mkv")
        scraper._scrape_tv.assert_not_called()
        scraper._scrape_movie.assert_not_called()
