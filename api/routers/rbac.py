# -*- coding: utf-8 -*-
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user
from app.schemas.auth import UserContext
from app.services.rbac_service import rbac_service
from app.utils.response import success, fail

router = APIRouter()


# ---------- Request Models ----------

class CreateMenuRequest(BaseModel):
    menu_name: str
    menu_code: str
    parent_id: Optional[int] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    component: Optional[str] = None
    sort_order: int = 0
    menu_level: int = 1
    permission_code: Optional[str] = None


class CreateRoleRequest(BaseModel):
    role_name: str
    role_code: str
    description: Optional[str] = None
    role_level: int = 100
    permission_ids: List[int] = []
    menu_ids: List[int] = []


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    nickname: Optional[str] = None
    role_ids: List[int] = []


class IdRequest(BaseModel):
    id: int


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str


class UpdateMenuRequest(BaseModel):
    id: int
    menu_name: Optional[str] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    component: Optional[str] = None
    sort_order: Optional[int] = None
    is_hidden: Optional[int] = None
    status: Optional[int] = None
    permission_code: Optional[str] = None


class MenuOrderItem(BaseModel):
    id: int
    sort_order: int
    parent_id: Optional[int] = None


class UpdateMenuSortRequest(BaseModel):
    menu_orders: List[MenuOrderItem] = []


class UpdateRoleRequest(BaseModel):
    id: int
    role_name: Optional[str] = None
    description: Optional[str] = None
    role_level: Optional[int] = None
    status: Optional[int] = None
    permission_ids: Optional[List[int]] = None
    menu_ids: Optional[List[int]] = None


class UpdateUserRequest(BaseModel):
    id: int
    email: Optional[str] = None
    nickname: Optional[str] = None
    status: Optional[int] = None
    avatar: Optional[str] = None
    role_ids: Optional[List[int]] = None


class GetUserMenusRequest(BaseModel):
    ignore: List[str] = []


# ---------- Endpoints ----------

@router.post("/create_menu")
def create_menu(
    req: CreateMenuRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.menu_name or not req.menu_code:
        return fail(success=False, message="菜单名称和代码不能为空")

    ok, result = rbac_service.create_menu(
        menu_name=req.menu_name,
        menu_code=req.menu_code,
        parent_id=req.parent_id,
        path=req.path,
        icon=req.icon,
        component=req.component,
        sort_order=req.sort_order,
        menu_level=req.menu_level,
        permission_code=req.permission_code,
    )
    if ok:
        return success(success=True, message="创建成功", data=result.to_dict())
    return fail(success=False, message=result)


@router.post("/create_role")
def create_role(
    req: CreateRoleRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.role_name or not req.role_code:
        return fail(success=False, message="角色名称和代码不能为空")

    ok, result = rbac_service.create_role(
        role_name=req.role_name,
        role_code=req.role_code,
        description=req.description,
        role_level=req.role_level,
        permission_ids=req.permission_ids,
        menu_ids=req.menu_ids,
    )
    if ok:
        return success(success=True, message="创建成功", data=result.to_dict())
    return fail(success=False, message=result)


@router.post("/create_user")
def create_user(
    req: CreateUserRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.username or not req.password:
        return fail(success=False, message="用户名和密码不能为空")

    ok, result = rbac_service.create_user(
        username=req.username,
        password=req.password,
        email=req.email or "",
        nickname=req.nickname or "",
        role_ids=req.role_ids,
    )
    if ok:
        return success(success=True, message="创建成功", data=result.to_dict())
    return fail(success=False, message=result)


@router.post("/delete_menu")
def delete_menu(
    req: IdRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="菜单ID不能为空")

    ok, message = rbac_service.delete_menu(req.id)
    if ok:
        return success(success=True, message=message)
    return fail(success=False, message=message)


@router.post("/delete_role")
def delete_role(
    req: IdRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="角色ID不能为空")

    ok, message = rbac_service.delete_role(req.id)
    if ok:
        return success(success=True, message=message)
    return fail(success=False, message=message)


@router.post("/delete_user")
def delete_user(
    req: IdRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="用户ID不能为空")

    ok, _ = rbac_service.delete_user(req.id)
    if ok:
        return success(success=True, message="删除成功")
    return fail(success=False, message="删除失败")


@router.post("/get_menu")
def get_menu(
    req: IdRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="菜单ID不能为空")

    menu = rbac_service.menu_repo.get_menu_by_id(req.id)
    if menu:
        return success(success=True, data=menu.to_dict())
    return fail(success=False, message="菜单不存在")


@router.post("/get_role")
def get_role(
    req: IdRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="角色ID不能为空")

    role = rbac_service.get_role_by_id(req.id)
    if role:
        return success(success=True, data=role.to_dict())
    return fail(success=False, message="角色不存在")


@router.post("/get_user")
def get_user(
    req: IdRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="用户ID不能为空")

    user = rbac_service.get_user_by_id(req.id)
    if user:
        return success(success=True, data=user.to_dict())
    return fail(success=False, message="用户不存在")


@router.post("/reset_password")
def reset_password(
    req: ResetPasswordRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.user_id or not req.new_password:
        return fail(success=False, message="用户ID和新密码不能为空")

    ok, message = rbac_service.reset_password(req.user_id, req.new_password)
    if ok:
        return success(success=True, message=message)
    return fail(success=False, message=message)


@router.post("/update_menu")
def update_menu(
    req: UpdateMenuRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="菜单ID不能为空")

    update_fields = {}
    for field in ["menu_name", "path", "icon", "component", "sort_order",
                  "is_hidden", "status", "permission_code"]:
        val = getattr(req, field, None)
        if val is not None:
            update_fields[field] = val

    ok, message = rbac_service.update_menu(req.id, **update_fields)
    if ok:
        return success(success=True, message=message)
    return fail(success=False, message=message)


@router.post("/update_menu_sort")
def update_menu_sort(
    req: UpdateMenuSortRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.menu_orders:
        return fail(success=False, message="菜单排序数据不能为空")

    success_count = 0
    for item in req.menu_orders:
        menu_id = item.id
        sort_order = item.sort_order
        parent_id = item.parent_id

        if menu_id is not None and sort_order is not None:
            update_fields = {"sort_order": sort_order}
            if parent_id is not None:
                update_fields["parent_id"] = parent_id

            ok2, _ = rbac_service.update_menu(menu_id, **update_fields)
            if ok2:
                success_count += 1

    return success(success=True, message=f"成功更新 {success_count} 个菜单排序")


@router.post("/update_role")
def update_role(
    req: UpdateRoleRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="角色ID不能为空")

    update_fields = {}
    for field in ["role_name", "description", "role_level", "status"]:
        val = getattr(req, field, None)
        if val is not None:
            update_fields[field] = val

    ok, message = rbac_service.update_role(req.id, **update_fields)

    if req.permission_ids is not None:
        rbac_service.assign_permissions_to_role(req.id, req.permission_ids)

    if req.menu_ids is not None:
        rbac_service.assign_menus_to_role(req.id, req.menu_ids)

    if ok:
        return success(success=True, message=message)
    return fail(success=False, message=message)


@router.post("/update_user")
def update_user(
    req: UpdateUserRequest,
    current_user: UserContext = Depends(get_current_user),
):
    if not req.id:
        return fail(success=False, message="用户ID不能为空")

    update_fields = {}
    for field in ["email", "nickname", "status", "avatar"]:
        val = getattr(req, field, None)
        if val is not None:
            update_fields[field] = val

    ok, message = rbac_service.update_user(req.id, **update_fields)

    if req.role_ids is not None:
        rbac_service.assign_roles_to_user(req.id, req.role_ids)

    if ok:
        return success(success=True, message=message)
    return fail(success=False, message=message)


def _get_user_id_from_ctx(current_user):
    """兼容层：从 UserContext 或 str 提取用户ID"""
    return getattr(current_user, 'user_id', 0)


def _build_compat_menu(m):
    """RBACMenu → 兼容旧前端格式"""
    return {
        "name": m.MENU_NAME,
        "page": (m.PATH or "").lstrip("/"),
        "icon": m.ICON or "",
        "level": m.MENU_LEVEL,
    }


@router.post("/get_top_menus")
def get_top_menus(
    current_user: UserContext = Depends(get_current_user),
):
    user_id = _get_user_id_from_ctx(current_user)
    if not user_id:
        return fail(success=False, message="用户不存在")
    menus = rbac_service.get_user_menus(user_id)
    result = [_build_compat_menu(m) for m in menus if m.MENU_LEVEL == 1]
    return success(menus=result)


@router.post("/get_user_menus")
def get_user_menus(
    req: GetUserMenusRequest,
    current_user: UserContext = Depends(get_current_user),
):
    user_id = _get_user_id_from_ctx(current_user)
    if not user_id:
        return fail(success=False, message="用户不存在")
    all_menus = rbac_service.get_user_menus(user_id)
    # 构建树形结构（兼容旧接口格式）
    parent_items = {m.ID: _build_compat_menu(m) for m in all_menus if not m.PARENT_ID}
    for child in all_menus:
        if child.PARENT_ID and child.PARENT_ID in parent_items:
            if "list" not in parent_items[child.PARENT_ID]:
                parent_items[child.PARENT_ID]["list"] = []
            parent_items[child.PARENT_ID]["list"].append(_build_compat_menu(child))
    result = list(parent_items.values())
    level = getattr(current_user, 'level', 0)
    return success(menus=result, level=level)


@router.post("/get_users")
def get_users(
    current_user: UserContext = Depends(get_current_user),
):
    users_raw, _ = rbac_service.get_users(page=1, page_size=1000)
    Users = []
    for user in users_raw:
        roles = []
        try:
            roles = [role.to_dict() for role in user.roles]
        except Exception:
            pass
        last_login = None
        if hasattr(user, 'LAST_LOGIN_AT') and user.LAST_LOGIN_AT:
            last_login = user.LAST_LOGIN_AT.strftime('%Y-%m-%d %H:%M')

        Users.append({
            "id": user.ID,
            "name": user.USERNAME,
            "username": user.USERNAME,
            "nickname": user.NICKNAME or user.USERNAME,
            "email": user.EMAIL,
            "status": user.STATUS,
            "roles": roles,
            "last_login_at": last_login,
            "pris": [role.get('role_name') for role in roles] if roles else ["普通用户"]
        })
    return success(result=Users)
