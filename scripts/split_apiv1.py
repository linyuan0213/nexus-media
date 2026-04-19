#!/usr/bin/env python3
"""
将 web/apiv1.py 按 flask-restx namespace 拆分到 web/controllers/api_v1/ 下，
并将基类提取到 web/core/apiv1_base.py。
重写后的 web/apiv1.py 仅保留 Api 初始化和 add_namespace 注册。
"""
import re
from pathlib import Path

SRC = Path("web/apiv1.py")
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)

# 1. 定位基类/辅助函数定义的起止行（ApiResource / ClientResource / Failed）
base_start = None
base_end = None
for i, line in enumerate(lines):
    if line.startswith("class ApiResource"):
        base_start = i
    if base_start is not None and line.startswith("@user.route('/info')"):
        base_end = i
        break

# 2. 提取基类到 web/core/apiv1_base.py
base_content = "".join(lines[base_start:base_end])
apiv1_base = Path("web/core/apiv1_base.py")
apiv1_base.write_text(
    "from flask_restx import Resource\n"
    "from web.security import require_auth, login_required\n\n"
    + base_content,
    encoding="utf-8"
)
print("Created web/core/apiv1_base.py")

# 3. 解析 namespace 赋值位置
ns_re = re.compile(r'^(\w+)\s*=\s*Apiv1\.namespace\(')
ns_positions = []
for i, line in enumerate(lines):
    m = ns_re.match(line)
    if m:
        ns_positions.append((m.group(1), i))

# 4. 构建通用头部（所有拆分文件共享的 imports）
# 收集原 apiv1.py 中的 controllers / backend imports（第 2-12 行、22 行左右）
controller_imports = []
for i, line in enumerate(lines[:base_start]):
    if line.startswith("from web.controllers.") or line.startswith("from web.backend."):
        controller_imports.append(line)

common_header = (
    "from flask import Blueprint, request\n"
    "from flask_restx import Namespace, reqparse, Resource\n"
    "from web.core.apiv1_base import ApiResource, ClientResource, Failed\n"
    "from app.brushtask import BrushTask\n"
    "from app.rsschecker import RssChecker\n"
    "from app.sites import Sites\n"
    "from app.utils import TokenCache\n"
    "from config import Config\n"
    "from web.backend.user import User\n"
    "from web.controllers.site import get_site_user_statistics\n"
    "from web.security import require_auth, login_required, generate_access_token\n"
    + "".join(controller_imports)
    + "\n"
)

# 5. 创建输出目录
OUT_DIR = Path("web/controllers/api_v1")
OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "__init__.py").write_text("", encoding="utf-8")

# 6. 按 namespace 切分并生成文件
for idx, (name, start) in enumerate(ns_positions):
    end = ns_positions[idx + 1][1] if idx + 1 < len(ns_positions) else len(lines)
    block = lines[start:end]
    block_text = "".join(block)
    # 把 "xxx = Apiv1.namespace(...)" 替换为 "xxx = Namespace(...)"
    block_text = re.sub(
        rf"^{name}\s*=\s*Apiv1\.namespace\(",
        f"{name} = Namespace(",
        block_text,
        flags=re.MULTILINE
    )
    # 文件末尾导出 {name}_api，方便 apiv1.py 统一 import
    file_content = common_header + block_text + f"\n{name}_api = {name}\n"
    out_path = OUT_DIR / f"{name}.py"
    out_path.write_text(file_content, encoding="utf-8")
    print(f"Created {out_path}")

# 7. 重写 web/apiv1.py 为入口注册文件
skeleton = '''from flask import Blueprint
from flask_restx import Api

apiv1_bp = Blueprint("apiv1",
                     __name__,
                     static_url_path=\'\',
                     static_folder=\'./frontend/static/\',
                     template_folder=\'./frontend/\', )
Apiv1 = Api(apiv1_bp,
            version="1.0",
            title="NAStool Api",
            description="POST接口调用 /user/login 获取Token，GET接口使用 基础设置->安全->Api Key 调用",
            doc="/",
            security=\'Bearer Auth\',
            authorizations={"Bearer Auth": {"type": "apiKey", "name": "Authorization", "in": "header"}},
            )

'''

for name, _ in ns_positions:
    skeleton += f"from web.controllers.api_v1.{name} import {name}_api as {name}\n"
skeleton += "\n"
for name, _ in ns_positions:
    skeleton += f"Apiv1.add_namespace({name})\n"

SRC.write_text(skeleton, encoding="utf-8")
print("Rewrote web/apiv1.py")
