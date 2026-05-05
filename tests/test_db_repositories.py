"""
Test cases for Repository Layer
验证 Repository 层的测试用例
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
