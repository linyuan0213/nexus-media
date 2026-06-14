import json
from enum import Enum
from typing import Any

import orjson

import log


class JsonUtils:
    @staticmethod
    def json_serializable(obj):
        """
        将普通对象转化为支持json序列化的对象
        @param obj: 待转化的对象
        @return: 支持json序列化的对象
        """

        def _try(o):
            if isinstance(o, Enum):
                return o.value
            try:
                return o.__dict__
            except Exception as err:
                log.warn(f"[JsonUtils]对象序列化失败: {err}")
                return str(o)

        return json.loads(json.dumps(obj, default=lambda o: _try(o)))

    @staticmethod
    def is_valid_json(text):
        """
        判断是否是有效的json格式字符串
        """
        try:
            if not text:
                return False
            orjson.loads(text)
            return True
        except orjson.JSONDecodeError:
            return False

    @staticmethod
    def get_nested_value(data, keys):
        """
        递归地获取嵌套结构中指定字段的值
        """
        if isinstance(data, dict):
            key, *remaining_keys = keys.split(".", 1)
            if "[" in key and "]" in key:
                key, index = key.split("[")
                index = int(index[:-1])
                value = data.get(key, [])
                if isinstance(value, list):
                    value = value[index] if len(value) > index else None
                else:
                    value = None
            else:
                value = data.get(key)
            if remaining_keys:
                return JsonUtils.get_nested_value(value, remaining_keys[0])
            return value
        elif isinstance(data, list):
            index, *remaining_keys = keys.split(".", 1)
            index = int(index)
            value = data[index] if len(data) > index else None
            if remaining_keys:
                return JsonUtils.get_nested_value(value, remaining_keys[0])
            return value
        else:
            return None

    @staticmethod
    def get_json_object(json_str, field):
        try:
            # 解析 JSON 字符串
            json_data = orjson.loads(json_str)
            # 提取指定字段的值
            field_value = JsonUtils.get_nested_value(json_data, field)
            return field_value
        except orjson.JSONDecodeError as e:
            log.warn(f"[JsonUtils]JSON 解析错误: {e}")
            return None
        except Exception as e:
            log.warn(f"[JsonUtils]提取字段失败: {e}")
            return None

    @staticmethod
    def dumps(
        obj: Any,
        *,
        ensure_ascii: bool = False,
        indent: bool | int = False,
        default=None,
        sort_keys: bool = False,
        separators: tuple[str, str] | None = None,
    ) -> str:
        """使用 orjson 序列化 JSON；需要缩进、自定义 encoder 或 separators 时回退到标准库 json."""
        if indent or default is not None or separators is not None:
            indent_value = 2 if indent is True else (None if indent is False else indent)
            return json.dumps(
                obj,
                ensure_ascii=ensure_ascii,
                indent=indent_value,
                default=default,
                sort_keys=sort_keys,
                separators=separators,
            )

        option = orjson.OPT_NON_STR_KEYS
        if not ensure_ascii:
            option |= orjson.OPT_SERIALIZE_NUMPY
        if sort_keys:
            option |= orjson.OPT_SORT_KEYS

        return orjson.dumps(obj, option=option).decode("utf-8")

    @staticmethod
    def dump(
        obj: Any,
        file,
        *,
        ensure_ascii: bool = False,
        indent: bool | int = False,
        default=None,
        sort_keys: bool = False,
        separators: tuple[str, str] | None = None,
    ) -> None:
        """将 JSON 写入文件对象；需要缩进、自定义 encoder 或 separators 时回退到标准库 json."""
        if indent or default is not None or separators is not None:
            indent_value = 2 if indent is True else (None if indent is False else indent)
            json.dump(
                obj,
                file,
                ensure_ascii=ensure_ascii,
                indent=indent_value,
                default=default,
                sort_keys=sort_keys,
                separators=separators,
            )
            return

        file.write(JsonUtils.dumps(obj, ensure_ascii=ensure_ascii, sort_keys=sort_keys))

    @staticmethod
    def loads(s: str | bytes) -> Any:
        """使用 orjson 反序列化 JSON."""
        if isinstance(s, str):
            s = s.encode("utf-8")
        return orjson.loads(s)

    @staticmethod
    def load(file) -> Any:
        """从文件对象读取 JSON."""
        return JsonUtils.loads(file.read())
