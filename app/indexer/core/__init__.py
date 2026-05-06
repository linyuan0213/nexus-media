# -*- coding: utf-8 -*-
"""
索引器核心流水线模块

职责：将搜索结果的处理流程解耦为清晰的三个阶段：
1. 本地解析和过滤（Local Filter）
2. 批量媒体识别（Batch Identification）
3. TMDB 匹配和最终过滤（Match Filter）

使用方式：
    from app.indexer.core import SearchPipeline
    pipeline = SearchPipeline()
    results = pipeline.process(raw_results, ...)
"""

from .pipeline import SearchPipeline
from .batch_identifier import BatchIdentifier
from .result_filter import ResultFilter
from .models import SearchCandidate

__all__ = [
    "SearchPipeline",
    "BatchIdentifier",
    "ResultFilter",
    "SearchCandidate",
]
