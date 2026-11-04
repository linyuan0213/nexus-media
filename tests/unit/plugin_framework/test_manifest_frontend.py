"""插件清单前端内容画像解析测试."""

from app.schemas.plugin import PluginManifest


def test_frontend_content_profiles_round_trip():
    manifest = PluginManifest.from_dict(
        {
            "id": "demo",
            "name": "Demo",
            "frontend": {
                "content_profiles": [
                    {"key": "demo", "label": "AV", "media_type": "movie"},
                    {"label": "缺少 key"},
                ],
                "routes": [],
                "slots": [],
            },
        }
    )

    assert manifest.frontend.content_profiles == [{"key": "demo", "label": "AV", "media_type": "movie"}]
    assert manifest.to_dict()["frontend"]["content_profiles"] == [{"key": "demo", "label": "AV", "media_type": "movie"}]


def test_manifest_accepts_message_template_pack():
    from app.schemas.plugin import PluginManifest

    manifest = PluginManifest.from_dict(
        {
            "id": "demo",
            "version": "1.0.0",
            "backend": {
                "metadata": {
                    "message_labels": {"demo": "AV"},
                    "message_templates": {
                        "demo": {
                            "rss_added": {
                                "title": "{{ media_info.get_title_string() }} AV",
                                "text": "画像：{{ profile_label }}",
                            }
                        }
                    },
                }
            },
        }
    )

    assert manifest.backend.metadata.message_labels == {"demo": "AV"}
    assert "rss_added" in manifest.backend.metadata.message_templates["demo"]
    assert "message_templates" in manifest.to_dict()["backend"]["metadata"]
