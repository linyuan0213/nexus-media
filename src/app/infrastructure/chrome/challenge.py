"""人机验证（Cloudflare / 雷池等）等待助手 — 供 Agent 浏览器工具与 autosignin 插件共用

nexus-chrome 导航后后台自动跑挑战，本助手负责轮询页面直到挑战页特征消失。
特征口径与 nexus-chrome 服务端（src/challenge/*）保持一致，仅匹配强特征，
避免普通页面正文文案（"正在"/"请稍候"/"challenge"/"由 Cloudflare 提供"页脚等）误判
导致长时间空轮询。
"""

import re
import time

# Cloudflare / 雷池强特征：仅整页拦截（interstitial）签名。
# 注意不能用裸 cf-chl / turnstile：正常页面内嵌 Turnstile 组件会生成
# cf-chl-widget-* 元素 id（如观众签到页），匹配会把正常页面误判为挑战页。
# 注意不能包含 challenge-platform：Cloudflare 会在已放行的正常页面里注入
# challenge-platform 脚本，用它判断会把正常页误判为挑战页并空等超时。
CHALLENGE_INDICATORS = re.compile(
    r"_cf_chl_opt|cf-browser-verification|cf-im-under-attack|challenge-form|"
    r"Checking your browser|Just a moment|Ray ID|slg-bg|slg-box",
    re.IGNORECASE,
)

# 页面内嵌 Turnstile 组件（验证通过后由页面脚本自动提交表单）
EMBEDDED_TURNSTILE = re.compile(
    r'class="cf-turnstile"|challenges\.cloudflare\.com/turnstile',
    re.IGNORECASE,
)

# 雷池（SafeLine）等 WAF：仅页面标题命中才算（与 nexus-chrome leichi.py 口径一致）
CHALLENGE_TITLES = ("雷池", "安全拦截", "访问验证", "Just a moment", "请稍候", "Checking your browser")

CHALLENGE_WAIT_TIMEOUT = 60
CHALLENGE_POLL_INTERVAL = 2

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _is_challenge(html_text: str) -> bool:
    """判定页面是否仍处于挑战页（强特征 + 标题级特征）"""
    if not html_text:
        return False
    if CHALLENGE_INDICATORS.search(html_text):
        return True
    match = _TITLE_RE.search(html_text)
    title = match.group(1).strip() if match else ""
    return any(keyword in title for keyword in CHALLENGE_TITLES)


def is_challenge(html_text: str) -> bool:
    """公共判定：页面是否仍处于挑战/拦截页（供直连降级与等待逻辑复用）"""
    return _is_challenge(html_text)


def has_pending_turnstile(html_text: str) -> bool:
    """页面是否包含待完成的人机验证组件（内嵌 Turnstile）"""
    return bool(html_text) and bool(EMBEDDED_TURNSTILE.search(html_text))


def wait_challenge_clear(
    session,
    initial_html: str = "",
    timeout: int = CHALLENGE_WAIT_TIMEOUT,
    tab_name: str | None = None,
) -> str:
    """等待指定标签页的人机验证通过；tab_name 为空时才读活动页."""
    html_text = initial_html
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_challenge(html_text):
            time.sleep(CHALLENGE_POLL_INTERVAL)
            html_text = session.html(tab_name) if tab_name else session.html()
            continue
        return html_text
    return html_text
