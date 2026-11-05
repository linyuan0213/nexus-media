"""索引器优先级解析：站点管理里的 PRI 必须优先于公共站兜底值."""

from types import SimpleNamespace

from app.indexer.indexer import resolve_indexer_priority


def _indexer(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        name=kwargs.get("name", "Sukebei"),
        public=kwargs.get("public", True),
        pri=kwargs.get("pri", 0),
    )


class TestResolveIndexerPriority:
    def test_site_priority_beats_public_fallback(self):
        site_priorities = {"Sukebei": 106, "0Magnet": 100}

        assert resolve_indexer_priority(_indexer(name="Sukebei", public=True), None, site_priorities) == 106

    def test_indexer_override_beats_site_priority(self):
        site_priorities = {"Sukebei": 106}

        assert resolve_indexer_priority(_indexer(name="Sukebei"), 5, site_priorities) == 5

    def test_public_without_site_priority_uses_fallback(self):
        assert resolve_indexer_priority(_indexer(name="Unknown", public=True), None, {}) == 100

    def test_private_without_priority_uses_default(self):
        idx = _indexer(name="Unknown", public=False, pri=0)

        assert resolve_indexer_priority(idx, None, {}) == 100

    def test_private_uses_own_priority(self):
        idx = _indexer(name="M-Team", public=False, pri=1)

        assert resolve_indexer_priority(idx, None, {}) == 1
