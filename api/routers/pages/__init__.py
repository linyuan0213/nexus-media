"""
Pages Router Package - FastAPI 页面路由
按业务领域拆分的页面路由模块
"""
from fastapi import APIRouter

from .base import router as base_router
from .discovery import router as discovery_router
from .rss import router as rss_router
from .site import router as site_router
from .download import router as download_router
from .sync import router as sync_router
from .setting import router as setting_router
from .utils_routes import router as utils_router

# 创建主 router
router = APIRouter()

# 包含所有子路由
router.include_router(base_router)
router.include_router(discovery_router)
router.include_router(rss_router)
router.include_router(site_router)
router.include_router(download_router)
router.include_router(sync_router)
router.include_router(setting_router)
router.include_router(utils_router)

# 导出 templates 供其他模块使用
from .utils import templates, register_template_filters

__all__ = ["router", "templates", "register_template_filters"]
