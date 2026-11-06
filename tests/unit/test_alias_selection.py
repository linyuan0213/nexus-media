"""别名筛选测试."""

from app.media.metadata.aliases import select_aliases


def test_select_aliases_keeps_chinese_native_english():
    values = select_aliases(
        "FX战士久留美",
        "FX戦士くるみちゃん",
        ["FX Fighter KURUMICHAN", "FX 戰士久留美", "FX 전사 쿠루미"],
        countries=["JP"],
        original_language="ja",
    )
    assert values == ["FX战士久留美", "FX戦士くるみちゃん", "FX Fighter KURUMICHAN"]


def test_chinese_release_does_not_add_extra_native_alias():
    values = select_aliases(
        "流浪地球",
        "流浪地球",
        ["The Wandering Earth", "流浪地球2", "The Wandering Earth II"],
        countries=["CN"],
        original_language="zh",
    )
    assert values == ["流浪地球", "The Wandering Earth"]


def test_select_aliases_dedupes_and_limits_three():
    values = select_aliases("标题", "标题", ["别名", "English Title", "Another"])
    assert values == ["标题", "English Title"]
    assert len(values) <= 3
