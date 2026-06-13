"""ReflectUtils 单元测试."""

from app.utils.reflect_utils import ReflectUtils


class TestReflectUtils:
    def test_get_class_by_name(self):
        cls = ReflectUtils.get_class_by_name("app.utils.number_utils", "NumberUtils")
        assert cls is not None
        assert cls.__name__ == "NumberUtils"

    def test_get_class_by_name_missing_lib(self):
        assert ReflectUtils.get_class_by_name("", "NumberUtils") is None
        assert ReflectUtils.get_class_by_name("app.utils.number_utils", "") is None

    def test_get_class_by_name_missing_class(self):
        assert ReflectUtils.get_class_by_name("app.utils.number_utils", "NotExist") is None

    def test_get_func_by_str_function(self):
        func = ReflectUtils.get_func_by_str("app.utils.pagination", "get_page_range")
        assert func is not None
        assert list(func(1, 3)) == [1, 2, 3]

    def test_get_func_by_str_method(self):
        func = ReflectUtils.get_func_by_str("app.utils.number_utils", "NumberUtils.get_size_gb")
        assert callable(func)
        assert func(1024 * 1024 * 1024) == 1.0

    def test_get_func_by_str_invalid(self):
        assert ReflectUtils.get_func_by_str("app.utils.number_utils", "") is None
        assert ReflectUtils.get_func_by_str("app.utils.number_utils", "NotExist.method") is None

    def test_import_submodules(self):
        classes = ReflectUtils.import_submodules("app.utils")
        names = [c.__name__ for c in classes]
        assert "NumberUtils" in names
        assert "ReflectUtils" in names

    def test_import_submodules_with_filter(self):
        classes = ReflectUtils.import_submodules("app.utils", filter_func=lambda name, obj: name == "NumberUtils")
        assert [c.__name__ for c in classes] == ["NumberUtils"]

    def test_import_submodules_private_skipped(self):
        classes = ReflectUtils.import_submodules("app.utils")
        names = [c.__name__ for c in classes]
        assert "_Mock" not in names
