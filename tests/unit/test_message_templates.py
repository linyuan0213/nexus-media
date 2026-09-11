"""默认消息模板渲染测试（防止 Jinja 语法回归）."""

import pytest

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.message.core.template_engine import TemplateEngine


class _Item(MediaInfo):
    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def engine():
    return TemplateEngine()


def _item():
    return _Item(
        title="少女怪兽焦糖味",
        year="2026",
        type=MediaType.TV,
        begin_season=1,
        begin_episode=3,
        end_episode=3,
        site="M-Team",
        org_string="Otome Kaijuu Caramelise S01E03 1080p",
        seeders=12,
        size=1234567890,
        hit_and_run=False,
        enclosure="http://site/dlv2?sign=secret-token",
    )


def test_download_fail_template_renders_and_hides_link(engine):
    title, text = engine.apply_client_template(
        {}, "download_fail", {"item": _item(), "error_msg": "站点返回：相同種子當天最多下載10次"}
    )
    assert title and "S01" in title and "E03" in title
    assert "添加下载失败" in title
    assert "原因：站点返回：相同種子當天最多下載10次" in text
    # 默认全局模板不得暴露签名下载链接
    assert "sign=secret-token" not in text
    assert "enclosure" not in text


def test_download_start_template_renders(engine):
    title, text = engine.apply_client_template({}, "download_start", {"item": _item()})
    assert title and "开始下载" in title
    assert "站点" in text and "做种" in text


def test_transfer_finished_template_renders(engine):
    item = _item()
    title, text = engine.apply_client_template(
        {},
        "transfer_finished",
        {
            "media_info": item,
            "total_episodes": 12,
            "exist_filenum": 0,
            "category_flag": False,
            "in_from": "RSS",
        },
    )
    assert title and "已入库" in title and "共12集" in title
    assert "类型" in text


def test_rss_added_and_finished_templates_render(engine):
    item = _item()
    item.user_name = "linyuan"
    added_title, added_text = engine.apply_client_template({}, "rss_added", {"media_info": item, "in_from": "WEB"})
    assert added_title and "已添加订阅" in added_title
    assert "用户：linyuan" in added_text

    finished_title, finished_text = engine.apply_client_template({}, "rss_finished", {"media_info": item})
    assert finished_title and "已完成订阅" in finished_title
    assert "类型" in finished_text


def test_transfer_fail_template_renders(engine):
    title, text = engine.apply_client_template(
        {}, "transfer_fail", {"count": 2, "path": "/downloads/x", "text": "磁盘空间不足"}
    )
    assert title and "入库失败" in title
    assert "原因：磁盘空间不足" in text
