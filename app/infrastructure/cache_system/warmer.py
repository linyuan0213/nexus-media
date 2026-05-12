# -*- coding: utf-8 -*-
"""
缓存预热模块

系统启动时自动加载热点数据到缓存，提高后续访问性能
"""
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import log

from .cache_manager import CacheManager


class CacheWarmer(ABC):
    """缓存预热器基类"""
    
    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self._is_warmed = False
        self._error = None
        self._duration = 0.0
    
    @abstractmethod
    def warm(self) -> bool:
        """执行预热"""
        pass
    
    @property
    def is_warmed(self) -> bool:
        return self._is_warmed
    
    @property
    def error(self) -> Optional[str]:
        return self._error
    
    @property
    def duration(self) -> float:
        return self._duration


class ConfigCacheWarmer(CacheWarmer):
    """配置数据缓存预热器"""
    
    def __init__(self):
        super().__init__("config", priority=0)
    
    def warm(self) -> bool:
        start_time = time.time()
        try:
            log.info("【CacheWarmer】开始预热配置数据...")
            cache_manager = CacheManager()
            
            from config import Config
            cfg = Config()
            
            config = cfg.get_config()
            if config:
                cache = cache_manager.get_or_create("config_load", "memory")
                cache.set("system_config", config, ttl=60)
                log.debug(f"【CacheWarmer】已缓存 app 配置")
            
            try:
                from app.media.category import Category
                category = Category()
                if category._categorys:
                    cache = cache_manager.get_or_create("category_load", "memory")
                    cache.set("categories", category._categorys, ttl=60)
                    log.debug("【CacheWarmer】已缓存分类配置")
            except Exception as e:
                log.warn(f"【CacheWarmer】分类配置预热失败: {e}")
            
            self._is_warmed = True
            self._duration = time.time() - start_time
            log.info(f"【CacheWarmer】配置数据预热完成，耗时 {self._duration:.2f}s")
            return True
        except Exception as e:
            self._error = str(e)
            self._duration = time.time() - start_time
            log.error(f"【CacheWarmer】配置数据预热失败: {e}")
            return False


class SiteCacheWarmer(CacheWarmer):
    """站点数据缓存预热器"""
    
    def __init__(self):
        super().__init__("site", priority=1)
    
    def warm(self) -> bool:
        start_time = time.time()
        try:
            log.info("【CacheWarmer】开始预热站点数据...")
            from app.db.repositories import SiteRepository
            db = SiteRepository()
            
            sites = db.get_config_site()
            if sites:
                cache_manager = CacheManager()
                cache = cache_manager.get_or_create("site_info", "memory")
                cache.set("sites", sites, ttl=300)
                log.debug(f"【CacheWarmer】已缓存 {len(sites)} 个站点")
            
            self._is_warmed = True
            self._duration = time.time() - start_time
            log.info(f"【CacheWarmer】站点数据预热完成，耗时 {self._duration:.2f}s")
            return True
        except Exception as e:
            self._error = str(e)
            self._duration = time.time() - start_time
            log.error(f"【CacheWarmer】站点数据预热失败: {e}")
            return False


class WordsCacheWarmer(CacheWarmer):
    """识别词缓存预热器"""
    
    def __init__(self):
        super().__init__("words", priority=2)
    
    def warm(self) -> bool:
        start_time = time.time()
        try:
            log.info("【CacheWarmer】开始预热识别词...")
            from app.helper.words_helper import WordsHelper
            words_helper = WordsHelper()
            
            if words_helper.words_info:
                log.debug(f"【CacheWarmer】已加载 {len(words_helper.words_info)} 条识别词")
            
            self._is_warmed = True
            self._duration = time.time() - start_time
            log.info(f"【CacheWarmer】识别词预热完成，耗时 {self._duration:.2f}s")
            return True
        except Exception as e:
            self._error = str(e)
            self._duration = time.time() - start_time
            log.error(f"【CacheWarmer】识别词预热失败: {e}")
            return False


class TMDBTrendingWarmer(CacheWarmer):
    """TMDB热门数据预热器"""
    
    def __init__(self):
        super().__init__("tmdb_trending", priority=3)
    
    def warm(self) -> bool:
        start_time = time.time()
        try:
            log.info("【CacheWarmer】开始预热TMDB热门数据...")
            from app.media import MediaService
            
            media = MediaService()
            if not media.tmdb:
                log.warn("【CacheWarmer】TMDB未配置，跳过预热")
                self._is_warmed = True
                return True
            
            # 预热本周趋势
            try:
                trending = media.get_tmdb_trending_all_week(page=1)
                if trending:
                    log.debug(f"【CacheWarmer】已缓存 {len(trending)} 条趋势数据")
            except Exception as e:
                log.warn(f"【CacheWarmer】预热趋势数据失败: {e}")
            
            self._is_warmed = True
            self._duration = time.time() - start_time
            log.info(f"【CacheWarmer】TMDB热门数据预热完成，耗时 {self._duration:.2f}s")
            return True
        except Exception as e:
            self._error = str(e)
            self._duration = time.time() - start_time
            log.error(f"【CacheWarmer】TMDB热门数据预热失败: {e}")
            return False


class CacheWarmerManager:
    """缓存预热管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._warmers: Dict[str, CacheWarmer] = {}
        self._is_running = False
        self._results: Dict[str, bool] = {}
        self._initialized = True
        
        self._register_default_warmers()
    
    def _register_default_warmers(self):
        """注册默认的预热器"""
        self.register(ConfigCacheWarmer())
        self.register(SiteCacheWarmer())
        self.register(WordsCacheWarmer())
        self.register(TMDBTrendingWarmer())
    
    def register(self, warmer: CacheWarmer) -> 'CacheWarmerManager':
        """注册预热器"""
        self._warmers[warmer.name] = warmer
        log.debug(f"【CacheWarmerManager】注册预热器: {warmer.name}")
        return self
    
    def unregister(self, name: str) -> bool:
        """注销预热器"""
        if name in self._warmers:
            del self._warmers[name]
            return True
        return False
    
    def warm_all(self, async_mode: bool = False) -> Dict[str, bool]:
        """
        执行所有预热
        
        Args:
            async_mode: 是否异步执行
            
        Returns:
            Dict[str, bool]: 各预热器的执行结果
        """
        if self._is_running:
            log.warn("【CacheWarmerManager】预热正在进行中")
            return self._results
        
        self._is_running = True
        self._results = {}
        
        # 按优先级排序
        sorted_warmers = sorted(
            self._warmers.values(),
            key=lambda w: w.priority
        )
        
        if async_mode:
            # 异步执行
            threads = []
            for warmer in sorted_warmers:
                t = threading.Thread(
                    target=self._run_warmer,
                    args=(warmer,),
                    name=f"CacheWarmer-{warmer.name}"
                )
                t.start()
                threads.append(t)
            
            # 等待所有线程完成
            for t in threads:
                t.join()
        else:
            # 同步执行
            for warmer in sorted_warmers:
                self._run_warmer(warmer)
        
        self._is_running = False
        
        # 输出统计
        success_count = sum(1 for r in self._results.values() if r)
        total_count = len(self._results)
        log.info(f"【CacheWarmerManager】预热完成: {success_count}/{total_count} 成功")
        
        return self._results
    
    def _run_warmer(self, warmer: CacheWarmer):
        """运行单个预热器"""
        try:
            result = warmer.warm()
            self._results[warmer.name] = result
        except Exception as e:
            log.error(f"【CacheWarmerManager】预热器 {warmer.name} 执行异常: {e}")
            self._results[warmer.name] = False
    
    def warm(self, name: str) -> bool:
        """
        执行指定预热器
        
        Args:
            name: 预热器名称
            
        Returns:
            bool: 是否成功
        """
        if name not in self._warmers:
            log.error(f"【CacheWarmerManager】预热器不存在: {name}")
            return False
        
        warmer = self._warmers[name]
        return warmer.warm()
    
    def get_status(self) -> Dict[str, Any]:
        """获取预热状态"""
        return {
            "is_running": self._is_running,
            "warmers": {
                name: {
                    "is_warmed": w.is_warmed,
                    "error": w.error,
                    "duration": w.duration,
                    "priority": w.priority
                }
                for name, w in self._warmers.items()
            },
            "last_results": self._results
        }
    
    def reset(self):
        """重置所有预热器状态"""
        for warmer in self._warmers.values():
            warmer._is_warmed = False
            warmer._error = None
            warmer._duration = 0.0
        self._results = {}
        log.info("【CacheWarmerManager】已重置所有预热器状态")


# 全局预热管理器实例
def get_warmer_manager() -> CacheWarmerManager:
    """获取全局缓存预热管理器"""
    return CacheWarmerManager()


def warm_cache_on_startup(async_mode: bool = False):
    """
    系统启动时执行缓存预热
    
    Args:
        async_mode: 是否异步执行预热
    """
    log.info("=" * 60)
    log.info("开始缓存预热...")
    log.info("=" * 60)
    
    manager = get_warmer_manager()
    results = manager.warm_all(async_mode=async_mode)
    
    # 输出详细结果
    for name, success in results.items():
        status = "✓" if success else "✗"
        log.info(f"  {status} {name}")
    
    log.info("=" * 60)
    
    return results
