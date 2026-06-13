"""PathUtils 单元测试."""

from app.utils.path_utils import PathUtils


class TestPathUtils:
    def test_get_dir_files_empty_path(self):
        assert PathUtils.get_dir_files("") == []

    def test_get_dir_files_missing_path(self):
        assert PathUtils.get_dir_files("/nonexistent/path") == []

    def test_get_dir_files_filter_ext(self, tmp_path):
        (tmp_path / "a.mkv").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        files = PathUtils.get_dir_files(str(tmp_path), exts=[".mkv"])
        assert len(files) == 1
        assert files[0].endswith("a.mkv")

    def test_get_dir_files_filter_size(self, tmp_path):
        small = tmp_path / "small.mkv"
        small.write_text("x")
        files = PathUtils.get_dir_files(str(tmp_path), filesize=10)
        assert files == []

    def test_get_dir_files_single_file(self, tmp_path):
        f = tmp_path / "movie.mkv"
        f.write_text("x" * 100)
        files = PathUtils.get_dir_files(str(f), exts=[".mkv"], filesize=10)
        assert len(files) == 1

    def test_get_dir_files_invalid_path(self, tmp_path):
        bad = tmp_path / "@Recycle" / "a.mkv"
        bad.parent.mkdir()
        bad.write_text("x")
        files = PathUtils.get_dir_files(str(bad.parent))
        assert files == []

    def test_get_dir_level1_files(self, tmp_path):
        (tmp_path / "a.mkv").write_text("x")
        (tmp_path / "b").mkdir()
        files = PathUtils.get_dir_level1_files(str(tmp_path), exts=[".mkv"])
        assert len(files) == 1

    def test_get_dir_level1_medias(self, tmp_path):
        (tmp_path / "a.mkv").write_text("x")
        (tmp_path / "b").mkdir()
        result = PathUtils.get_dir_level1_medias(str(tmp_path), exts=[".mkv"])
        assert len(result) == 2

    def test_is_invalid_path(self):
        assert PathUtils.is_invalid_path("") is True
        assert PathUtils.is_invalid_path("/media/@Recycle/file") is True
        assert PathUtils.is_invalid_path("/media/.hidden/file") is True
        assert PathUtils.is_invalid_path("/media/movie.mkv") is False

    def test_is_path_in_path(self):
        assert PathUtils.is_path_in_path("/a/b", "/a/b/c/d") is True
        assert PathUtils.is_path_in_path("/a/b", "/a/b") is True
        assert PathUtils.is_path_in_path("/a/b", "/x/y") is False
        assert PathUtils.is_path_in_path("", "/a/b") is False

    def test_get_bluray_dir_root(self, tmp_path):
        bdmv = tmp_path / "BDMV"
        bdmv.mkdir()
        (bdmv / "index.bdmv").write_text("x")
        assert PathUtils.get_bluray_dir(str(tmp_path)) == str(tmp_path)

    def test_get_bluray_dir_bdmv_subdir(self, tmp_path):
        bdmv = tmp_path / "BDMV"
        bdmv.mkdir()
        (bdmv / "index.bdmv").write_text("x")
        assert PathUtils.get_bluray_dir(str(bdmv)) == str(tmp_path)

    def test_get_bluray_dir_stream(self, tmp_path):
        bdmv = tmp_path / "BDMV"
        stream = bdmv / "STREAM"
        stream.mkdir(parents=True)
        (bdmv / "index.bdmv").write_text("x")
        assert PathUtils.get_bluray_dir(str(stream)) == str(tmp_path)

    def test_get_bluray_dir_none(self, tmp_path):
        assert PathUtils.get_bluray_dir(str(tmp_path)) is None
        assert PathUtils.get_bluray_dir("") is None

    def test_get_parent_paths(self):
        assert PathUtils.get_parent_paths("/a/b/c", 1) == "/a/b"
        assert PathUtils.get_parent_paths("/a/b/c", 2) == "/a"
