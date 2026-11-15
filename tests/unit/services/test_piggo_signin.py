"""Piggo 签到结果判定测试."""

from types import SimpleNamespace
from typing import cast

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.piggo import Piggo
from app.plugin_framework.context import PluginContext


def test_is_signed_pill_only_accepts_button_state():
    handler = Piggo(cast(PluginContext, SimpleNamespace(site_engine=None)))
    assert handler._is_signed_pill("已签到")
    assert handler._is_signed_pill(" 已 签 到 ")
    assert not handler._is_signed_pill("签到")
    assert not handler._is_signed_pill("累计签到0天")
    assert not handler._is_signed_pill("已签到记录")
