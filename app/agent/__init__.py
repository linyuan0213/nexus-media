"""app.agent — 大模型 Agent 层

架构:
  - service.py        — AgentService 门面（统一入口）
  - config.py         — 提供商配置
  - providers/        — 多提供商实现（OpenAI/Ollama/Gemini）
  - agents/           — 领域 Agent（媒体识别/搜索意图/对话/问答）
  - prompts/          — 提示词模板
"""

from app.agent.agents import (
    BatchResult,
    ChatAgent,
    MediaRecognizer,
    MediaResult,
    QuestionAnswerAgent,
    SearchIntent,
    SearchIntentAgent,
)
from app.agent.config import ProviderConfig, get_provider
from app.agent.providers import (
    BaseProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderConfig,
)
from app.agent.service import AgentService

__all__ = [
    # Service
    "AgentService",
    # Config
    "ProviderConfig",
    "get_provider",
    # Providers
    "BaseProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "GeminiProvider",
    # Agents
    "MediaRecognizer",
    "MediaResult",
    "BatchResult",
    "SearchIntentAgent",
    "SearchIntent",
    "ChatAgent",
    "QuestionAnswerAgent",
]
