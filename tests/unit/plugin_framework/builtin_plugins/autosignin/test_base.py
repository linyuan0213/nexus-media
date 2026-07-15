from unittest.mock import MagicMock

import pytest

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)


class TestSigninResult:
    def test_success(self):
        r = SigninResult.success("test_site")
        assert r.ok is True
        assert r.msg == "[test_site]签到成功"

    def test_already(self):
        r = SigninResult.already("test_site")
        assert r.ok is True
        assert r.msg == "[test_site]今日已签到"

    def test_fail(self):
        r = SigninResult.fail("test_site", "cookie失效")
        assert r.ok is False
        assert r.msg == "[test_site]签到失败，cookie失效"

    def test_custom(self):
        r = SigninResult.custom(True, "custom message")
        assert r.ok is True
        assert r.msg == "custom message"

    def test_signin_result_attrs(self):
        assert SigninResult.SUCCESS == "签到成功"
        assert SigninResult.ALREADY == "已签到"
        assert SigninResult.COOKIE_EXPIRED == "cookie失效"
        assert SigninResult.SITE_UNREACHABLE == "请检查站点连通性"
        assert SigninResult.REQUEST_FAILED == "签到接口请求失败"


class TestSiteSigninContext:
    def test_from_site_info_without_engine(self):
        ctx = SiteSigninContext.from_site_info(
            {"id": 1, "name": "test", "signurl": "https://test.com/sign", "cookie": "c"}
        )
        assert ctx.site_id == "1"
        assert ctx.site == "test"
        assert ctx.site_url == "https://test.com/sign"
        assert ctx.cookie == "c"

    def test_from_site_info_resolves_canonical_id(self):
        site_def = MagicMock()
        site_def.id = "btschool"
        site_def.name = "学校"
        site_def.domain = "https://pt.btschool.club"
        engine = MagicMock()
        engine.get_by_url = MagicMock(return_value=site_def)

        ctx = SiteSigninContext.from_site_info(
            {"id": 71, "name": "学校", "signurl": "https://pt.btschool.club/index.php?action=addbonus"},
            site_engine=engine,
        )
        assert ctx.site_id == "btschool"
        assert ctx.site == "学校"
        assert ctx.site_url == "https://pt.btschool.club/index.php?action=addbonus"
        engine.get_by_url.assert_called_once()

    def test_from_site_info_fallback_by_name(self):
        site_def = MagicMock()
        site_def.id = "audiences"
        site_def.name = "Audiences"
        site_def.domain = "https://audiences.me"
        engine = MagicMock()
        engine.get_by_url = MagicMock(return_value=None)
        engine.get_by_name = MagicMock(return_value=site_def)

        ctx = SiteSigninContext.from_site_info(
            {"id": 3, "name": "Audiences", "strict_url": "", "signurl": "", "rssurl": ""},
            site_engine=engine,
        )
        assert ctx.site_id == "audiences"
        assert ctx.site == "Audiences"
        assert ctx.site_url == "https://audiences.me"


class TestSiteSigninHandler:
    def test_check_cookie_expired(self):
        class DummyHandler(SiteSigninHandler):
            def signin(self, ctx):
                return SigninResult.custom(True, "")

        result = DummyHandler(MagicMock())._check_cookie("login.php in text", "test_site")
        assert result is not None
        assert result.ok is False
        assert "cookie失效" in result.msg

    def test_check_cookie_ok(self):
        class DummyHandler(SiteSigninHandler):
            def signin(self, ctx):
                return SigninResult.custom(True, "")

        result = DummyHandler(MagicMock())._check_cookie("<html>normal page</html>", "test_site")
        assert result is None

    @pytest.mark.parametrize(
        "html_res,regexs,expected",
        [
            ("已签到", ["已签到"], True),
            ("not matched", ["已签到"], False),
            ("签到成功", ["签到成功", "已签到"], True),
            ("今日已签到", ["签到成功"], False),
        ],
    )
    def test_sign_in_result(self, html_res, regexs, expected):
        result = SiteSigninHandler.sign_in_result(html_res, regexs)
        assert result == expected
