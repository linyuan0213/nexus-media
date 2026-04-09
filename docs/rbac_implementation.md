# RBAC 权限管理系统实现文档

## 概述

本项目已实现了基于角色的访问控制（RBAC）权限管理系统，用于替代原有的简单权限管理机制。新系统支持用户、角色、权限、菜单的动态管理，符合企业级权限管理规范。

## 架构设计

### 1. 数据模型层

#### 核心模型 (`app/db/models/rbac.py`)

- **RBACUser**: 用户表，存储用户基本信息
- **RBACRole**: 角色表，定义系统角色
- **RBACPermission**: 权限表，定义权限点
- **RBACMenu**: 菜单表，管理系统菜单结构
- **RBACUserLoginLog**: 用户登录日志
- **RBACOperationLog**: 操作日志

#### 关联关系

- 用户 <-> 角色：多对多
- 角色 <-> 权限：多对多
- 角色 <-> 菜单：多对多
- 菜单自关联：支持多级菜单

### 2. 数据访问层 (Repository)

`app/db/repositories/rbac_repository.py`

- **RBACUserRepository**: 用户数据操作
- **RBACRoleRepository**: 角色数据操作
- **RBACPermissionRepository**: 权限数据操作
- **RBACMenuRepository**: 菜单数据操作
- **RBACLogRepository**: 日志数据操作

### 3. 业务逻辑层 (Service)

`app/services/rbac_service.py`

- **RBACService**: 核心业务逻辑
  - 用户认证
  - 用户管理（CRUD）
  - 角色管理（CRUD）
  - 权限管理（CRUD）
  - 菜单管理（CRUD）
  - 权限检查

### 4. 初始化模块

`app/services/rbac_init.py`

- 默认权限定义
- 默认菜单定义
- 默认角色定义
- 系统初始化函数

### 5. 用户类封装

`web/backend/user.py`

- **User**: 兼容Flask-Login的用户类
- 封装RBAC功能
- 保持向后兼容的接口

### 6. API接口

`web/apiv1_rbac.py`

- RESTful API接口
- 用户、角色、权限、菜单的CRUD接口
- 权限装饰器

### 7. 前端模板

#### 用户管理 (`web/templates/setting/users.html`)

- 用户列表展示
- 新增/编辑用户
- 角色分配
- 密码重置

#### 角色管理 (`web/templates/setting/roles.html`)

- 角色列表展示
- 角色权限配置
- 角色菜单配置

#### 菜单管理 (`web/templates/setting/menus.html`)

- 菜单树形结构
- 菜单详情
- 新增/编辑/删除菜单

## 权限定义

### 内置权限

| 权限代码 | 名称 | 模块 |
|---------|------|------|
| user:view | 用户查看 | user |
| user:create | 用户创建 | user |
| user:update | 用户编辑 | user |
| user:delete | 用户删除 | user |
| role:view | 角色查看 | role |
| role:create | 角色创建 | role |
| role:update | 角色编辑 | role |
| role:delete | 角色删除 | role |
| permission:view | 权限查看 | permission |
| permission:create | 权限创建 | permission |
| permission:update | 权限编辑 | permission |
| permission:delete | 权限删除 | permission |
| menu:view | 菜单查看 | menu |
| menu:create | 菜单创建 | menu |
| menu:update | 菜单编辑 | menu |
| menu:delete | 菜单删除 | menu |
| setting:view | 系统设置查看 | setting |
| setting:update | 系统设置编辑 | setting |
| library:view | 媒体库查看 | library |
| library:manage | 媒体库管理 | library |
| site:view | 站点查看 | site |
| site:manage | 站点管理 | site |
| download:view | 下载查看 | download |
| download:manage | 下载管理 | download |
| rss:view | 订阅查看 | rss |
| rss:manage | 订阅管理 | rss |
| search:view | 资源搜索 | search |
| search:execute | 执行搜索 | search |
| service:view | 服务查看 | service |
| service:manage | 服务管理 | service |
| plugin:view | 插件查看 | plugin |
| plugin:manage | 插件管理 | plugin |
| log:view | 日志查看 | log |

## 默认角色

### 超级管理员 (superadmin)
- 拥有所有权限
- 级别: 1

### 管理员 (admin)
- 拥有大部分管理权限
- 级别: 10

### 普通用户 (user)
- 拥有基本使用权限
- 级别: 100

### 访客 (guest)
- 仅拥有查看权限
- 级别: 200

## 使用方法

### 1. 检查权限

```python
from flask_login import current_user

# 在视图函数中
if current_user.has_permission('user:create'):
    # 允许创建用户
    pass

# 检查多个权限
if current_user.has_any_permission(['user:create', 'user:update']):
    pass

if current_user.has_all_permissions(['user:view', 'user:update']):
    pass
```

### 2. 权限装饰器

```python
from app.services.rbac_service import require_permission

@app.route('/admin/users')
@login_required
@require_permission('user:view')
def admin_users():
    return render_template('users.html')
```

### 3. 模板中使用

```html
{% if has_permission('user:create') %}
  <a href="/admin/users/create" class="btn btn-primary">新增用户</a>
{% endif %}
```

### 4. 获取用户菜单

```python
# 在视图中
menus = current_user.get_menu_tree()
```

## API接口

### 认证接口

- `POST /api/v1/rbac/auth/login` - 用户登录
- `POST /api/v1/rbac/auth/logout` - 用户登出
- `POST /api/v1/rbac/auth/change-password` - 修改密码

### 用户接口

- `GET /api/v1/rbac/users` - 获取用户列表
- `POST /api/v1/rbac/users` - 创建用户
- `GET /api/v1/rbac/users/{id}` - 获取用户详情
- `PUT /api/v1/rbac/users/{id}` - 更新用户
- `DELETE /api/v1/rbac/users/{id}` - 删除用户
- `POST /api/v1/rbac/users/{id}/reset-password` - 重置密码

### 角色接口

- `GET /api/v1/rbac/roles` - 获取角色列表
- `POST /api/v1/rbac/roles` - 创建角色
- `GET /api/v1/rbac/roles/{id}` - 获取角色详情
- `PUT /api/v1/rbac/roles/{id}` - 更新角色
- `DELETE /api/v1/rbac/roles/{id}` - 删除角色

### 权限接口

- `GET /api/v1/rbac/permissions` - 获取权限列表
- `POST /api/v1/rbac/permissions` - 创建权限
- `PUT /api/v1/rbac/permissions/{id}` - 更新权限
- `DELETE /api/v1/rbac/permissions/{id}` - 删除权限

### 菜单接口

- `GET /api/v1/rbac/menus` - 获取菜单列表
- `GET /api/v1/rbac/menus/tree` - 获取菜单树
- `GET /api/v1/rbac/menus/user` - 获取当前用户菜单
- `POST /api/v1/rbac/menus` - 创建菜单
- `PUT /api/v1/rbac/menus/{id}` - 更新菜单
- `DELETE /api/v1/rbac/menus/{id}` - 删除菜单

## 测试

测试文件: `tests/test_rbac.py`

运行测试:
```bash
uv run pytest tests/test_rbac.py -v
```

## 数据库迁移

RBAC系统会自动创建所需的数据表，无需手动迁移。

在应用启动时，调用初始化函数:
```python
from app.services.rbac_init import init_rbac_system

init_rbac_system()
```

## 注意事项

1. 超级管理员拥有所有权限，不受权限检查限制
2. 删除用户是软删除（将状态设为禁用）
3. 删除菜单会同时删除其子菜单
4. 角色级别数字越小级别越高

## 后续扩展

1. 添加数据权限控制（行级权限）
2. 添加API接口级别的细粒度权限控制
3. 添加权限缓存机制提高性能
4. 添加更多操作日志记录
