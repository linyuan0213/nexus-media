"""Info services - 系统信息、版本、网络、搜索、进度与用户管理."""

import datetime
import platform

import psutil

from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.di import container
from app.domain.engine.brush_rule_engine import BrushRuleEngine
from app.message.commands import COMMANDS
from app.schemas.system import (
    NetTestResultDTO,
    ProgressResultDTO,
    SystemInfoDTO,
    UserManageResultDTO,
    VersionInfoDTO,
    WebSearchResultDTO,
)
from app.services.search_web_service import search_medias_for_web
from app.utils import RequestUtils
from app.utils.config_tools import get_proxies
from app.utils.types import MediaType, MovieTypes, ProgressKey
from app.utils.web_utils import WebUtils
from version import APP_VERSION


class SystemInfoService:
    """
    系统信息服务
    获取系统版本、运行时长、Python版本等基本信息
    """

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """格式化运行时长"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}分钟")
        return "".join(parts)

    @staticmethod
    def get_system_info() -> SystemInfoDTO:
        """获取系统基本信息"""
        process = psutil.Process()
        try:
            start_time = datetime.datetime.fromtimestamp(process.create_time())
            uptime_seconds = (datetime.datetime.now() - start_time).total_seconds()
            uptime = SystemInfoService._format_uptime(uptime_seconds)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            start_time = None
            uptime = "-"
            uptime_seconds = 0

        try:
            mem = process.memory_info()
            memory_mb = round(mem.rss / 1024 / 1024, 1)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            memory_mb = 0

        return SystemInfoDTO(
            version=APP_VERSION,
            python_version=platform.python_version(),
            platform=platform.platform(),
            uptime=uptime,
            uptime_seconds=int(uptime_seconds),
            start_time=start_time.isoformat() if start_time else None,
            memory_mb=memory_mb,
        )


class VersionService:
    """
    版本检查业务服务
    """

    @staticmethod
    def get_latest_version() -> VersionInfoDTO:
        """获取最新版本信息"""
        version, url, flag = WebUtils.get_latest_version()
        if flag:
            return VersionInfoDTO(version=version or "", url=url or "", has_update=True)
        return VersionInfoDTO(version="", url="", has_update=False)


class NetTestService:
    """
    网络连通性测试业务服务
    """

    def test(self, target: str) -> NetTestResultDTO:
        """测试指定目标的网络连通性"""
        if target == "image.tmdb.org":
            target = target + "/t/p/w500/wwemzKWzjKYJFfCeiB57q3r4Bcm.png"
        if target == "qyapi.weixin.qq.com":
            target = target + "/cgi-bin/message/send"
        target = "https://" + target
        start_time = datetime.datetime.now()
        if (
            target.find("themoviedb") != -1
            or target.find("telegram") != -1
            or target.find("fanart") != -1
            or target.find("tmdb") != -1
        ):
            res = RequestUtils(proxies=get_proxies(), timeout=5).get_res(target)
        else:
            res = RequestUtils(timeout=5).get_res(target)
        seconds = int((datetime.datetime.now() - start_time).microseconds / 1000)
        if res and res.ok:
            return NetTestResultDTO(success=True, time_ms=seconds)
        return NetTestResultDTO(success=False, time_ms=seconds)


class WebSearchService:
    """
    WEB资源搜索业务服务
    """

    def __init__(self, search_fn=None):
        self._search_fn = search_fn or search_medias_for_web

    def search(
        self, search_word: str, ident_flag: bool = True, filters=None, tmdbid=None, media_type=None
    ) -> WebSearchResultDTO:
        """执行WEB搜索"""
        if not search_word:
            return WebSearchResultDTO(code=0, msg="")
        if media_type:
            if media_type in MovieTypes:
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        ret, ret_msg = self._search_fn(
            content=search_word, ident_flag=ident_flag, filters=filters, tmdbid=tmdbid, media_type=media_type
        )
        return WebSearchResultDTO(code=ret, msg=ret_msg or "")


class ProgressService:
    """
    进度查询业务服务
    """

    def __init__(self, progress_helper=None):
        self._progress = progress_helper or container.progress_helper()

    def get_progress(self, ptype: str) -> ProgressResultDTO:
        detail = self._progress.get_process(ProgressKey(ptype))
        if detail:
            return ProgressResultDTO(value=detail.get("value", 0), text=detail.get("text", ""), exists=True)
        return ProgressResultDTO(exists=False, text="正在处理...")


class UserManageService:
    """
    用户管理业务服务
    """

    def __init__(self, rbac_svc=None):
        self._rbac = rbac_svc

    def _get_rbac(self):
        if self._rbac is None:
            self._rbac = container.rbac_service()
        return self._rbac

    def add_user(self, name: str, password: str, pris=None) -> UserManageResultDTO:
        rbac = self._get_rbac()
        user = rbac.create_user(username=name, password=password)
        return UserManageResultDTO(success=user is not None)

    def delete_user(self, name: str) -> UserManageResultDTO:
        rbac = self._get_rbac()
        user = rbac.get_user_by_username(name)
        if user:
            rbac.delete_user(user.ID)  # type: ignore[arg-type]
            return UserManageResultDTO(success=True)
        return UserManageResultDTO(success=False, message="用户不存在")


def get_commands():
    return [{"id": cid, "name": name} for cid, name in COMMANDS.items()]


def get_rmt_modes():
    return [
        {"value": "copy", "name": "复制"},
        {"value": "move", "name": "移动"},
        {"value": "link", "name": "硬链接"},
        {"value": "softlink", "name": "软链接"},
    ]


def get_system_message(lst_time):
    messages = container.message().messagecenter.get_system_messages(lst_time=lst_time)
    if messages:
        lst_time = messages[0].get("time")
    return {"code": 0, "message": messages, "lst_time": lst_time}


def parse_brush_rule_string(rules):
    return BrushRuleEngine.format_rule_html(rules)
