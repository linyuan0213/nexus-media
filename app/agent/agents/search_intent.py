# -*- coding: utf-8 -*-
"""搜索意图理解 Agent"""
from typing import Optional

import log
from pydantic import BaseModel

from app.agent.prompts.search import SEARCH_INTENT_PROMPT
from app.agent.service import AgentService


class SearchIntent(BaseModel):
    """搜索意图解析结果"""
    keywords: str = ""                  # 核心搜索关键词
    media_type: Optional[str] = None    # movie / tv / anime
    year: Optional[int] = None          # 指定年份
    season: Optional[int] = None        # 指定季
    episode: Optional[int] = None       # 指定集
    quality: Optional[str] = None       # 质量要求
    language: Optional[str] = None      # 语言偏好
    source: Optional[str] = None        # 来源偏好
    is_specific: bool = False           # 是否明确指定了具体作品


class SearchIntentAgent:
    """搜索意图理解 Agent"""

    def __init__(self):
        self._svc = AgentService()

    @property
    def ready(self) -> bool:
        return self._svc.ready

    def parse(self, query: str) -> Optional[SearchIntent]:
        """解析用户搜索意图"""
        if not self.ready:
            return None
        log.info(f"【SearchIntentAgent】解析意图: {query[:80]}...")
        result = self._svc.structured_chat(
            messages=[{"role": "user", "content": query}],
            system_prompt=SEARCH_INTENT_PROMPT,
            response_model=SearchIntent,
        )
        if result and result.is_specific:
            log.info(f"【SearchIntentAgent】解析成功: keywords={result.keywords}, type={result.media_type}, "
                     f"season={result.season}, ep={result.episode}, year={result.year}")
        elif result:
            log.info(f"【SearchIntentAgent】意图不明确: keywords={result.keywords}")
        else:
            log.warn("【SearchIntentAgent】解析失败")
        return result
