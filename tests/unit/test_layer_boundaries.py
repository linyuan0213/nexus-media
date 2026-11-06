"""分层依赖方向守卫.

下层模块只能依赖同层及更底层；发现反向 import 时尽早失败，避免形成循环依赖。
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "src" / "app"

# 层 -> 禁止依赖的上层模块
FORBIDDEN_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "domain": ("app.api", "app.db", "app.infrastructure", "app.services"),
    "db": ("app.api", "app.infrastructure", "app.media", "app.services"),
    "core": ("app.db",),
    "utils": ("app.infrastructure",),
    "sites": ("app.message",),
    "message": ("app.agent",),
    "indexer": ("app.services",),
}


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _violates(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def test_layers_do_not_import_upward() -> None:
    violations: list[str] = []
    for layer, forbidden_modules in FORBIDDEN_DEPENDENCIES.items():
        layer_root = APP_ROOT / layer
        if not layer_root.exists():
            continue
        for path in layer_root.rglob("*.py"):
            for line, module in _imports(path):
                for forbidden in forbidden_modules:
                    if _violates(module, forbidden):
                        violations.append(f"{path.relative_to(APP_ROOT.parent.parent)}:{line} {layer} -> {module}")
    assert not violations, "检测到反向依赖:\n" + "\n".join(violations)
