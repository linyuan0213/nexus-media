"""TMDB lookup 工具函数测试."""

from app.domain.mediatypes import MediaType
from app.media.lookup.tmdb_lookup import TmdbLookup
from app.media.models import MediaInfo


class TestMergeMediaInfo:
    """测试 merge_media_info 合并媒体信息."""

    def test_merge_media_info_copies_image_fields(self):
        """搜索结果缺少图片时应从原始匹配媒体复制图片字段."""
        target = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            year="2026",
            tmdb_id=123456,
        )
        source = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            year="2026",
            tmdb_id=123456,
            poster_path="https://image.tmdb.org/t/p/w500/abc.jpg",
            backdrop_path="https://image.tmdb.org/t/p/w1280/xyz.jpg",
            fanart_backdrop="https://fanart.tv/123.jpg",
        )

        result = TmdbLookup.merge_media_info(target, source)

        assert result.poster_path == "https://image.tmdb.org/t/p/w500/abc.jpg"
        assert result.backdrop_path == "https://image.tmdb.org/t/p/w1280/xyz.jpg"
        assert result.fanart_backdrop == "https://fanart.tv/123.jpg"

    def test_merge_media_info_keeps_target_image(self):
        """目标本身有图片时保留目标的图片."""
        target = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            poster_path="https://target.poster.jpg",
        )
        source = MediaInfo(
            title="攻壳机动队",
            type=MediaType.TV,
            poster_path="https://source.poster.jpg",
        )

        result = TmdbLookup.merge_media_info(target, source)

        assert result.poster_path == "https://target.poster.jpg"

    def test_merge_media_info_returns_target_when_source_is_none(self):
        """source 为空时返回 target."""
        target = MediaInfo(title="Test", type=MediaType.MOVIE)
        assert TmdbLookup.merge_media_info(target, None) is target

    def test_merge_media_info_returns_target_when_target_is_none(self):
        """target 为空时返回 target."""
        source = MediaInfo(title="Test", type=MediaType.MOVIE)
        assert TmdbLookup.merge_media_info(None, source) is None
