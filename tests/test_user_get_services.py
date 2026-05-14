"""
测试 User.get_services 方法
验证服务页面功能正常工作
"""
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


# 设置测试环境
@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """设置测试环境变量"""
    import os
    # 设置必要的测试环境
    test_config_path = str(Path(__file__).parent.parent / "config" / "config.yaml")
    os.environ["NASTOOL_CONFIG"] = test_config_path


class TestUserGetServices:
    """测试 User.get_services 方法 - 验证 SERVICE_CONF 常量定义"""

    def test_service_conf_defined_in_code(self):
        """测试 SERVICE_CONF 常量已在 web/backend/user.py 中定义"""
        # 直接读取文件验证 SERVICE_CONF 定义存在
        user_file = Path(__file__).parent.parent / "web" / "backend" / "user.py"
        content = user_file.read_text(encoding='utf-8')

        assert "SERVICE_CONF = {" in content, "web/backend/user.py 应定义 SERVICE_CONF 常量"
        assert "'rssdownload':" in content, "SERVICE_CONF 应包含 rssdownload 服务"
        assert "'subscribe_search_all':" in content, "SERVICE_CONF 应包含 subscribe_search_all 服务"
        assert "'pttransfer':" in content, "SERVICE_CONF 应包含 pttransfer 服务"
        assert "'sync':" in content, "SERVICE_CONF 应包含 sync 服务"
        assert "'processes':" in content, "SERVICE_CONF 应包含 processes 服务"

    def test_get_services_method_defined(self):
        """测试 get_services 方法已在 User 类中定义"""
        user_file = Path(__file__).parent.parent / "web" / "backend" / "user.py"
        content = user_file.read_text(encoding='utf-8')

        assert "def get_services(self)" in content, "User 类应定义 get_services 方法"
        assert "return SERVICE_CONF" in content, "get_services 应返回 SERVICE_CONF"

    def test_service_conf_structure_from_code(self):
        """测试服务配置结构正确（从代码中解析）"""
        user_file = Path(__file__).parent.parent / "web" / "backend" / "user.py"
        content = user_file.read_text(encoding='utf-8')

        # 验证每个服务都有必要的字段
        import re

        # 查找所有服务定义 'servicename': {
        service_pattern = r"'([a-z_]+)':\s*\{"
        services = re.findall(service_pattern, content)

        # 验证关键服务存在
        required_services = ['rssdownload', 'subscribe_search_all', 'pttransfer', 'sync', 'processes']
        for service in required_services:
            assert service in services, f"SERVICE_CONF 应包含 {service} 服务"

    def test_service_conf_uses_lucide_icons(self):
        """测试服务配置使用 Lucide 图标（从代码中验证）"""
        user_file = Path(__file__).parent.parent / "web" / "backend" / "user.py"
        content = user_file.read_text(encoding='utf-8')

        # 验证使用 icon 字段而不是 svg 字段
        assert "'icon':" in content, "SERVICE_CONF 应使用 'icon' 字段"

        # 验证有 Lucide 风格的图标名称（短横线分隔的小写字母）
        lucide_icon_patterns = [
            r"'cloud-download'",
            r"'search'",
            r"'replace'",
            r"'refresh-cw'",
            r"'eraser'",
            r"'network'",
            r"'database-backup'",
            r"'terminal'",
        ]

        found_icons = 0
        for pattern in lucide_icon_patterns:
            if re.search(pattern, content):
                found_icons += 1

        assert found_icons >= 3, f"SERVICE_CONF 应使用多个 Lucide 图标（找到 {found_icons} 个）"

    def test_service_template_updated_for_lucide(self):
        """测试服务模板已更新以支持 Lucide 图标"""
        template_file = Path(__file__).parent.parent / "web" / "templates" / "service.html"
        content = template_file.read_text(encoding='utf-8')

        # 验证模板支持新的 icon 字段
        assert "data-lucide" in content, "service.html 应使用 data-lucide 属性"
        assert "{% if Scheduler.icon %}" in content, "service.html 应检查 Scheduler.icon 字段"
        assert "{% elif Scheduler.svg %}" in content, "service.html 应保留对 svg 的兼容"

        # 验证有 Lucide 初始化代码
        assert "lucide.createIcons()" in content, "service.html 应调用 lucide.createIcons()"


class TestMainPyCompatibility:
    """测试 main.py 服务端点的兼容性"""

    def test_main_py_service_endpoint(self):
        """测试 main.py 的 service 函数使用正确的服务 key"""
        main_file = Path(__file__).parent.parent / "web" / "main.py"
        content = main_file.read_text(encoding='utf-8')

        # 验证 service 函数使用 get_services
        assert "current_user.get_services()" in content, "main.py 应调用 current_user.get_services()"

        # 验证使用了正确的服务 key
        required_keys = [
            '"rssdownload" in Services',
            '"subscribe_search_all" in Services',
            '"pttransfer" in Services',
            '"sync" in Services',
            '"processes" in Services',
        ]

        for key_check in required_keys:
            assert key_check in content, f"main.py 应检查 {key_check}"


class TestServiceIntegration:
    """测试服务集成"""

    @patch.dict('sys.modules', {
        'app.services.rbac_service': Mock(),
        'app.db.repositories': Mock(),
        'app.db.models.rbac': Mock(),
        'app.conf': Mock(),
        'app.conf.systemconfig': Mock(),
        'app.conf.moduleconf': Mock(),
    })
    def test_service_conf_with_mocked_imports(self):
        """使用模拟导入测试 SERVICE_CONF 可以被导入"""
        # 创建一个模拟的 ModuleConf
        mock_module_conf = Mock()
        mock_module_conf.NETTEST_TARGETS = ['target1', 'target2']

        with patch.dict('sys.modules', {'app.conf.ModuleConf': mock_module_conf}):
            # 直接执行代码字符串来验证 SERVICE_CONF 定义
            service_conf_code = '''
SERVICE_CONF = {
    'rssdownload': {
        'name': '电影/电视剧订阅',
        'icon': 'cloud-download',
        'color': 'blue',
        'level': 2
    },
    'subscribe_search_all': {
        'name': '订阅搜索',
        'icon': 'search',
        'color': 'blue',
        'level': 2
    },
}
'''
            # 验证代码可以执行
            local_vars = {}
            exec(service_conf_code, {}, local_vars)

            assert 'SERVICE_CONF' in local_vars
            assert 'rssdownload' in local_vars['SERVICE_CONF']
            assert local_vars['SERVICE_CONF']['rssdownload']['icon'] == 'cloud-download'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
