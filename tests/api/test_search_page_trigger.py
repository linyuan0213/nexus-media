"""
搜索页面自动触发搜索功能测试
验证当访问 /search?s=xxx 时页面能正确传递搜索词并自动触发搜索
"""
import os


class TestSearchPageTrigger:
    """测试搜索页面自动触发搜索功能"""

    def test_search_page_template_has_auto_search_script(self):
        """验证模板中包含自动搜索的 JavaScript 代码"""
        template_path = os.path.join(os.path.dirname(__file__), "..", "..", "web", "templates", "search.html")
        with open(template_path, encoding="utf-8") as f:
            template_content = f.read()

        # 验证包含自动搜索的关键代码
        assert "SearchWord" in template_content
        assert "show_refresh_progress" in template_content
        assert "/api/system/search" in template_content
        assert "{% if SearchWord %}" in template_content
        assert "{% endif %}" in template_content
        # 验证有自动触发的 AJAX 请求
        assert "ajax_post" in template_content
        # 验证有防止重复搜索的全局锁
        assert "__searchRequestSent" in template_content
        # 验证有进度监听和自动跳转逻辑
        assert "navmenu('search')" in template_content

    def test_discovery_py_passes_search_word(self):
        """验证 discovery.py 路由将 SearchWord 传递给模板"""
        discovery_path = os.path.join(os.path.dirname(__file__), "..", "..", "api", "routers", "pages", "discovery.py")
        with open(discovery_path, encoding="utf-8") as f:
            content = f.read()

        # 验证包含 SearchWord 传递给模板
        assert '"SearchWord": s or ""' in content

    def test_discovery_py_has_s_param(self):
        """验证 discovery.py 路由定义了 s 参数"""
        discovery_path = os.path.join(os.path.dirname(__file__), "..", "..", "api", "routers", "pages", "discovery.py")
        with open(discovery_path, encoding="utf-8") as f:
            content = f.read()

        # 验证包含 s 参数定义
        assert 's: Optional[str] = Query(None)' in content

    def test_auto_search_logic_flow(self):
        """验证自动搜索的逻辑流程完整"""
        template_path = os.path.join(os.path.dirname(__file__), "..", "..", "web", "templates", "search.html")
        with open(template_path, encoding="utf-8") as f:
            template_content = f.read()

        # 验证逻辑流程：
        # 1. 检查 SearchWord 是否存在
        assert "{% if SearchWord %}" in template_content
        # 2. 使用立即执行函数
        assert "(function() {" in template_content
        # 3. 全局锁防止重复触发
        assert "__searchRequestSent" in template_content
        # 4. 获取搜索词（使用 tojson 过滤器安全转义）
        assert "{{ SearchWord | tojson }}" in template_content
        # 5. 显示进度条
        assert 'show_refresh_progress("正在搜索 "' in template_content
        # 6. 调用搜索 API
        assert 'ajax_post("/api/system/search"' in template_content
        # 7. 监听进度完成并自动跳转
        assert "setInterval" in template_content
        assert "$('#modal-process')" in template_content
        # 8. 结束 if 判断
        assert "{% endif %}" in template_content
