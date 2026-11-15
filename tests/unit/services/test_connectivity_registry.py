"""动态连通性测试目标注册表测试."""

from app.services.system import connectivity_registry as registry


def test_builtin_targets_use_rexxar_douban():
    targets = registry.list_targets()
    douban = next(item for item in targets if item.key == "m.douban.com")
    assert "rexxar" in douban.url
    assert not any(item.key == "frodo.douban.com" for item in targets)


def test_plugin_can_inject_and_remove_targets():
    registry.register_plugin_targets(
        "demo",
        [
            {
                "key": "api.example.com",
                "label": "Example",
                "url": "https://api.example.com/health",
                "category": "metadata",
            }
        ],
    )
    try:
        target = registry.resolve_target("api.example.com")
        assert target is not None
        assert target.label == "Example"
    finally:
        registry.unregister_plugin_targets("demo")
    assert registry.resolve_target("api.example.com") is None


def test_net_test_service_exposes_registry_targets():
    from app.services.system.info import NetTestService

    targets = NetTestService.targets()
    assert any(item["key"] == "m.douban.com" for item in targets)
    assert any(item["key"] == "api.themoviedb.org" for item in targets)
