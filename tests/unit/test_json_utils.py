"""JsonUtils 单元测试."""

from enum import Enum

from app.utils.json_utils import JsonUtils


class _Color(Enum):
    RED = "red"
    GREEN = "green"


class _Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class TestJsonUtils:
    def test_json_serializable_dict(self):
        result = JsonUtils.json_serializable({"a": 1})
        assert result == {"a": 1}

    def test_json_serializable_enum(self):
        result = JsonUtils.json_serializable({"color": _Color.RED})
        assert result == {"color": "red"}

    def test_json_serializable_object(self):
        result = JsonUtils.json_serializable({"point": _Point(1, 2)})
        assert result == {"point": {"x": 1, "y": 2}}

    def test_json_serializable_nested(self):
        result = JsonUtils.json_serializable([{"color": _Color.GREEN}])
        assert result == [{"color": "green"}]

    def test_is_valid_json_true(self):
        assert JsonUtils.is_valid_json('{"a": 1}') is True
        assert JsonUtils.is_valid_json("[1, 2]") is True

    def test_is_valid_json_false(self):
        assert JsonUtils.is_valid_json("{a: 1}") is False
        assert JsonUtils.is_valid_json("") is False
        assert JsonUtils.is_valid_json(None) is False

    def test_get_nested_value_dict(self):
        data = {"a": {"b": {"c": 1}}}
        assert JsonUtils.get_nested_value(data, "a.b.c") == 1

    def test_get_nested_value_list(self):
        data = {"items": [{"id": 1}, {"id": 2}]}
        assert JsonUtils.get_nested_value(data, "items[1].id") == 2

    def test_get_nested_value_missing(self):
        data = {"a": {"b": {}}}
        assert JsonUtils.get_nested_value(data, "a.b.c") is None
        assert JsonUtils.get_nested_value(data, "missing") is None

    def test_get_nested_value_list_root(self):
        data = [{"x": 1}, {"x": 2}]
        assert JsonUtils.get_nested_value(data, "1.x") == 2

    def test_get_json_object(self):
        assert JsonUtils.get_json_object('{"a": {"b": 1}}', "a.b") == 1

    def test_get_json_object_invalid(self):
        assert JsonUtils.get_json_object("not json", "a") is None
