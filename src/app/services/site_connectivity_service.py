"""站点连通性测试."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.schemas.site import SiteTestResultDTO


class SiteConnectivityService:
    """连通性探测；单点失败不阻断批量结果."""

    @staticmethod
    def test(site_resolver: Any, site_id: int | str) -> SiteTestResultDTO:
        flag, msg, times = site_resolver.test_connection(site_id)
        return SiteTestResultDTO(flag=flag, msg=msg, times=times, code=0 if flag else -1)

    @staticmethod
    def test_batch(site_resolver: Any, site_ids: list[str] | None) -> list[dict[str, Any]]:
        ids = [str(s) for s in (site_ids or []) if str(s).strip()]
        if not ids:
            return []

        def _run(sid: str) -> dict[str, Any]:
            try:
                flag, msg, times = site_resolver.test_connection(sid)
            except (ServiceError, DomainError, RepositoryError) as e:
                flag, msg, times = False, str(e), 0.0
            except Exception as e:  # noqa: BLE001
                flag, msg, times = False, f"测试异常: {e}", 0.0
            return {"id": sid, "flag": flag, "msg": msg, "times": times}

        results: list[dict[str, Any]] = []
        max_workers = min(5, len(ids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run, sid): sid for sid in ids}
            for future in as_completed(futures):
                results.append(future.result())
        return results
