"""M-Team 签到 handler 纯逻辑单测（URL/签名/响应判定，不依赖网络与 Redis）."""

import json
from typing import cast
from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.mteam import MTeam
from app.plugin_framework.context import PluginContext
from app.sites.credential_provider import SpaCredentials


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def _handler():
    return MTeam(plugin_ctx=cast(PluginContext, MagicMock()))


def test_build_sign_vector_matches_real_request():
    # 用户抓包真实请求：timestamp/sgin 由内置密钥生成
    sig = MTeam._build_sign("POST", "/api/member/updateLastBrowse", 1788666941029, "HLkPcWmycL57mfJt")
    assert sig == "Fl4kdsfOTdR+zQmlZZQQS86GiYA="


def test_response_code_string_zero_is_success():
    res = _FakeResponse(json.dumps({"code": "0", "message": "SUCCESS"}))
    result = _handler()._check_response(res, "M-Team")
    assert result.ok is True


def test_response_code_number_zero_is_success():
    res = _FakeResponse(json.dumps({"code": 0, "message": "success"}))
    result = _handler()._check_response(res, "M-Team")
    assert result.ok is True


def test_response_code_one_fail_is_now_success():
    # 2026-10 起 updateLastBrowse 成功返回 {"code":"1","message":"FAIL","data":null}
    res = _FakeResponse(json.dumps({"code": "1", "message": "FAIL", "data": None}))
    result = _handler()._check_response(res, "M-Team")
    assert result.ok is True


def test_response_code_one_fail_message_is_success_number_code():
    res = _FakeResponse(json.dumps({"code": 1, "message": "FAIL", "data": None}))
    result = _handler()._check_response(res, "M-Team")
    assert result.ok is True


def test_response_other_code_one_message_still_failure():
    # 仅新的成功标志（message=FAIL）视为成功，其它 code=1 报文不误判
    res = _FakeResponse(json.dumps({"code": "1", "message": "SOME ERROR"}))
    result = _handler()._check_response(res, "M-Team")
    assert result.ok is False


def test_api_base_prefers_cc_domain():
    class Api:
        base_url = "https://api.m-team.cc"

    class SiteDef:
        domain = "kp.m-team.cc"
        api = Api()

    assert _handler()._resolve_api_base(SiteDef()) == "https://api.m-team.cc"
    assert _handler()._resolve_api_base(None) == "https://api.m-team.cc"


def test_response_401_auth_expired_returns_clear_message():
    """JWT 过期(401)：返回明确提示而非接口原文，且不触发自动重登路径"""
    handler = _handler()
    res = _FakeResponse('{"code":401,"message":"Full authentication is required to access this resource","data":null}')
    result = handler._check_response(res, "M-Team")
    assert result.ok is False
    assert "登录态已过期" in result.msg


def test_response_revoked_credential_returns_clear_message():
    handler = _handler()
    res = _FakeResponse('{"code":"1","message":"系统检测到疑似登录凭证泄露，已吊销该会话","data":null}')
    result = handler._check_response(res, "M-Team")
    assert result.ok is False
    assert "吊销" in result.msg


def _signin_ctx():
    from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import SiteSigninContext

    return SiteSigninContext(
        site="M-Team",
        site_id="mteam",
        site_url="https://kp.m-team.cc",
        cookie=None,
        api_key=None,
        bearer_token=None,
        ua="BROWSER-UA",
        proxy_url=None,
        headers={},
    )


def _run_signin(local_storage, response_text='{"code":"1","message":"FAIL","data":null}'):
    from types import SimpleNamespace

    from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import SigninResult

    handler = MTeam(plugin_ctx=MagicMock())
    handler._plugin_ctx.site_engine.get_by_id.return_value = SimpleNamespace(
        domain="kp.m-team.cc", api=SimpleNamespace(base_url="https://api.m-team.cc")
    )
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.post.return_value = _FakeResponse(response_text)
    with (
        patch("app.plugin_framework.builtin_plugins.autosignin.backend.handlers.mteam.resolve_spa_credentials") as cc,
        patch(
            "app.plugin_framework.builtin_plugins.autosignin.backend.handlers.mteam.HttpClient",
            return_value=client,
        ),
        patch("app.plugin_framework.builtin_plugins.autosignin.backend.handlers.mteam.time.sleep"),
        patch.object(handler, "_fetch_secret", return_value=None),
    ):
        cc.return_value = SpaCredentials(
            local_storage=local_storage,
            bearer_token=str(local_storage.get("auth") or ""),
            visitor_id=str(local_storage.get("visitorId") or ""),
        )
        result = handler.signin(_signin_ctx())
    assert isinstance(result, SigninResult)
    return result, client


def test_signin_headers_aligned_with_browser():
    result, client = _run_signin({"auth": "JWT", "did": "DID", "visitorId": "VID", "webversion": "2000"})
    assert result.ok is True
    headers = client.post.call_args.kwargs["headers"]
    assert headers["referer"] == "https://kp.m-team.cc/index"
    assert headers["webversion"] == "2000"
    assert headers["did"] == "DID"
    assert headers["visitorid"] == "VID"


def test_signin_webversion_defaults_when_missing():
    _result, client = _run_signin({"auth": "JWT", "did": "DID", "visitorId": "VID"})
    assert client.post.call_args.kwargs["headers"]["webversion"] == MTeam._DEFAULT_WEBVERSION


def test_signin_missing_fingerprint_fails_without_request():
    result, client = _run_signin({"auth": "JWT", "visitorId": "VID"})
    assert result.ok is False
    assert "did" in result.msg
    client.post.assert_not_called()
