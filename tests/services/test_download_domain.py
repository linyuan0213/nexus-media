"""
下载领域层单元测试
测试DownloadHistory/Setting/IndexerStatistics实体和适配器
"""

from unittest.mock import MagicMock

from app.db.repositories.download_repo_adapter import (
    DownloadHistoryRepositoryAdapter,
    DownloadSettingRepositoryAdapter,
    IndexerStatisticsRepositoryAdapter,
)
from app.domain.entities.download import (
    DownloaderEntity,
    DownloadHistoryEntity,
    DownloadSettingEntity,
    IndexerStatisticsEntity,
)


class TestDownloaderEntity:
    """测试DownloaderEntity领域实体"""

    def test_from_orm_success(self):
        """测试从ORM模型成功转换"""
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.NAME = "qb1"
        mock_orm.ENABLED = 1
        mock_orm.TYPE = "qbittorrent"
        mock_orm.TRANSFER = 1
        mock_orm.ONLY_NEXUS_MEDIA = 0
        mock_orm.MATCH_PATH = 1
        mock_orm.RMT_MODE = "link"
        mock_orm.CONFIG = '{"host": "127.0.0.1"}'
        mock_orm.DOWNLOAD_DIR = "/downloads"

        entity = DownloaderEntity.from_orm(mock_orm)

        assert entity is not None
        assert entity.id == 1
        assert entity.name == "qb1"
        assert entity.enabled is True
        assert entity.type == "qbittorrent"
        assert entity.transfer is True
        assert entity.only_nexus_media is False
        assert entity.match_path is True
        assert entity.rmt_mode == "link"
        assert entity.config == '{"host": "127.0.0.1"}'
        assert entity.download_dir == "/downloads"

    def test_from_orm_none(self):
        """测试ORM为None时返回None"""
        assert DownloaderEntity.from_orm(None) is None

    def test_to_dict(self):
        """测试转换为字典"""
        entity = DownloaderEntity(
            id=1,
            name="test",
            enabled=True,
            type="transmission",
            transfer=True,
            only_nexus_media=False,
            match_path=True,
            rmt_mode="copy",
            config="{}",
            download_dir="/dl",
        )
        d = entity.to_dict()
        assert d["id"] == 1
        assert d["name"] == "test"
        assert d["enabled"] is True


class TestDownloadHistoryEntity:
    """测试DownloadHistoryEntity领域实体"""

    def test_from_orm_success(self):
        """测试从ORM模型成功转换"""
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.TITLE = "Test Movie"
        mock_orm.YEAR = "2023"
        mock_orm.TYPE = "MOV"
        mock_orm.TMDBID = "12345"
        mock_orm.SE = "S01E01"
        mock_orm.VOTE = "8.5"
        mock_orm.POSTER = "http://poster.jpg"
        mock_orm.OVERVIEW = "Overview"
        mock_orm.TORRENT = "test.torrent"
        mock_orm.ENCLOSURE = "enc123"
        mock_orm.SITE = "SiteA"
        mock_orm.DESC = "Description"
        mock_orm.DOWNLOADER = "qb1"
        mock_orm.DOWNLOAD_ID = "dl123"
        mock_orm.SAVE_PATH = "/downloads"
        mock_orm.DATE = "2023-01-01 12:00:00"

        entity = DownloadHistoryEntity.from_orm(mock_orm)

        assert entity is not None
        assert entity.title == "Test Movie"
        assert entity.year == "2023"
        assert entity.media_type == "MOV"
        assert entity.tmdb_id == "12345"
        assert entity.season_episode == "S01E01"

    def test_from_orm_none(self):
        """测试ORM为None时返回None"""
        assert DownloadHistoryEntity.from_orm(None) is None

    def test_to_dict(self):
        """测试转换为字典"""
        entity = DownloadHistoryEntity(
            id=1,
            title="Test",
            year="2023",
            media_type="MOV",
            tmdb_id="123",
            season_episode="S01",
            vote="8.0",
            poster="url",
            overview="desc",
            torrent="t.t",
            enclosure="enc",
            site="site",
            description="desc",
            downloader="qb",
            download_id="dl1",
            save_path="/dl",
            date="2023-01-01",
        )
        d = entity.to_dict()
        assert d["title"] == "Test"
        assert d["tmdbid"] == "123"


class TestDownloadSettingEntity:
    """测试DownloadSettingEntity领域实体"""

    def test_from_orm_success(self):
        """测试从ORM模型成功转换"""
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.NAME = "HD Settings"
        mock_orm.CATEGORY = "Movie"
        mock_orm.TAGS = "hd,tag"
        mock_orm.IS_PAUSED = 0
        mock_orm.UPLOAD_LIMIT = 1024
        mock_orm.DOWNLOAD_LIMIT = 2048
        mock_orm.RATIO_LIMIT = 200  # 2.0 * 100
        mock_orm.SEEDING_TIME_LIMIT = 1440
        mock_orm.DOWNLOADER = "qb1"
        mock_orm.NOTE = "Note"

        entity = DownloadSettingEntity.from_orm(mock_orm)

        assert entity is not None
        assert entity.name == "HD Settings"
        assert entity.is_paused is False
        assert entity.upload_limit == 1024
        assert entity.ratio_limit == 200

    def test_from_orm_none(self):
        """测试ORM为None时返回None"""
        assert DownloadSettingEntity.from_orm(None) is None

    def test_to_dict(self):
        """测试转换为字典"""
        entity = DownloadSettingEntity(
            id=1,
            name="Test",
            category="TV",
            tags="tag1",
            is_paused=True,
            upload_limit=100,
            download_limit=200,
            ratio_limit=150,
            seeding_time_limit=60,
            downloader="qb",
            note="note",
        )
        d = entity.to_dict()
        assert d["name"] == "Test"
        assert d["is_paused"] is True


class TestIndexerStatisticsEntity:
    """测试IndexerStatisticsEntity领域实体"""

    def test_to_dict(self):
        """测试转换为字典"""
        entity = IndexerStatisticsEntity(indexer="SiteA", total=100, fail=5, success=95, avg_seconds=1.5)
        d = entity.to_dict()
        assert d["indexer"] == "SiteA"
        assert d["total"] == 100
        assert d["fail"] == 5
        assert d["success"] == 95
        assert d["avg_seconds"] == 1.5


class TestDownloadHistoryRepositoryAdapter:
    """测试DownloadHistoryRepositoryAdapter适配器"""

    def _create_mock_repo(self):
        return MagicMock()

    def test_is_exists(self):
        """测试存在性检查"""
        mock_repo = self._create_mock_repo()
        mock_repo.is_exists_download_history.return_value = True

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        result = adapter.is_exists("enc123", "qb", "dl1")

        assert result is True
        mock_repo.is_exists_download_history.assert_called_once_with("enc123", "qb", "dl1")

    def test_is_exists_by_tmdb(self):
        """测试按TMDB检查存在性"""
        mock_repo = self._create_mock_repo()
        mock_repo.is_exists_download_history_by_tmdb.return_value = False

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        result = adapter.is_exists_by_tmdb("12345", "S01")

        assert result is False
        mock_repo.is_exists_download_history_by_tmdb.assert_called_once_with("12345", "S01")

    def test_insert(self):
        """测试插入历史"""
        mock_repo = self._create_mock_repo()
        mock_media = MagicMock()

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        adapter.insert(mock_media, "qb", "dl1", "/dl")

        mock_repo.insert_download_history.assert_called_once_with(mock_media, "qb", "dl1", "/dl")

    def test_get_all_empty(self):
        """测试空列表返回"""
        mock_repo = self._create_mock_repo()
        mock_repo.get_download_history.return_value = []

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        result = adapter.get_all()

        assert result == []

    def test_get_by_title(self):
        """测试按标题查询"""
        mock_repo = self._create_mock_repo()
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.TITLE = "Test"
        mock_repo.get_download_history_by_title.return_value = [mock_orm]

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        result = adapter.get_by_title("Test")

        assert len(result) == 1
        assert result[0].title == "Test"

    def test_get_by_path(self):
        """测试按路径查询"""
        mock_repo = self._create_mock_repo()
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.SAVE_PATH = "/downloads"
        mock_repo.get_download_history_by_path.return_value = mock_orm

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        result = adapter.get_by_path("/downloads")

        assert result is not None
        assert result.save_path == "/downloads"

    def test_get_by_path_none(self):
        """测试按路径查询无结果"""
        mock_repo = self._create_mock_repo()
        mock_repo.get_download_history_by_path.return_value = None

        adapter = DownloadHistoryRepositoryAdapter(mock_repo)
        result = adapter.get_by_path("/notexist")

        assert result is None


class TestDownloadSettingRepositoryAdapter:
    """测试DownloadSettingRepositoryAdapter适配器"""

    def _create_mock_repo(self):
        return MagicMock()

    def test_delete(self):
        """测试删除设置"""
        mock_repo = self._create_mock_repo()

        adapter = DownloadSettingRepositoryAdapter(mock_repo)
        adapter.delete(1)

        mock_repo.delete_download_setting.assert_called_once_with(1)

    def test_get_all(self):
        """测试获取所有设置"""
        mock_repo = self._create_mock_repo()
        mock_orm = MagicMock()
        mock_orm.ID = 1
        mock_orm.NAME = "Test"
        mock_repo.get_download_setting.return_value = [mock_orm]

        adapter = DownloadSettingRepositoryAdapter(mock_repo)
        result = adapter.get_all()

        assert len(result) == 1
        assert result[0].name == "Test"

    def test_update(self):
        """测试更新设置"""
        mock_repo = self._create_mock_repo()

        adapter = DownloadSettingRepositoryAdapter(mock_repo)
        adapter.update(
            sid=1,
            name="Test",
            category="TV",
            tags="tag",
            is_paused=True,
            upload_limit=100.0,
            download_limit=200.0,
            ratio_limit=2.0,
            seeding_time_limit=60.0,
            downloader="qb",
        )

        mock_repo.update_download_setting.assert_called_once()


class TestIndexerStatisticsRepositoryAdapter:
    """测试IndexerStatisticsRepositoryAdapter适配器"""

    def _create_mock_repo(self):
        return MagicMock()

    def test_insert(self):
        """测试插入统计"""
        mock_repo = self._create_mock_repo()

        adapter = IndexerStatisticsRepositoryAdapter(mock_repo)
        adapter.insert("SiteA", "builtin", 1.5, "Y")

        mock_repo.insert_indexer_statistics.assert_called_once_with("SiteA", "builtin", 1.5, "Y")

    def test_delete_all(self):
        """测试删除所有统计"""
        mock_repo = self._create_mock_repo()

        adapter = IndexerStatisticsRepositoryAdapter(mock_repo)
        adapter.delete_all()

        mock_repo.delete_all_indexer_statistics.assert_called_once()

    def test_get_by_client(self):
        """测试按客户端获取统计"""
        mock_repo = self._create_mock_repo()
        # 模拟返回: indexer, total, fail, success, avg
        mock_repo.get_indexer_statistics.return_value = [
            ("SiteA", 100, 5, 95, 1.5),
            ("SiteB", 50, 0, 50, 2.0),
        ]

        adapter = IndexerStatisticsRepositoryAdapter(mock_repo)
        result = adapter.get_by_client("builtin")

        assert len(result) == 2
        assert result[0].indexer == "SiteA"
        assert result[0].total == 100
        assert result[0].fail == 5
        assert result[0].success == 95
        assert result[0].avg_seconds == 1.5

    def test_get_by_client_empty(self):
        """测试空统计返回"""
        mock_repo = self._create_mock_repo()
        mock_repo.get_indexer_statistics.return_value = []

        adapter = IndexerStatisticsRepositoryAdapter(mock_repo)
        result = adapter.get_by_client("builtin")

        assert result == []
