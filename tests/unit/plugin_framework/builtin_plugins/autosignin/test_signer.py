import re


class TestSignerBugFixes:
    def test_retry_regex_extracts_site_name(self):
        text = "[hdarea]签到失败，请检查站点连通性"
        site_names = re.findall(r"\[(.*?)\]", text)
        assert site_names == ["hdarea"]

    def test_retry_regex_does_not_match_random_chars(self):
        old_pattern = r"[(.*?)]"
        text = "[hdarea]签到失败"
        result = re.findall(old_pattern, text)
        assert result != ["hdarea"]

    def test_signin_result_msg_format(self):
        from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import SigninResult

        assert SigninResult.success("52pt").msg == "[52pt]签到成功"
        assert SigninResult.already("52pt").msg == "[52pt]今日已签到"
        assert SigninResult.fail("52pt", "cookie失效").msg == "[52pt]签到失败，cookie失效"
