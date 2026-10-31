"""插件分类贡献注册与核心合并测试."""

import pytest

from app.media.category_contributions import (
    clear_category_contributions,
    get_category_contributions,
    register_category_contribution,
    unregister_plugin_contributions,
)
from app.media.category_matcher import get_category
from app.plugin_sdk.category import CategoryContribution


@pytest.fixture(autouse=True)
def _clean_contributions():
    clear_category_contributions()
    yield
    clear_category_contributions()


def test_extension_contribution_is_visible_but_not_core():
    contribution = CategoryContribution(
        namespace="demo_plugin",
        media_types=("tv",),
        categories={"demo_category": {"genres": "animation"}},
        scope="extension",
    )
    register_category_contribution(contribution, "demo_plugin")
    assert get_category_contributions("tv", scope="extension") == [contribution]
    assert get_category({"fallback": {}}, {"genres": [{"id": 16}]}, "tv") == "fallback"


def test_core_contribution_participates_in_category_match():
    contribution = CategoryContribution(
        namespace="demo_plugin",
        media_types=("tv",),
        categories={"plugin_animation": [{"field": "genre", "operator": "contains", "value": "animation"}]},
        scope="core",
    )
    register_category_contribution(contribution, "demo_plugin")
    assert get_category({"fallback": {}}, {"genres": [{"id": 16}]}, "tv") == "plugin_animation"


def test_plugin_contributions_are_removed_on_unload():
    contribution = CategoryContribution(
        namespace="demo_plugin",
        media_types=("movie",),
        categories={"demo": {}},
    )
    register_category_contribution(contribution, "demo_plugin")
    unregister_plugin_contributions("demo_plugin")
    assert get_category_contributions() == []
