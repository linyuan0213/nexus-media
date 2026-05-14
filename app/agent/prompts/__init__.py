"""LLM 提示词模板集合"""
from app.agent.prompts.media import MEDIA_BATCH_PROMPT, MEDIA_RECOGNITION_PROMPT
from app.agent.prompts.search import SEARCH_INTENT_PROMPT

__all__ = [
    "MEDIA_RECOGNITION_PROMPT",
    "MEDIA_BATCH_PROMPT",
    "SEARCH_INTENT_PROMPT",
]
