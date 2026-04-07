"""
Test cases for Repository Layer and DbHelper Compatibility
验证 Repository 层和 DbHelper 兼容性的测试用例
"""
import pytest
from unittest.mock import MagicMock, patch, Mock


class TestRepositoriesImport:
    """测试 Repository 模块导入"""

    def test_all_repositories_can_be_imported(self):
        """测试所有 Repository 类可以正常导入"""
        from app.db.repositories import (
            BaseRepository,
            SearchRepository,
            TransferRepository,
            SiteRepository,
            RssRepository,
            BrushRepository,
            DownloadRepository,
            UserRepository,
            SyncRepository,
            WordRepository,
            ConfigRepository,
            PluginRepository,
        )
        assert BaseRepository is not None
        assert SearchRepository is not None
        assert TransferRepository is not None
        assert SiteRepository is not None
        assert RssRepository is not None
        assert BrushRepository is not None
        assert DownloadRepository is not None
        assert UserRepository is not None
        assert SyncRepository is not None
        assert WordRepository is not None
        assert ConfigRepository is not None
        assert PluginRepository is not None


class TestDbHelperCompatibility:
    """测试 DbHelper 兼容层"""

    def test_db_helper_can_be_imported(self):
        """测试 DbHelper 可以正常导入"""
        from app.helper import DbHelper
        assert DbHelper is not None

    def test_db_helper_initializes_repositories(self):
        """测试 DbHelper 初始化所有 Repository"""
        from app.helper import DbHelper
        helper = DbHelper()
        
        # 验证所有 repository 实例都被初始化
        assert helper._search_repo is not None
        assert helper._transfer_repo is not None
        assert helper._site_repo is not None
        assert helper._rss_repo is not None
        assert helper._brush_repo is not None
        assert helper._download_repo is not None
        assert helper._user_repo is not None
        assert helper._sync_repo is not None
        assert helper._word_repo is not None
        assert helper._config_repo is not None
        assert helper._plugin_repo is not None


class TestSearchRepository:
    """测试 SearchRepository"""

    def test_search_repository_initialization(self):
        """测试 SearchRepository 初始化"""
        from app.db.repositories import SearchRepository
        repo = SearchRepository()
        assert repo is not None
        assert repo.db is not None


class TestTransferRepository:
    """测试 TransferRepository"""

    def test_transfer_repository_initialization(self):
        """测试 TransferRepository 初始化"""
        from app.db.repositories import TransferRepository
        repo = TransferRepository()
        assert repo is not None
        assert repo.db is not None


class TestSiteRepository:
    """测试 SiteRepository"""

    def test_site_repository_initialization(self):
        """测试 SiteRepository 初始化"""
        from app.db.repositories import SiteRepository
        repo = SiteRepository()
        assert repo is not None
        assert repo.db is not None


class TestRssRepository:
    """测试 RssRepository"""

    def test_rss_repository_initialization(self):
        """测试 RssRepository 初始化"""
        from app.db.repositories import RssRepository
        repo = RssRepository()
        assert repo is not None
        assert repo.db is not None


class TestBrushRepository:
    """测试 BrushRepository"""

    def test_brush_repository_initialization(self):
        """测试 BrushRepository 初始化"""
        from app.db.repositories import BrushRepository
        repo = BrushRepository()
        assert repo is not None
        assert repo.db is not None


class TestDownloadRepository:
    """测试 DownloadRepository"""

    def test_download_repository_initialization(self):
        """测试 DownloadRepository 初始化"""
        from app.db.repositories import DownloadRepository
        repo = DownloadRepository()
        assert repo is not None
        assert repo.db is not None


class TestUserRepository:
    """测试 UserRepository"""

    def test_user_repository_initialization(self):
        """测试 UserRepository 初始化"""
        from app.db.repositories import UserRepository
        repo = UserRepository()
        assert repo is not None
        assert repo.db is not None


class TestSyncRepository:
    """测试 SyncRepository"""

    def test_sync_repository_initialization(self):
        """测试 SyncRepository 初始化"""
        from app.db.repositories import SyncRepository
        repo = SyncRepository()
        assert repo is not None
        assert repo.db is not None


class TestWordRepository:
    """测试 WordRepository"""

    def test_word_repository_initialization(self):
        """测试 WordRepository 初始化"""
        from app.db.repositories import WordRepository
        repo = WordRepository()
        assert repo is not None
        assert repo.db is not None


class TestConfigRepository:
    """测试 ConfigRepository"""

    def test_config_repository_initialization(self):
        """测试 ConfigRepository 初始化"""
        from app.db.repositories import ConfigRepository
        repo = ConfigRepository()
        assert repo is not None
        assert repo.db is not None


class TestPluginRepository:
    """测试 PluginRepository"""

    def test_plugin_repository_initialization(self):
        """测试 PluginRepository 初始化"""
        from app.db.repositories import PluginRepository
        repo = PluginRepository()
        assert repo is not None
        assert repo.db is not None


class TestBaseRepositoryUtils:
    """测试 BaseRepository 工具方法"""

    def test_normalize_path(self):
        """测试路径标准化"""
        from app.db.repositories import BaseRepository
        repo = BaseRepository()
        
        # 测试空路径
        assert repo._normalize_path("") == ""
        assert repo._normalize_path(None) == ""
        
        # 测试正常路径（不实际调用 os.path.normpath，只测试方法存在）
        assert hasattr(repo, '_normalize_path')

    def test_paginate_exists(self):
        """测试分页方法存在"""
        from app.db.repositories import BaseRepository
        repo = BaseRepository()
        assert hasattr(repo, '_paginate')

    def test_build_like_pattern(self):
        """测试 LIKE 模式构建"""
        from app.db.repositories import BaseRepository
        repo = BaseRepository()
        
        # 测试空搜索
        assert repo._build_like_pattern("") == "%%"
        
        # 测试正常搜索
        pattern = repo._build_like_pattern("test")
        assert "test" in pattern
        assert "%" in pattern


class TestDbHelperMethodDelegation:
    """测试 DbHelper 方法委托"""

    @patch('app.db.repositories.SearchRepository.insert_search_results')
    def test_insert_search_results_delegation(self, mock_insert):
        """测试 insert_search_results 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        
        # 调用 DbHelper 方法
        helper.insert_search_results([], title="test", ident_flag=True)
        
        # 验证委托给了 repository
        mock_insert.assert_called_once_with([], "test", True)

    @patch('app.db.repositories.TransferRepository.get_transfer_history')
    def test_get_transfer_history_delegation(self, mock_get):
        """测试 get_transfer_history 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = (0, [])
        
        # 调用 DbHelper 方法
        result = helper.get_transfer_history("search", 1, 10)
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with("search", 1, 10)
        assert result == (0, [])

    @patch('app.db.repositories.SiteRepository.get_config_site')
    def test_get_config_site_delegation(self, mock_get):
        """测试 get_config_site 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_config_site()
        
        # 验证委托给了 repository
        mock_get.assert_called_once()
        assert result == []

    @patch('app.db.repositories.RssRepository.get_rss_movies')
    def test_get_rss_movies_delegation(self, mock_get):
        """测试 get_rss_movies 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_rss_movies(state="D")
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with("D", None)
        assert result == []

    @patch('app.db.repositories.BrushRepository.get_brushtasks')
    def test_get_brushtasks_delegation(self, mock_get):
        """测试 get_brushtasks 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_brushtasks()
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with(None)
        assert result == []

    @patch('app.db.repositories.DownloadRepository.get_download_history')
    def test_get_download_history_delegation(self, mock_get):
        """测试 get_download_history 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_download_history(date=None, hid=None, num=30, page=1)
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with(None, None, 30, 1)
        assert result == []

    @patch('app.db.repositories.UserRepository.get_users')
    def test_get_users_delegation(self, mock_get):
        """测试 get_users 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_users()
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with(None, None)
        assert result == []

    @patch('app.db.repositories.SyncRepository.get_config_sync_paths')
    def test_get_config_sync_paths_delegation(self, mock_get):
        """测试 get_config_sync_paths 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_config_sync_paths()
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with(None)
        assert result == []

    @patch('app.db.repositories.WordRepository.get_custom_words')
    def test_get_custom_words_delegation(self, mock_get):
        """测试 get_custom_words 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_custom_words()
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with(None, None, None)
        assert result == []

    @patch('app.db.repositories.ConfigRepository.get_message_client')
    def test_get_message_client_delegation(self, mock_get):
        """测试 get_message_client 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = []
        
        # 调用 DbHelper 方法
        result = helper.get_message_client()
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with(None)
        assert result == []

    @patch('app.db.repositories.PluginRepository.get_plugin_history')
    def test_get_plugin_history_delegation(self, mock_get):
        """测试 get_plugin_history 委托"""
        from app.helper import DbHelper
        helper = DbHelper()
        mock_get.return_value = None
        
        # 调用 DbHelper 方法
        result = helper.get_plugin_history("plugin_id", "key")
        
        # 验证委托给了 repository
        mock_get.assert_called_once_with("plugin_id", "key")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
