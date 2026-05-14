"""
索引器核心流水线内部数据模型
"""


class SearchCandidate:
    """
    搜索候选对象，保存单个搜索结果在流水线各阶段的状态
    """

    def __init__(self, item, meta_info, res_order=0, skip_tmdb=False, media_info=None,
                 indexer_name="", indexer_order=0, indexer_public=False):
        self.item = item
        self.meta_info = meta_info
        self.res_order = res_order
        self.skip_tmdb = skip_tmdb
        self.media_info = media_info
        self.indexer_name = indexer_name
        self.indexer_order = indexer_order
        self.indexer_public = indexer_public


class FilterStats:
    """
    过滤统计，记录各阶段命中/失败数量
    """

    def __init__(self):
        self.index_sucess = 0
        self.index_rule_fail = 0
        self.index_match_fail = 0
        self.index_error = 0

    def merge(self, other):
        self.index_sucess += other.index_sucess
        self.index_rule_fail += other.index_rule_fail
        self.index_match_fail += other.index_match_fail
        self.index_error += other.index_error
        return self


class PipelineResult:
    """
    流水线最终结果
    """

    def __init__(self, results, stats, elapsed_seconds=0):
        self.results = results
        self.stats = stats
        self.elapsed_seconds = elapsed_seconds
