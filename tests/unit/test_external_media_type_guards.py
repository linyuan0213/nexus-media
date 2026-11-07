"""静态守卫：lookup/provider 适配层不得用内部 MediaType 判断外部协议类型."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIRS = (
    ROOT / "src" / "app" / "media" / "lookup",
    ROOT / "src" / "app" / "media" / "metadata" / "providers",
)


def _iter_python_files():
    for directory in TARGET_DIRS:
        yield from sorted(directory.rglob("*.py"))


def _is_internal_media_type(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "MediaType"
        and node.attr in {"MOVIE", "TV"}
    )


class _ExternalProtocolGuard(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        # ProviderDescriptor 的历史字段仍声明内部 MediaType，不属于协议判断。
        if isinstance(node.func, ast.Name) and node.func.id == "ProviderDescriptor":
            return
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _is_internal_media_type(node):
            self.violations.append(node.lineno)
        self.generic_visit(node)


def _collect_violations(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    guard = _ExternalProtocolGuard()
    guard.visit(tree)
    return guard.violations


def test_lookup_and_provider_layers_use_provider_media_type_for_external_protocol():
    offenders: list[str] = []
    for path in _iter_python_files():
        violations = _collect_violations(path)
        offenders.extend(f"{path.relative_to(ROOT)}:{line}" for line in violations)
    assert not offenders, "外部协议判断应使用 ProviderMediaType/MediaKind: " + ", ".join(offenders)
