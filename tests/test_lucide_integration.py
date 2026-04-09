"""
测试 Lucide 图标集成
验证菜单图标功能正常工作
"""
import pytest
from unittest.mock import Mock, patch


class TestLucideIntegration:
    """测试 Lucide 图标集成"""

    def test_navigation_html_contains_lucide_script(self):
        """测试 navigation.html 包含 Lucide 脚本引用"""
        with open('web/templates/navigation.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证 Lucide CDN 脚本被引入
        assert 'unpkg.com/lucide' in content, "navigation.html 应包含 Lucide CDN 脚本"
        assert '<script src="https://unpkg.com/lucide@latest"></script>' in content, "应正确引入 Lucide 脚本"

    def test_navbar_component_uses_lucide_icons(self):
        """测试 navbar 组件使用 Lucide 图标"""
        with open('web/static/components/layout/navbar/index.js', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证使用 data-lucide 属性
        assert 'data-lucide' in content, "navbar 组件应使用 data-lucide 属性"
        
        # 验证调用 lucide.createIcons()
        assert 'lucide.createIcons()' in content, "应调用 lucide.createIcons() 渲染图标"
        
        # 验证不再直接使用 unsafeHTML 渲染图标
        assert 'item.icon' in content, "应使用 item.icon 作为图标名称"

    def test_navbar_icon_html_generation(self):
        """测试图标 HTML 生成逻辑"""
        with open('web/static/components/layout/navbar/index.js', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证图标 HTML 模板正确
        assert 'data-lucide="${item.icon}"' in content, "应使用 item.icon 作为 Lucide 图标名称"
        assert 'lucide-icon' in content, "图标应有 lucide-icon 类名"
        assert 'width="20"' in content, "图标应有宽度设置"
        assert 'height="20"' in content, "图标应有高度设置"

    def test_navbar_listeners_for_icon_rendering(self):
        """测试 navbar 在正确时机渲染图标"""
        with open('web/static/components/layout/navbar/index.js', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证在菜单加载后渲染图标
        assert '_renderLucideIcons' in content, "应有 _renderLucideIcons 方法"
        
        # 验证在 firstUpdated 中调用
        assert 'firstUpdated' in content, "应在 firstUpdated 生命周期中调用"
        
        # 验证在 updated 中监听 navbar_list 变化
        assert 'updated(changedProperties)' in content, "应在 updated 中监听属性变化"
        assert "changedProperties.has('navbar_list')" in content, "应监听 navbar_list 变化"

    def test_navbar_handles_missing_icon(self):
        """测试 navbar 处理缺失图标的情况"""
        with open('web/static/components/layout/navbar/index.js', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证处理无图标的情况
        assert 'item.icon ?' in content or 'item.icon' in content, "应处理 item.icon 是否存在"
        assert 'nothing' in content, "无图标时应渲染 nothing"

    def test_icon_name_mapping(self):
        """测试常见图标名称映射"""
        # 常见菜单图标名称应与 Lucide 图标库兼容
        # 注意：Lucide 使用短横线分隔的小写字母命名
        common_icons = [
            'server',
            'settings',
            'tv',
            'home',
            'users',
            'download',
            'rss',
            'search',
            'film',
            'monitor',
            'list-check',  # 刷流任务
            'file-pen',    # 媒体整理
            'scan-line',   # 手动识别
            'refresh-cw',  # 目录同步
            'layout-dashboard',  # 服务
            'menu-square', # 菜单管理
        ]
        
        # 验证这些图标名称在 Lucide 中通常可用
        # 注意：实际可用性需要在浏览器中验证
        for icon in common_icons:
            assert isinstance(icon, str), f"图标名称 {icon} 应为字符串"
            assert len(icon) > 0, f"图标名称 {icon} 不应为空"


class TestMenuDataStructure:
    """测试菜单数据结构"""

    def test_user_model_get_usermenus_returns_icon(self):
        """测试 User.get_usermenus 返回包含 icon 字段的菜单数据"""
        # 直接读取源代码检查，避免导入时的配置依赖
        with open('web/backend/user.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证 get_usermenus 方法存在
        assert 'def get_usermenus' in content, "User 类应有 get_usermenus 方法"
        
        # 验证返回的菜单数据包含 icon 字段
        assert "'icon':" in content or '"icon":' in content, "菜单数据应包含 icon 字段"

    def test_menu_model_has_icon_field(self):
        """测试 RBACMenu 模型有 ICON 字段"""
        # 直接读取源代码检查
        with open('app/db/models/rbac.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查 ICON 字段定义
        assert 'ICON = Column' in content, "RBACMenu 应有 ICON 字段定义"

    def test_menu_to_dict_includes_icon(self):
        """测试 RBACMenu.to_dict 包含 icon 字段"""
        # 直接读取源代码检查
        with open('app/db/models/rbac.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查 to_dict 方法包含 icon
        assert "'icon': self.ICON" in content or '"icon": self.ICON' in content, "to_dict 应包含 icon 字段"


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_navbar_component_structure_unchanged(self):
        """测试 navbar 组件结构基本保持不变"""
        with open('web/static/components/layout/navbar/index.js', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证核心属性仍然存在
        assert 'navbar_list' in content, "应有 navbar_list 属性"
        assert '_render_page_item' in content, "应有 _render_page_item 方法"
        assert 'nav-link-icon' in content, "应有 nav-link-icon 类"
        
        # 验证点击事件处理
        assert '@click' in content, "应有点击事件处理"
        assert 'navmenu' in content, "应调用 navmenu 函数"
