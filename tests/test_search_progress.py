#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搜索进度条修复测试
验证：
1. 索引器 search_by_keyword 不再写入 progress value（避免多线程竞争导致进度乱跳）
2. 外层 web/backend/search_torrents.py 和 app/searcher.py 统一控制进度 value
"""
import ast
import sys
import unittest

sys.path.insert(0, '.')


class TestSearchProgress(unittest.TestCase):
    """测试搜索进度条修复"""

    def _find_call_kwarg(self, node, func_name, kwarg_name, value_pattern):
        """在 AST 中查找指定函数调用是否包含特定关键字参数"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # 判断调用的是不是 func_name
                if isinstance(child.func, ast.Attribute) and child.func.attr == func_name:
                    for kw in child.keywords:
                        if kw.arg == kwarg_name:
                            # 简单模式匹配：检查源码文本是否包含 value_pattern
                            start_line = kw.value.lineno
                            end_line = kw.value.end_lineno
                            lines = self._source_lines[start_line - 1:end_line]
                            expr_text = "".join(lines)
                            if value_pattern in expr_text:
                                return True
        return False

    def test_indexer_does_not_update_progress_value(self):
        """
        验证 app/indexer/indexer.py 的 search_by_keyword 不再更新 progress value。
        value 更新应由外层调用方统一控制，否则多关键词并发时会出现进度乱跳/回退。
        """
        with open("app/indexer/indexer.py", "r", encoding="utf-8") as f:
            source = f.read()
        self._source_lines = source.splitlines(keepends=True)
        tree = ast.parse(source)

        # 找到 search_by_keyword 方法
        method_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "search_by_keyword":
                method_node = node
                break

        self.assertIsNotNone(method_node, "应存在 search_by_keyword 方法")

        has_value_update = self._find_call_kwarg(
            method_node, "update", "value", "round(100 *"
        )
        self.assertFalse(
            has_value_update,
            "search_by_keyword 内部不应再更新 progress value，否则多线程竞争会导致进度乱跳"
        )

    def test_web_search_updates_progress_externally(self):
        """
        验证 web/backend/search_torrents.py 在外层统一更新进度 value。
        """
        with open("web/backend/search_torrents.py", "r", encoding="utf-8") as f:
            source = f.read()
        self._source_lines = source.splitlines(keepends=True)
        tree = ast.parse(source)

        # 找到 search_medias_for_web 函数
        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "search_medias_for_web":
                func_node = node
                break

        self.assertIsNotNone(func_node, "应存在 search_medias_for_web 函数")

        has_value_update = self._find_call_kwarg(
            func_node, "update", "value", "round(100 *"
        )
        self.assertTrue(
            has_value_update,
            "search_medias_for_web 应在 as_completed 循环外层统一更新 progress value"
        )

    def test_searcher_updates_progress_externally(self):
        """
        验证 app/searcher.py 的 search_one_media 在外层统一更新进度 value。
        """
        with open("app/searcher.py", "r", encoding="utf-8") as f:
            source = f.read()
        self._source_lines = source.splitlines(keepends=True)
        tree = ast.parse(source)

        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "search_one_media":
                func_node = node
                break

        self.assertIsNotNone(func_node, "应存在 search_one_media 方法")

        has_value_update = self._find_call_kwarg(
            func_node, "update", "value", "round(100 *"
        )
        self.assertTrue(
            has_value_update,
            "search_one_media 应在 as_completed 循环外层统一更新 progress value"
        )


if __name__ == '__main__':
    unittest.main()
