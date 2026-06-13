"""SubmoduleLoader 单元测试."""

from app.utils.submodule_loader import SubmoduleLoader


class TestSubmoduleLoader:
    def test_import_submodules(self):
        classes = SubmoduleLoader.import_submodules("app.utils")
        names = [c.__name__ for c in classes]
        assert "NumberUtils" in names
        assert "SubmoduleLoader" in names

    def test_import_submodules_with_filter(self):
        classes = SubmoduleLoader.import_submodules("app.utils", filter_func=lambda name, obj: name == "NumberUtils")
        assert [c.__name__ for c in classes] == ["NumberUtils"]

    def test_import_submodules_private_skipped(self):
        classes = SubmoduleLoader.import_submodules("app.utils")
        names = [c.__name__ for c in classes]
        assert "_Mock" not in names
