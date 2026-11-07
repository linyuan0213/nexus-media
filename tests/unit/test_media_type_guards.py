"""媒体类型边界守卫：禁止业务执行链继续使用 movie/tv 二分兜底."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "app"
GUARDED = (
    "services/download_service.py",
    "services/lifecycle_service.py",
    "services/scrape_queue_service.py",
    "services/search_subject.py",
    "services/subscribe/strategies/rss_feed.py",
    "services/transfer/filetransfer_service.py",
)


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp):
            for value in node.values:
                if isinstance(value, ast.Constant) and value.value == "movie":
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno} movie fallback")
        if isinstance(node, ast.IfExp):
            for branch in (node.body, node.orelse):
                if isinstance(branch, ast.Attribute) and branch.attr in {"MOVIE", "TV"}:
                    if isinstance(branch.value, ast.Name) and branch.value.id == "MediaType":
                        found.append(f"{path.relative_to(ROOT)}:{node.lineno} MediaType binary fallback")
        if isinstance(node, ast.Compare):
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value == "tv":
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno} raw tv comparison")
    return found


def test_execution_chain_has_no_raw_media_type_fallbacks() -> None:
    violations: list[str] = []
    for relative in GUARDED:
        path = ROOT / relative
        if path.exists():
            violations.extend(_violations(path))
    assert not violations, "\n".join(violations)
