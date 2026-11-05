"""通知来源展示：content_id 是内部锚点，不能直接展示给用户."""

from types import SimpleNamespace

from app.message.core.message_builder import _source_provider


def test_content_id_without_real_ref_shows_code_label():
    item = SimpleNamespace(provider="content_id", anchor_provider="content_id", metadata_ref="", provider_data={})

    assert _source_provider(item) == "番号识别"


def test_content_id_uses_metadata_ref_provider():
    item = SimpleNamespace(
        provider="content_id", anchor_provider="content_id", metadata_ref="javdb:P0dyv", provider_data={}
    )

    assert _source_provider(item).lower() == "javdb"
