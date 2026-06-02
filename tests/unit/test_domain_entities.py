"""领域实体单元测试."""

from app.domain.entities.sync import SyncPathEntity
from app.domain.entities.word import CustomWordEntity
from app.domain.entities.transfer import TransferHistoryEntity
from app.domain.entities.download import DownloadHistoryEntity
from app.domain.entities.config import TorrentRemoveTaskEntity


class TestSyncPathEntity:
    def test_validate_empty_source(self):
        entity = SyncPathEntity(
            id=1,
            source="",
            dest="/dst",
            unknown="",
            mode="copy",
            compatibility=False,
            rename=False,
            enabled=True,
            note=None,
        )
        errors = entity.validate()
        assert "源目录不能为空" in errors

    def test_validate_root_source(self):
        entity = SyncPathEntity(
            id=1,
            source="/",
            dest="/dst",
            unknown="",
            mode="copy",
            compatibility=False,
            rename=False,
            enabled=True,
            note=None,
        )
        errors = entity.validate()
        assert "源目录不能是根目录" in errors

    def test_validate_invalid_mode(self):
        entity = SyncPathEntity(
            id=1,
            source="/src",
            dest="/dst",
            unknown="",
            mode="invalid",
            compatibility=False,
            rename=False,
            enabled=True,
            note=None,
        )
        errors = entity.validate()
        assert any("无效的同步模式" in e for e in errors)

    def test_validate_hardlink_cross_disk(self):
        result = SyncPathEntity.validate_hardlink("/a/src", "/b/dst")
        assert result == "硬链接不能跨盘"

    def test_validate_hardlink_same_disk(self):
        result = SyncPathEntity.validate_hardlink("/mnt/a/src", "/mnt/a/dst")
        assert result is None

    def test_is_subpath_true(self):
        assert SyncPathEntity.is_subpath("/parent", "/parent/child") is True

    def test_is_subpath_false(self):
        assert SyncPathEntity.is_subpath("/parent", "/other") is False

    def test_is_subpath_same(self):
        assert SyncPathEntity.is_subpath("/parent", "/parent") is True


class TestCustomWordEntity:
    def test_is_valid_replace(self):
        entity = CustomWordEntity(
            id=1,
            replaced="old",
            replace="new",
            front="",
            back="",
            offset="",
            type=2,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.is_valid is True

    def test_is_valid_offset(self):
        entity = CustomWordEntity(
            id=1,
            replaced=None,
            replace=None,
            front="f",
            back="b",
            offset="EP+1",
            type=4,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.is_valid is True

    def test_is_valid_invalid(self):
        entity = CustomWordEntity(
            id=1,
            replaced=None,
            replace=None,
            front="",
            back="",
            offset="",
            type=1,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.is_valid is False

    def test_validate_offset_valid(self):
        entity = CustomWordEntity(
            id=1,
            replaced=None,
            replace=None,
            front="",
            back="",
            offset="EP+1",
            type=4,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.validate_offset() is None

    def test_validate_offset_no_ep(self):
        entity = CustomWordEntity(
            id=1,
            replaced=None,
            replace=None,
            front="",
            back="",
            offset="1+2",
            type=4,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.validate_offset() == "偏移集数格式有误"

    def test_validate_offset_invalid_chars(self):
        entity = CustomWordEntity(
            id=1,
            replaced=None,
            replace=None,
            front="",
            back="",
            offset="EP+a",
            type=4,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.validate_offset() == "偏移集数格式有误"

    def test_validate_offset_not_offset_type(self):
        entity = CustomWordEntity(
            id=1,
            replaced="old",
            replace="new",
            front="",
            back="",
            offset="",
            type=2,
            group_id=1,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        assert entity.validate_offset() is None


class TestTransferHistoryEntity:
    def test_is_renamed_true(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电影",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="",
            source="",
            source_path="",
            source_filename="a.mkv",
            dest="",
            dest_path="",
            dest_filename="b.mkv",
            date="",
        )
        assert entity.is_renamed is True

    def test_is_renamed_false(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电影",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="",
            source="",
            source_path="",
            source_filename="a.mkv",
            dest="",
            dest_path="",
            dest_filename="a.mkv",
            date="",
        )
        assert entity.is_renamed is False

    def test_source_ext(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电影",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="",
            source="",
            source_path="",
            source_filename="a.mkv",
            dest="",
            dest_path="",
            dest_filename="b.mp4",
            date="",
        )
        assert entity.source_ext == ".mkv"

    def test_dest_ext(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电影",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="",
            source="",
            source_path="",
            source_filename="a.mkv",
            dest="",
            dest_path="",
            dest_filename="b.mp4",
            date="",
        )
        assert entity.dest_ext == ".mp4"

    def test_is_same_drive_true(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电影",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="",
            source="",
            source_path="/mnt/a/src",
            source_filename="",
            dest="",
            dest_path="/mnt/a/dst",
            dest_filename="",
            date="",
        )
        assert entity.is_same_drive is True

    def test_is_same_drive_false(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电影",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="",
            source="",
            source_path="/a/src",
            source_filename="",
            dest="",
            dest_path="/b/dst",
            dest_filename="",
            date="",
        )
        assert entity.is_same_drive is False

    def test_is_season_pack_no_episode(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电视剧",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="S01",
            source="",
            source_path="",
            source_filename="",
            dest="",
            dest_path="",
            dest_filename="",
            date="",
        )
        assert entity.is_season_pack is True

    def test_is_season_pack_with_episode(self):
        entity = TransferHistoryEntity(
            id=1,
            mode="copy",
            media_type="电视剧",
            category="",
            tmdb_id=0,
            title="",
            year="",
            season_episode="S01E01",
            source="",
            source_path="",
            source_filename="",
            dest="",
            dest_path="",
            dest_filename="",
            date="",
        )
        assert entity.is_season_pack is False


class TestDownloadHistoryEntity:
    def test_is_movie(self):
        entity = DownloadHistoryEntity(
            id=1,
            title="",
            year="",
            media_type="movie",
            tmdb_id="",
            season_episode="",
            vote="",
            poster="",
            overview="",
            torrent="",
            enclosure="",
            site="",
            description="",
            downloader="",
            download_id="",
            save_path="",
            date="",
        )
        assert entity.is_movie is True
        assert entity.is_tv is False
        assert entity.is_anime is False

    def test_is_tv(self):
        entity = DownloadHistoryEntity(
            id=1,
            title="",
            year="",
            media_type="tv",
            tmdb_id="",
            season_episode="",
            vote="",
            poster="",
            overview="",
            torrent="",
            enclosure="",
            site="",
            description="",
            downloader="",
            download_id="",
            save_path="",
            date="",
        )
        assert entity.is_tv is True

    def test_parsed_season(self):
        entity = DownloadHistoryEntity(
            id=1,
            title="",
            year="",
            media_type="电视剧",
            tmdb_id="",
            season_episode="S01E02",
            vote="",
            poster="",
            overview="",
            torrent="",
            enclosure="",
            site="",
            description="",
            downloader="",
            download_id="",
            save_path="",
            date="",
        )
        assert entity.parsed_season == 1

    def test_parsed_season_none(self):
        entity = DownloadHistoryEntity(
            id=1,
            title="",
            year="",
            media_type="电影",
            tmdb_id="",
            season_episode="",
            vote="",
            poster="",
            overview="",
            torrent="",
            enclosure="",
            site="",
            description="",
            downloader="",
            download_id="",
            save_path="",
            date="",
        )
        assert entity.parsed_season is None

    def test_parsed_episodes(self):
        entity = DownloadHistoryEntity(
            id=1,
            title="",
            year="",
            media_type="电视剧",
            tmdb_id="",
            season_episode="S01E01-E02",
            vote="",
            poster="",
            overview="",
            torrent="",
            enclosure="",
            site="",
            description="",
            downloader="",
            download_id="",
            save_path="",
            date="",
        )
        assert entity.parsed_episodes == [1, 2]

    def test_parsed_episodes_empty(self):
        entity = DownloadHistoryEntity(
            id=1,
            title="",
            year="",
            media_type="电影",
            tmdb_id="",
            season_episode="",
            vote="",
            poster="",
            overview="",
            torrent="",
            enclosure="",
            site="",
            description="",
            downloader="",
            download_id="",
            save_path="",
            date="",
        )
        assert entity.parsed_episodes == []


class TestTorrentRemoveTaskEntity:
    def test_parsed_config(self):
        entity = TorrentRemoveTaskEntity(id=1, name="test", downloader="qbit", config='{"action": 2}', enabled=True)
        assert entity.parsed_config == {"action": 2}

    def test_parsed_config_empty(self):
        entity = TorrentRemoveTaskEntity(id=1, name="test", downloader="qbit", config="", enabled=True)
        assert entity.parsed_config == {}

    def test_action_display(self):
        entity = TorrentRemoveTaskEntity(id=1, name="test", downloader="qbit", config='{"action": 2}', enabled=True)
        assert entity.action_display == "删除种子"

    def test_action_display_unknown(self):
        entity = TorrentRemoveTaskEntity(id=1, name="test", downloader="qbit", config='{"action": 99}', enabled=True)
        assert entity.action_display == "未知"

    def test_validate_params_valid(self):
        data = {"name": "test", "action": 2, "interval": 60, "enabled": 1, "samedata": 0, "only_nexus_media": 1}
        errors = TorrentRemoveTaskEntity.validate_params(data)
        assert errors == []

    def test_validate_params_invalid_action(self):
        data = {"name": "test", "action": 5}
        errors = TorrentRemoveTaskEntity.validate_params(data)
        assert "动作参数不合法" in errors

    def test_validate_params_missing_name(self):
        data = {"name": ""}
        errors = TorrentRemoveTaskEntity.validate_params(data)
        assert "名称参数不合法" in errors

    def test_validate_config_invalid_ratio(self):
        errors = TorrentRemoveTaskEntity.validate_config({"ratio": "abc"})
        assert "分享率参数不合法" in errors

    def test_validate_config_invalid_size(self):
        errors = TorrentRemoveTaskEntity.validate_config({"size": [1]})
        assert "种子大小参数不合法" in errors
