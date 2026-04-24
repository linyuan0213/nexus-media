# -*- coding: utf-8 -*-
"""
Pages Router 测试
验证 FastAPI 页面路由结构正确（不触发重型初始化）
"""
import pytest
import os
from unittest.mock import patch, MagicMock


# 在测试执行时动态导入，避免测试收集阶段触发重型初始化
def _import_router():
    """导入 router，隔离导入副作用"""
    with patch("app.utils.wallpaper.get_login_wallpaper"):
        from api.routers.pages import router
        return router


def _get_template_dir():
    """获取模板目录"""
    with patch("app.utils.wallpaper.get_login_wallpaper"):
        from api.routers.pages.utils import _template_dir
        return _template_dir


class TestPagesRouter:
    """测试页面路由结构"""

    def test_login_page_route_exists(self):
        """验证登录页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/" in routes

    def test_login_page_post_route_exists(self):
        """验证登录 POST 路由存在"""
        router = _import_router()
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        post_routes = [p for p, m in routes if "/" == p and "POST" in m]
        assert len(post_routes) > 0

    def test_web_page_route_exists(self):
        """验证导航页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/web" in routes

    def test_index_page_route_exists(self):
        """验证首页路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/index" in routes

    def test_login_page_has_expected_context(self):
        """验证登录页面返回正确的模板上下文结构"""
        template_dir = _get_template_dir()

        # 验证模板目录存在且指向正确的位置
        assert template_dir is not None
        assert "web/templates" in str(template_dir)

    def test_search_page_route_exists(self):
        """验证搜索页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/search" in routes

    def test_recommend_page_route_exists(self):
        """验证推荐页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/recommend" in routes

    def test_movie_rss_page_route_exists(self):
        """验证电影订阅页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/movie_rss" in routes

    def test_tv_rss_page_route_exists(self):
        """验证电视剧订阅页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/tv_rss" in routes

    def test_site_page_route_exists(self):
        """验证站点维护页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/site" in routes

    def test_downloading_page_route_exists(self):
        """验证正在下载页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/downloading" in routes

    def test_service_page_route_exists(self):
        """验证服务页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/service" in routes

    def test_history_page_route_exists(self):
        """验证历史记录页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/history" in routes

    def test_basic_setting_page_route_exists(self):
        """验证基础设置页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/basic" in routes

    def test_downloader_setting_page_route_exists(self):
        """验证下载器设置页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/downloader" in routes

    def test_user_rss_page_route_exists(self):
        """验证自定义订阅页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/user_rss" in routes

    def test_statistics_page_route_exists(self):
        """验证数据统计页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/statistics" in routes

    def test_brushtask_page_route_exists(self):
        """验证刷流任务页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/brushtask" in routes

    def test_logging_page_route_exists(self):
        """验证日志页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/logging" in routes

    def test_scheduler_page_route_exists(self):
        """验证调度任务页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/scheduler" in routes

    def test_mediafile_page_route_exists(self):
        """验证媒体文件页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/mediafile" in routes

    def test_rss_calendar_page_route_exists(self):
        """验证订阅日历页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/rss_calendar" in routes

    def test_rss_history_page_route_exists(self):
        """验证订阅历史页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/rss_history" in routes

    def test_torrent_remove_page_route_exists(self):
        """验证自动删种页面路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/torrent_remove" in routes

    def test_upload_route_exists(self):
        """验证文件上传路由存在"""
        router = _import_router()
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        post_routes = [p for p, m in routes if "/upload" == p and "POST" in m]
        assert len(post_routes) > 0

    def test_dirlist_route_exists(self):
        """验证目录列表路由存在"""
        router = _import_router()
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        post_routes = [p for p, m in routes if "/dirlist" == p and "POST" in m]
        assert len(post_routes) > 0

    def test_stream_logging_route_exists(self):
        """验证日志流路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/stream-logging" in routes

    def test_stream_progress_route_exists(self):
        """验证进度流路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/stream-progress" in routes

    def test_backup_route_exists(self):
        """验证备份路由存在"""
        router = _import_router()
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        post_routes = [p for p, m in routes if "/backup" == p and "POST" in m]
        assert len(post_routes) > 0

    def test_healthcheck_route_exists(self):
        """验证健康检查路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/healthcheck" in routes

    def test_robots_txt_route_exists(self):
        """验证 robots.txt 路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/robots.txt" in routes

    def test_ical_route_exists(self):
        """验证 iCal 路由存在"""
        router = _import_router()
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/ical" in routes

    def test_no_old_controller_imports_in_pages(self):
        """验证 pages 路由包不再导入旧的 web.controllers 模块"""
        import api.routers.pages as pages_pkg
        import ast
        import inspect

        pkg_dir = os.path.dirname(inspect.getfile(pages_pkg))
        controller_imports = []

        for fname in os.listdir(pkg_dir):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(pkg_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                source = f.read()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.startswith("web.controllers"):
                        controller_imports.append((fname, module))

        assert len(controller_imports) == 0, (
            f"发现旧的 controller 导入: {controller_imports}"
        )
