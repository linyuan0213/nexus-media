"""测试文件列表层类型推断"""

import pytest

from app.downloader.pipeline import DownloadPipeline


class TestInferTypeFromFiles:
    TV_PATTERNS = [
        (["Show - 01.mkv", "Show - 02.mkv", "Show - 03.mkv"], "tv"),
        (["Show_01.mkv", "Show_02.mkv", "Show_03.mkv", "Show_04.mkv"], "tv"),
        (["S01E01.mkv", "S01E02.mkv", "S01E03.mkv"], "tv"),
        (["[Group] Title EP01 [1080P].mkv", "[Group] Title EP02 [1080P].mkv", "[Group] Title EP03 [1080P].mkv"], "tv"),
        (["path/to/Show.E01.mkv", "path/to/Show.E02.mkv", "path/to/Show.E03.mkv"], "tv"),
    ]

    MOVIE_PATTERNS = [
        (["Movie Title.mkv"], "movie"),
        (["/path/to/BDRip.mkv"], "movie"),
    ]

    NO_SIGNAL_PATTERNS = [
        ([], None),
        (["file1.mkv", "file2.mkv"], None),
        (["disc1.mkv", "disc2.mkv"], None),
        (["Show - 01.mkv", "Show - 02.mkv"], None),
        (["Show - 03.mkv", "Show - 01.mkv", "Show - 02.mkv"], None),  # non-sequential
        (["Extra.mkv", "Menu.mkv", "Trailer.mkv", "Feature.mkv"], None),  # no numbers
    ]

    @pytest.mark.parametrize("files,expected", TV_PATTERNS)
    def test_tv_patterns(self, files, expected):
        assert DownloadPipeline._infer_type_from_files(files) == expected

    @pytest.mark.parametrize("files,expected", MOVIE_PATTERNS)
    def test_movie_patterns(self, files, expected):
        assert DownloadPipeline._infer_type_from_files(files) == expected

    @pytest.mark.parametrize("files,expected", NO_SIGNAL_PATTERNS)
    def test_no_signal_patterns(self, files, expected):
        assert DownloadPipeline._infer_type_from_files(files) == expected


class TestFileTypeMismatch:
    def test_no_mismatch_when_no_files(self, capsys):
        from unittest.mock import MagicMock

        media_info = MagicMock()
        DownloadPipeline._check_file_type_mismatch(media_info, [])
        captured = capsys.readouterr()
        assert "类型推断不一致" not in captured.err

    def test_no_mismatch_when_ambiguous(self, capsys):
        from unittest.mock import MagicMock

        media_info = MagicMock()
        DownloadPipeline._check_file_type_mismatch(media_info, ["a.mkv", "b.mkv"])
        captured = capsys.readouterr()
        assert "类型推断不一致" not in captured.err
