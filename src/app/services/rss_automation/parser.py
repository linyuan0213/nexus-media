"""RSS 解析引擎."""

from typing import Any

import jsonpath
from lxml import etree
from lxml.etree import _Element

from app.core.exceptions import RepositoryError, ServiceError
from app.utils.json_utils import JsonUtils


class RssParserEngine:
    """RSS 解析引擎：纯逻辑，无状态，负责 XML/JSON 报文解析"""

    @staticmethod
    def parse_items(rss_parser: dict, rss_text: str, address_index: int) -> list[dict[str, Any]]:
        """
        根据解析器配置解析 RSS 原始文本
        :param rss_parser: 解析器配置字典
        :param rss_text: HTTP 响应文本
        :param address_index: 地址序号（用于回显）
        :return: 解析后的条目列表
        """
        parser_type = rss_parser.get("type")
        parser_format = JsonUtils.loads(rss_parser.get("format") or "{}")
        rss_result: list[dict[str, Any]] = []

        if parser_type == "XML":
            try:
                result_tree = etree.XML(rss_text.encode("utf-8"))
                item_list_raw = result_tree.xpath(parser_format.get("list"))
                item_list = item_list_raw if isinstance(item_list_raw, list) else []
                for item in item_list:
                    if not isinstance(item, _Element):
                        continue
                    rss_item = {}
                    for key, attr in parser_format.get("item", {}).items():
                        if attr.get("path"):
                            if attr.get("namespaces"):
                                value = item.xpath(
                                    "//ns:{}".format(attr.get("path")), namespaces={"ns": attr.get("namespaces")}
                                )
                            else:
                                value = item.xpath(attr.get("path"))
                        elif attr.get("value"):
                            value = attr.get("value")
                        else:
                            continue
                        if value and isinstance(value, list):
                            rss_item.update({key: value[0]})
                    rss_item.update({"address_index": address_index})
                    rss_result.append(rss_item)
            except (ServiceError, RepositoryError) as e:
                raise ValueError(f"XML解析失败: {e!s}") from e
            except Exception as err:
                raise ValueError(f"XML解析失败: {err!s}") from err

        elif parser_type == "JSON":
            try:
                result_json = JsonUtils.loads(rss_text)
            except (ServiceError, RepositoryError) as e:
                raise ValueError(f"JSON解析失败: {e!s}") from e
            except Exception as err:
                raise ValueError(f"JSON解析失败: {err!s}") from err
            item_list = jsonpath.jsonpath(result_json, parser_format.get("list"))  # type: ignore[call-arg]
            if not item_list or not isinstance(item_list, list):
                raise ValueError("jsonpath结果不是列表")
            item_list = item_list[0]
            if not isinstance(item_list, list):
                raise ValueError("list后不是列表")
            for item in item_list:
                rss_item = {}
                for key, attr in parser_format.get("item", {}).items():
                    if attr.get("path"):
                        value = jsonpath.jsonpath(item, attr.get("path"))  # type: ignore[call-arg]
                    elif attr.get("value"):
                        value = attr.get("value")
                    else:
                        continue
                    if value:
                        rss_item.update({key: value[0]})
                rss_item.update({"address_index": address_index})
                rss_result.append(rss_item)

        return rss_result
