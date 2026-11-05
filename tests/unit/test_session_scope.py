"""DB session 作用域静态检查，防止 with 结束后继续复用连接."""

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _uses_after_close(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    findings: list[str] = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        scoped: list[tuple[str, int, int]] = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.With):
                continue
            for item in node.items:
                call = item.context_expr
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                if call.func.attr not in {"session", "readonly"}:
                    continue
                if isinstance(item.optional_vars, ast.Name):
                    scoped.append((item.optional_vars.id, node.lineno, node.end_lineno or node.lineno))
        for name, start, end in scoped:
            for node in ast.walk(fn):
                if not (
                    isinstance(node, ast.Name)
                    and node.id == name
                    and isinstance(node.ctx, ast.Load)
                    and node.lineno > end
                ):
                    continue
                # 后续另一个同名 with 内的使用是合法的
                if any(
                    other_name == name and other_start <= node.lineno <= other_end
                    for other_name, other_start, other_end in scoped
                    if (other_start, other_end) != (start, end)
                ):
                    continue
                findings.append(f"{path}:{node.lineno} {fn.name} 在 with 结束后使用 {name}")
                break
    return findings


def test_sessions_not_used_after_close():
    findings: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        findings.extend(_uses_after_close(path))
    assert not findings, "\n".join(findings)
