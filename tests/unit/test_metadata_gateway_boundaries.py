"""ADR-028 第四阶段边界测试：业务层只依赖元数据网关。"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

from app.domain.mediatypes import MediaType
from app.media.metadata.gateway import MetadataGateway

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BUSINESS_DIRS = (
    SRC / "app" / "services",
    SRC / "app" / "media" / "scraper",
)
METADATA_IMPL = {
    (SRC / "app" / "services" / "metadata_service.py").resolve(),
    (SRC / "app" / "services" / "metadata_admin_service.py").resolve(),
}
DETAIL_MODULES = {
    SRC / "app" / "services" / "media_info_service.py",
    SRC / "app" / "services" / "web" / "utils.py",
    SRC / "app" / "services" / "search_orchestrator.py",
    SRC / "app" / "services" / "search_message_service.py",
    SRC / "app" / "services" / "transfer_history_service.py",
    SRC / "app" / "services" / "sync_service.py",
    SRC / "app" / "services" / "transfer" / "filetransfer_service.py",
    SRC / "app" / "services" / "transfer" / "library_rename_service.py",
    SRC / "app" / "services" / "transfer" / "library_rename_planner.py",
    SRC / "app" / "services" / "subscribe" / "management" / "add_service.py",
    SRC / "app" / "services" / "subscribe" / "management" / "calendar_service.py",
    SRC / "app" / "services" / "subscribe" / "management" / "refresh_service.py",
    SRC / "app" / "media" / "scraper" / "__init__.py",
}


def _iter_python_files():
    for base in BUSINESS_DIRS:
        yield from base.rglob("*.py")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _violates(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def test_business_layer_does_not_import_metadata_service():
    offenders = []
    for path in _iter_python_files():
        if path.resolve() in METADATA_IMPL:
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "app.services.metadata_service":
                offenders.append(str(path.relative_to(ROOT)))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app.services.metadata_service":
                        offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_business_layer_does_not_call_tmdb_helpers():
    offenders: list[str] = []
    for path in _iter_python_files():
        if path.resolve() in METADATA_IMPL:
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and node.module in {
                "app.infrastructure.cache_system.caches",
                "app.media.cache.media_cache",
            }:
                if any(alias.name in {"TMDBCache", "MediaCache"} for alias in node.names):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} import cache")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr.startswith("get_tmdb_"):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} call {node.func.attr}")
    assert offenders == []


def test_business_detail_modules_do_not_instantiate_provider_clients():
    offenders = []
    for path in DETAIL_MODULES:
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"DouBan", "Bangumi"}:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


def test_business_layer_does_not_call_douban_detail_directly():
    offenders = []
    for path in _iter_python_files():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"get_douban_detail", "get_douban_info"}:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


class _CountingService:
    def __init__(self) -> None:
        self.lookups = 0
        self.composes = 0

    def lookup(self, provider, external_id, **kwargs):
        self.lookups += 1
        return {"title": "Demo", "media_type": "movie", "refs": []}

    def compose_for_ref(self, provider, external_id, **kwargs):
        self.composes += 1
        return {"title": "Demo", "media_type": "movie", "refs": [], "fields": {}}

    def find_identity_id(self, *args, **kwargs):
        return None

    def latest_snapshot_record(self, *args, **kwargs):
        return None

    def metrics(self):
        return {}


def test_same_ref_calls_provider_once_per_chain():
    service = _CountingService()
    gateway = MetadataGateway(service)

    first = gateway.lookup("boundary_demo", "BOUNDARY-1", media_type=MediaType.MOVIE)
    second = gateway.lookup("boundary_demo", "BOUNDARY-1", media_type=MediaType.MOVIE)

    assert first == second
    assert service.lookups == 1


def test_concurrent_same_ref_calls_provider_once():
    service = _CountingService()
    gateway = MetadataGateway(service)
    results = []

    def worker():
        results.append(gateway.lookup("boundary_demo", "BOUNDARY-2", media_type=MediaType.MOVIE))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 8
    assert service.lookups == 1


FORBIDDEN_BOUNDARY_DIRS = (
    SRC / "app" / "services" / "subscribe",
    SRC / "app" / "services" / "transfer",
    SRC / "app" / "media" / "scraper",
)
FORBIDDEN_BOUNDARY_FILES = (SRC / "app" / "services" / "search_orchestrator.py",)
FORBIDDEN_MODULES = ("app.media.lookup", "app.media.cache.media_cache")


def _boundary_files():
    for base in FORBIDDEN_BOUNDARY_DIRS:
        yield from base.rglob("*.py")
    yield from FORBIDDEN_BOUNDARY_FILES


def test_business_boundary_does_not_bypass_metadata_gateway():
    """订阅/转移/刮削/搜索不得直连底层元数据实现."""
    offenders: list[str] = []
    for path in _boundary_files():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(_violates(node.module, item) for item in FORBIDDEN_MODULES):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} import {node.module}")
                if any(alias.name == "TMDBCache" for alias in node.names):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} import TMDBCache")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(_violates(alias.name, item) for item in FORBIDDEN_MODULES):
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} import {alias.name}")
                    if alias.name == "TMDBCache":
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} import TMDBCache")
            elif isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    name = node.func.id
                if name.startswith("get_tmdb_") or name in {
                    "cached_tmdb_info",
                    "tmdb_info",
                    "tv_seasons",
                    "season_detail",
                }:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} call {name}")
    assert offenders == [], "检测到绕过元数据网关的直接调用:\n" + "\n".join(offenders)


def test_base_search_has_no_legacy_media_cache() -> None:
    """BaseSearchStrategy 只允许通过网关读取 TMDB 缓存."""
    path = SRC / "app" / "services" / "subscribe" / "strategies" / "base_search.py"
    offenders: list[str] = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "MediaCache" for alias in node.names):
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} import MediaCache")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "BaseSearchStrategy":
                if any(keyword.arg == "media_cache" for keyword in node.keywords):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} BaseSearchStrategy(media_cache=...)")
    assert offenders == []


def test_same_ref_resolve_composes_once():
    service = _CountingService()
    gateway = MetadataGateway(service)

    gateway.resolve("boundary_demo", "BOUNDARY-3", media_type=MediaType.MOVIE)
    gateway.resolve("boundary_demo", "BOUNDARY-3", media_type=MediaType.MOVIE)

    assert service.composes == 1
