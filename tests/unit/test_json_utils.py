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

    def test_dumps_basic(self):
        assert JsonUtils.dumps({"a": 1}) == '{"a":1}'

    def test_dumps_ensure_ascii(self):
        # orjson 没有 ensure_ascii 选项，始终保留 unicode
        result = JsonUtils.dumps({"key": "中文"}, ensure_ascii=True)
        assert result == '{"key":"中文"}'

    def test_dumps_no_ensure_ascii(self):
        result = JsonUtils.dumps({"key": "中文"}, ensure_ascii=False)
        assert result == '{"key":"中文"}'

    def test_dumps_indent_fallback_to_stdlib(self):
        result = JsonUtils.dumps({"a": 1}, indent=True)
        assert result == '{\n  "a": 1\n}'

    def test_dumps_custom_default_fallback_to_stdlib(self):
        result = JsonUtils.dumps({"dt": "2024-01-01"}, default=lambda o: str(o))
        assert '"2024-01-01"' in result

    def test_dumps_sort_keys(self):
        assert JsonUtils.dumps({"b": 1, "a": 2}, sort_keys=True) == '{"a":2,"b":1}'

    def test_dump_to_file(self):
        import io

        buffer = io.StringIO()
        JsonUtils.dump({"a": 1}, buffer)
        buffer.seek(0)
        assert buffer.read() == '{"a":1}'

    def test_dump_to_file_with_indent(self):
        import io

        buffer = io.StringIO()
        JsonUtils.dump({"a": 1}, buffer, indent=True)
        buffer.seek(0)
        assert buffer.read() == '{\n  "a": 1\n}'

    def test_loads_str(self):
        assert JsonUtils.loads('{"a":1}') == {"a": 1}

    def test_loads_bytes(self):
        assert JsonUtils.loads(b'{"a":1}') == {"a": 1}

    def test_load_from_file(self):
        import io

        buffer = io.BytesIO(b'{"a":1}')
        assert JsonUtils.load(buffer) == {"a": 1}
