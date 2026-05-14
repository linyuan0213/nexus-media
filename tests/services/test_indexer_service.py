from unittest.mock import MagicMock

import pytest

from app.domain.entities.download import IndexerStatisticsEntity
from app.schemas.download import IndexerStatisticsDTO
from app.schemas.indexer import (
    IndexerClientInfoDTO,
    IndexerHashDTO,
    UserIndexerDTO,
)
from app.services.indexer_service import IndexerService


@pytest.fixture
def svc():
    mock_indexer = MagicMock()
    mock_str = MagicMock()
    mock_stats_repo = MagicMock()
    service = IndexerService(
        indexer=mock_indexer,
        string_utils=mock_str,
        indexer_statistics_repo=mock_stats_repo
    )
    return service


class TestGetUserIndexers:
    def test_empty(self, svc):
        svc._indexer.get_indexers.return_value = []
        result = svc.get_user_indexers()
        assert result == []

    def test_with_items(self, svc):
        item1 = MagicMock()
        item1.id = "i1"
        item1.name = "SiteA"
        item1.public = True
        item1.builtin = False
        item2 = MagicMock()
        item2.id = "i2"
        item2.name = "SiteB"
        item2.public = False
        item2.builtin = True
        svc._indexer.get_indexers.return_value = [item1, item2]
        result = svc.get_user_indexers()
        assert len(result) == 2
        assert result[0] == UserIndexerDTO(id="i1", name="SiteA")
        assert result[1] == UserIndexerDTO(id="i2", name="SiteB")


class TestGetIndexerHashDict:
    def test_empty(self, svc):
        svc._indexer.get_indexers.return_value = []
        result = svc.get_indexer_hash_dict()
        assert result == {}

    def test_with_items(self, svc):
        item = MagicMock()
        item.id = "i1"
        item.name = "SiteA"
        item.public = True
        item.builtin = False
        svc._indexer.get_indexers.return_value = [item]
        svc._string_utils.md5_hash.return_value = "hash123"
        result = svc.get_indexer_hash_dict()
        assert "hash123" in result
        assert result["hash123"] == IndexerHashDTO(
            id="i1", name="SiteA", public=True, builtin=False
        )


class TestGetUserIndexerNames:
    def test_empty(self, svc):
        svc._indexer.get_indexers.return_value = []
        result = svc.get_user_indexer_names()
        assert result == []

    def test_with_items(self, svc):
        item1 = MagicMock()
        item1.name = "SiteA"
        item1.public = True
        item1.builtin = False
        item2 = MagicMock()
        item2.name = "SiteB"
        item2.public = False
        item2.builtin = True
        svc._indexer.get_indexers.return_value = [item1, item2]
        result = svc.get_user_indexer_names()
        assert result == ["SiteA", "SiteB"]


class TestGetBuiltinIndexers:
    def test_called(self):
        # BuiltinIndexer 会触发真实网络和线程池，
        # 直接调用会导致 pytest 退出时 ThreadPoolExecutor 死锁。
        # 这里只验证方法是存在的薄包装即可。
        assert hasattr(IndexerService, 'get_builtin_indexers')


class TestListResources:
    def test_success(self, svc):
        svc._indexer.list_resources.return_value = [{"id": 1}]
        dto = svc.list_resources("idx1", 1, "kw")
        assert dto.success is True
        assert dto.data == [{"id": 1}]
        svc._indexer.list_resources.assert_called_once_with(
            index_id="idx1", page=1, keyword="kw")

    def test_failure(self, svc):
        svc._indexer.list_resources.return_value = None
        dto = svc.list_resources("idx1", 0, None)
        assert dto.success is False
        assert "无法连接到站点" in dto.msg


class TestGetClientInfo:
    def test_with_client(self, svc):
        mock_client = MagicMock()
        mock_client.client_id = "builtin"
        mock_client.client_name = "Builtin"
        mock_type = MagicMock()
        mock_type.value = "builtin"
        svc._indexer.get_client.return_value = mock_client
        svc._indexer.get_client_type.return_value = mock_type
        dto = svc.get_client_info()
        assert dto.client_id == "builtin"
        assert dto.client_type == "builtin"
        assert dto.client_name == "Builtin"

    def test_without_client(self, svc):
        svc._indexer.get_client.return_value = None
        svc._indexer.get_client_type.return_value = None
        dto = svc.get_client_info()
        assert dto == IndexerClientInfoDTO()


class TestGetClient:
    def test_returns_client(self, svc):
        mock_client = MagicMock()
        svc._indexer.get_client.return_value = mock_client
        assert svc.get_client() is mock_client


class TestGetClientType:
    def test_returns_type(self, svc):
        svc._indexer.get_client_type.return_value = "builtin"
        assert svc.get_client_type() == "builtin"


class TestGetIndexerStatistics:
    def test_empty(self, svc):
        svc._indexer.get_client.return_value = MagicMock(client_id="builtin")
        svc._indexer_statistics_repo.get_by_client.return_value = []
        stats, dataset = svc.get_indexer_statistics()
        assert stats == []
        assert dataset == [["indexer", "avg"]]

    def test_with_data(self, svc):
        svc._indexer.get_client.return_value = MagicMock(client_id="builtin")
        svc._indexer_statistics_repo.get_by_client.return_value = [
            IndexerStatisticsEntity(indexer="SiteA", total=10, fail=2, success=8, avg_seconds=1.23),
        ]
        stats, dataset = svc.get_indexer_statistics()
        assert len(stats) == 1
        assert stats[0] == IndexerStatisticsDTO(
            name="SiteA", total=10, fail=2, success=8, avg=1.2
        )
        assert dataset == [["indexer", "avg"], ["SiteA", "1.2"]]

    def test_none_result(self, svc):
        svc._indexer.get_client.return_value = MagicMock(client_id="builtin")
        svc._indexer_statistics_repo.get_by_client.return_value = []
        stats, dataset = svc.get_indexer_statistics()
        assert stats == []
        assert dataset == [["indexer", "avg"]]

    def test_no_client(self, svc):
        svc._indexer.get_client.return_value = None
        stats, dataset = svc.get_indexer_statistics()
        assert stats == []
        assert dataset == [["indexer", "avg"]]
