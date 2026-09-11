"""刮削 NFO 基础名计算测试（避免生成 xxx.mkv.nfo）."""

from app.services.transfer.filetransfer_service import FileTransferService


class TestScrapeFileBaseName:
    def test_strips_file_extension(self):
        assert (
            FileTransferService._scrape_file_base_name("/video/一级指控 (2021) - 2160p.mkv", "/video")
            == "一级指控 (2021) - 2160p"
        )

    def test_strips_only_last_extension(self):
        assert FileTransferService._scrape_file_base_name("/v/Show.S01E01.1080p.mkv", "/v") == "Show.S01E01.1080p"

    def test_dir_path_keeps_dots(self):
        # 蓝光原盘：无文件路径时取目录名，保留目录中的点
        assert FileTransferService._scrape_file_base_name(None, "/video/Show.S01") == "Show.S01"

    def test_file_without_extension(self):
        assert FileTransferService._scrape_file_base_name("/v/noext", "/v") == "noext"

    def test_both_empty(self):
        assert FileTransferService._scrape_file_base_name(None, None) == ""
