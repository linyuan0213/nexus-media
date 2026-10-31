"""PathUtils 下载完整性判断测试."""

from app.utils.path_utils import PathUtils


def test_completed_media_suffix_dir_is_not_incomplete(tmp_path):
    source = tmp_path / "download-001.mp4"
    source.mkdir()
    (source / "info.mp4").write_bytes(b"x")

    assert PathUtils.is_incomplete_media_dir(str(source)) is False


def test_incomplete_media_dir_by_xltd_marker(tmp_path):
    source = tmp_path / "Movie"
    source.mkdir()
    (source / "Movie.mp4.xltd").write_text("", encoding="utf-8")
    (source / "Movie.mp4").write_bytes(b"x")

    assert PathUtils.is_incomplete_media_dir(str(source)) is True


def test_completed_media_dir_is_not_incomplete(tmp_path):
    source = tmp_path / "Movie"
    source.mkdir()
    (source / "Movie.mkv").write_bytes(b"x")

    assert PathUtils.is_incomplete_media_dir(str(source)) is False


def test_incomplete_media_dir_by_xltd_directory(tmp_path):
    source = tmp_path / "Movie"
    source.mkdir()
    (source / "part.xltd").mkdir()

    assert PathUtils.is_incomplete_media_dir(str(source)) is True
