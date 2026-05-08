# LLM Agent 集成设计文档

## 1. 概述

### 1.1 目标

将 LLM（大语言模型）作为智能 Agent 集成到 NAS-Tools 中，替代/增强现有的正则表达式硬编码解析器，实现：

- 复杂媒体文件名的高精度识别（动漫、多语言混合、不规则格式）
- 非标准季/集编号与 TMDB 标准季/集的自动映射
- 批量并行识别以满足搜索/订阅的速度要求
- 可扩展的消息模板 Agent 和自定义业务 Agent

### 1.2 当前局限

| 问题 | 现状 | LLM 解决方案 |
|------|------|-------------|
| 文件名解析 | Token + 正则硬编码，对不规则格式脆弱 | LLM 语义理解，处理任意格式 |
| 季集映射 | 无映射能力，S04E03 和 S1E57 无法对应 | LLM + TMDB API 查询自动映射 |
| 动漫检测 | 依赖 `【】` 模式判断 | LLM 直接从内容语义判断 |
| 批量识别 | RSS 阶段 2 用 ThreadPool（最多4w） | LLM batch API 一次处理多条 |
| AI 集成 | 仅作为 TMDB 搜索的最后一个回退 | 作为首要识别 + 多 Agent 协作 |

### 1.3 文件示例

**输入：**
```
[ANi] Pardon the Intrusion Im Home / 我回来了，他又来打扰了！第四季 - 03 [1080P][Baha][WEB-DL][AAC AVC][CHT][MP4]
```

**期望输出：**
```json
{
  "title_en": "Pardon the Intrusion I'm Home",
  "title_cn": "我回来了，他又来打扰了！",
  "season": 4,
  "episode": 3,
  "resolution": "1080p",
  "source": "WEB-DL",
  "video_codec": "AVC",
  "audio_codec": "AAC",
  "language": ["CHT"],
  "platform": "Baha",
  "release_group": "ANi",
  "format": "MP4",
  "type": "anime",
  "tmdb_id": null,
  "tmdb_season": null,
  "tmdb_episode": null
}
```

---

## 2. Agent 架构

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                      Agent Registry                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │  Media   │ │  Season  │ │ Template │ │   Custom     │ │
│  │Recognizer│ │  Mapper  │ │  Agent   │ │   Agents     │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│       │             │            │               │        │
│  ┌────┴─────────────┴────────────┴───────────────┴────┐   │
│  │                   LLM Provider                      │   │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐             │   │
│  │  │ OpenAI  │ │ DeepSeek│ │  Custom  │             │   │
│  │  │ (GPT-4) │ │  (V3)   │ │ (Ollama) │             │   │
│  │  └─────────┘ └─────────┘ └──────────┘             │   │
│  └────────────────────────────────────────────────────┘   │
│                           │                                │
│  ┌────────────────────────┴────────────────────────────┐  │
│  │                  Tool System                         │  │
│  │  TMDB API  │  Media Cache  │  Search Service  │ ... │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 2.2 核心类设计

```python
# app/agent/base.py
class BaseAgent:
    """Agent 基类"""
    agent_name: str
    provider: str = "openai"   # openai | deepseek | custom
    model: str = "gpt-4o-mini"
    system_prompt: str
    tools: List[Callable]
    max_tokens: int = 4096
    temperature: float = 0.1

    async def run(self, input_data) -> dict
    async def run_batch(self, inputs: List) -> List[dict]


# app/agent/media_recognizer.py
class MediaRecognizerAgent(BaseAgent):
    """媒体识别 Agent — 解析文件名/种子名"""
    agent_name = "media_recognizer"
    # 支持 Function Calling，可调用 TMDB API 验证


# app/agent/season_mapper.py
class SeasonMapperAgent(BaseAgent):
    """季集映射 Agent — 非标准季集 → TMDB 标准季集"""
    agent_name = "season_mapper"
    # 需要 TMDB API tool 获取剧集分组信息


# app/agent/template_agent.py
class TemplateAgent(BaseAgent):
    """消息模板 Agent — 自定义通知格式"""
    agent_name = "template"


# app/agent/registry.py
class AgentRegistry:
    """Agent 注册中心 — 统一管理所有 Agent"""
    _agents: Dict[str, BaseAgent] = {}
    
    @classmethod
    def register(cls, agent: BaseAgent)
    @classmethod
    def get(cls, name: str) -> BaseAgent
    @classmethod
    def run_pipeline(cls, pipeline: List[str], input_data) -> dict
```

### 2.3 Agent 执行流水线

```python
# 媒体识别流水线
pipeline = [
    "media_recognizer",   # 阶段1: 解析文件名
    "season_mapper",      # 阶段2: 映射季集
    "tmdb_enricher",      # 阶段3: 补充 TMDB 信息 (非 Agent，直接 API)
]

result = AgentRegistry.run_pipeline(pipeline, input_data="[ANi] Pardon...")
```

---

## 3. 媒体识别 Agent (MediaRecognizerAgent)

### 3.1 System Prompt 设计

```
你是一个专业的媒体文件名解析助手，专门识别动漫和影视资源的文件名。

## 输入格式
你会收到一个文件名或种子名，可能包含：
- [ANi] — 发布组/字幕组
- Pardon the Intrusion I'm Home — 英文标题
- 我回来了，他又来打扰了！第四季 - 03 — 中文标题、季集
- [1080P][Baha][WEB-DL][AAC AVC][CHT][MP4] — 分辨率、平台、来源、编码、语言、格式

## 输出要求
返回 JSON，包含以下字段（未知字段填 null）：
{
  "title_en": "英文/罗马音标题",
  "title_cn": "中文标题",
  "alternate_titles": ["其他可能的标题变体"],
  "year": 年份数字或null,
  "season": 季号数字或null,
  "season_raw": "原始季文本（如第四季）或null",
  "episode": 集号数字或null,
  "resolution": "分辨率（1080p/2160p/720p等）",
  "source": "来源（BDRip/WEB-DL/HDTV等）",
  "video_codec": "视频编码（AVC/HEVC/XviD等）",
  "audio_codec": "音频编码（AAC/FLAC/DTS等）",
  "language": ["语言标签列表（CHT/CHS/JPN等）"],
  "platform": "平台（Baha/CR/NF等）",
  "release_group": "发布组",
  "format": "文件格式（MP4/MKV等）",
  "edition": "版本/导演剪辑版等",
  "type": "movie/tv/anime",
  "is_anime": true/false
}

## 规则
- 季集信息优先从中文字段提取（第四季→4）
- 分辨率统一为小写（1080P→1080p）
- 双语文件名保留两个标题
- 如果是剧集包（全X集/Complete），episode 填 null
```

### 3.2 批量识别设计

```python
class MediaRecognizerAgent(BaseAgent):
    
    async def run_batch(self, filenames: List[str]) -> List[dict]:
        """批量识别 — 一次 API 调用处理多条"""
        batch_prompt = """
请识别以下文件名列表，返回 JSON 数组：
["文件名1", "文件名2", ...]
        
返回格式：[{识别结果1}, {识别结果2}, ...]
"""
        response = await self._call_llm(
            messages=[{"role": "user", "content": batch_prompt + "\n".join(filenames)}],
            response_format={"type": "json_object"}
        )
        return response["results"]
    
    def recognize_batch(self, filenames: List[str], batch_size: int = 20) -> List[dict]:
        """同步批量识别 — 将大批量分片处理"""
        results = []
        for i in range(0, len(filenames), batch_size):
            batch = filenames[i:i+batch_size]
            results.extend(self.run_batch_sync(batch))
        return results
```

### 3.3 集成点

```python
# 修改 app/media/meta/metainfo.py
def MetaInfo(title, subtitle=None, isfile=True):
    # 优先级: LLM Agent > 传统 Token 解析
    cfg = Config().get_config("agent")
    if cfg.get("media_recognizer_enabled"):
        try:
            agent = AgentRegistry.get("media_recognizer")
            result = agent.run_sync(title)
            return _build_meta_from_agent_result(result)
        except Exception:
            pass  # 回退到传统解析
    
    # 传统解析（现有逻辑保持不变）
    return _legacy_parse(title, subtitle, isfile)
```

---

## 4. 季集映射 Agent (SeasonMapperAgent)

### 4.1 问题描述

不同数据源的季集编号不一致：

| 数据源 | 格式 | 说明 |
|--------|------|------|
| 文件名 | S0403 / S04E03 | 第4季第3集 |
| 文件名 | S1E57 | 累计集号 |
| TMDB | Season 4, Episode 3 | 标准分季 |
| TMDB | Season 1, Episode 57 | 累计分季（单季长番） |

**核心矛盾**：文件名 `S04E03` 对应 TMDB `S01E57`（某长番动漫按 TMDB 定义为单季），反过来文件名 `S1E57` 对应 TMDB `S04E03`（TMDB 按标准季分）。

### 4.2 映射策略

```python
class SeasonMapperAgent(BaseAgent):
    agent_name = "season_mapper"
    
    tools = [
        "tmdb_get_tv_seasons",      # 获取 TMDB 该剧的所有季
        "tmdb_get_season_episodes",  # 获取某季的所有集
        "tmdb_search_tv",            # 搜索电视剧
    ]
    
    system_prompt = """
你是一个电视剧/动漫季集映射助手。当文件名中的季集编号与 TMDB 标准不一致时，
你需要查询 TMDB API 获取正确的季集映射。

## 映射场景
1. **文件名S1E57 → TMDB应在哪季？**
   - 查询 TMDB 所有季的剧集列表
   - 如果 S1-S3 各有 12 集 (36集)，S4 从第37集开始
   - 则 S1E57 = S4E21

2. **文件名S4E03 → TMDB S1E57?**
   - 判断该剧在 TMDB 是分季还是单季
   - 如果是单季长番（如某些动漫），S4E03 映射到累计集号

3. **文件名包含「全08集」→ 对应哪季？**
   - 查询 TMDB 找到包含 8 集的季

## 步骤
1. 根据标题搜索 TMDB 获取 TV ID
2. 获取所有季列表和各季集数
3. 建立分季→累计集号的映射表
4. 返回标准 TMDB 季集号
    """
```

### 4.3 映射数据结构

```python
@dataclass
class SeasonMapping:
    """季集映射结果"""
    tmdb_id: int                      # TMDB 剧集 ID
    source_season: int                # 文件名中的季号
    source_episode: int               # 文件名中的集号
    source_total: Optional[int]       # 文件名中的总集数
    target_season: int                # TMDB 标准季号
    target_episode: int               # TMDB 标准集号
    mapping_type: str                 # absolute | season_based | single_season
    confidence: float                 # 置信度 0-1
    season_breakdown: Dict[int, int]  # 季号→该季最后一集累计号
    # 例如 {1: 12, 2: 24, 3: 36, 4: 48}
```

### 4.4 批量缓存

季集映射应该缓存到 Redis，避免重复查询 TMDB API：

```python
# 缓存 key: tmdb_id:absolute:{episode_number}
# 缓存值: {"season": 4, "episode": 3}
CACHE_KEY = f"season_map:{tmdb_id}:abs:{absolute_episode}"
```

---

## 5. 批量识别系统

### 5.1 RSS 集成

```python
# 修改 app/services/rss_core.py 阶段2
async def _batch_recognize_media(self, items: List[dict]) -> List[dict]:
    """批量识别 RSS 标题"""
    titles = [item["title"] for item in items]
    
    # 优先使用 LLM Agent 批量识别
    cfg = Config().get_config("agent")
    if cfg.get("batch_recognize_enabled"):
        try:
            agent = AgentRegistry.get("media_recognizer")
            results = await agent.run_batch(titles)
            for item, result in zip(items, results):
                item["meta"] = result
            return items
        except Exception:
            pass
    
    # 回退到传统逐个识别
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(Media().get_media_info, t): t for t in titles}
        ...
```

### 5.2 搜索集成

```python
# 修改 app/services/search_torrents.py — 搜索关键词提取
def get_keyword_from_string(content):
    # 优先用 LLM 提取搜索参数
    cfg = Config().get_config("agent")
    if cfg.get("search_intent_enabled"):
        try:
            agent = AgentRegistry.get("search_parser")
            result = agent.run_sync(content)
            return result  # {"keyword": "...", "type": "tv", "season": 4, ...}
        except Exception:
            pass
    
    # 回退到 StringUtils.get_keyword_from_string()
    return StringUtils.get_keyword_from_string(content)
```

### 5.3 批量处理性能设计

| 方式 | 单次处理量 | 延迟 | 适用场景 |
|------|----------|------|---------|
| 单条 API 调用 | 1 条 | ~200ms | 交互式搜索 |
| Batch API 调用 | 20-50 条 | ~1s | RSS 定时任务 |
| 流式处理 | 持续 | 实时 | 聊天机器人消息 |

```
RSS 批量识别流程:
  RSS items (100条)
    ↓ 去重
  unique items (70条)
    ↓ 分片 (batch_size=20)
  ┌─ batch 1 (20条) ─→ LLM API ─→ results
  ├─ batch 2 (20条) ─→ LLM API ─→ results
  ├─ batch 3 (20条) ─→ LLM API ─→ results
  └─ batch 4 (10条) ─→ LLM API ─→ results
    ↓ 合并
  identified items (70条)
    ↓
  匹配订阅规则 → 下载
```

---

## 6. 消息模板 Agent (TemplateAgent)

### 6.1 设计目标

允许用户自定义通知消息格式，LLM 负责：
- 根据媒体类型选择合适的模板风格
- 自动生成 Emoji 和格式化文本
- 支持多语言（中文/英文）

### 6.2 配置示例

```json
{
  "agent": {
    "template_agent": {
      "enabled": true,
      "templates": {
        "download_start": {
          "system": "你是下载通知格式化助手，用简洁风格",
          "format": "emoji_first_line"
        },
        "transfer_finished": {
          "system": "你是入库通知格式化助手，用庆祝风格",
          "format": "emoji_first_line"
        },
        "weekly_report": {
          "system": "你是周报生成助手，用数据风格",
          "format": "markdown"
        }
      }
    }
  }
}
```

### 6.3 Agent 实现

```python
class TemplateAgent(BaseAgent):
    agent_name = "template"
    
    system_prompt = """
你是一个消息通知格式化助手。根据输入的事件类型和媒体信息，生成格式化的通知消息。

## 输入格式
{"event": "download_start", "media": {媒体信息}, "style": "emoji_first_line"}

## 输出格式
{
  "title": "🎬 我回来了，他又来打扰了！S04E03 开始下载",
  "text": "站点: ANi · 分辨率: 1080p · 来源: WEB-DL · 大小: 1.2GB",
  "emoji": "🎬"
}

## 风格
- emoji_first_line: 标题含一个 Emoji，正文简洁
- markdown: 用 Markdown 格式化（**粗体**，`代码`）
- minimal: 最简风格，无 Emoji
- celebration: 庆祝风格，多个 Emoji
    """
```

---

## 7. 自定义 Agent 扩展

### 7.1 扩展接口

```python
# app/agent/base.py
class BaseAgent:
    agent_name: str                          # 唯一标识
    agent_type: str = "custom"               # media | mapper | template | custom
    enabled: bool = True
    
    def validate_input(self, input_data) -> bool
    def pre_process(self, input_data) -> dict
    def post_process(self, output_data) -> dict
    
    @abstractmethod
    async def run(self, input_data) -> dict: ...
    @abstractmethod
    async def run_batch(self, inputs: List) -> List[dict]: ...
```

### 7.2 已规划 Agent 列表

| Agent | 类型 | 功能 | 优先级 |
|-------|------|------|--------|
| `media_recognizer` | media | 文件名/种子名解析 | P0 |
| `season_mapper` | mapper | 非标准季集→TMDB 映射 | P0 |
| `search_parser` | media | 搜索意图解析（关键词提取） | P1 |
| `template` | template | 消息通知格式化 | P1 |
| `subtitle_sync` | custom | 字幕时间轴调整 | P2 |
| `quality_judge` | custom | 资源质量评估（多版本选择） | P2 |
| `plugin_agent` | custom | 用户自定义插件 Agent | P2 |
| `weekly_report` | custom | 周报生成（统计+推荐） | P2 |

### 7.3 插件化 Agent 配置

```json
{
  "agent": {
    "custom_agents": [
      {
        "name": "my_translator",
        "description": "自动翻译日文标题为中文",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "system_prompt": "你是日文→中文翻译助手...",
        "trigger": "on_download_start",
        "input_fields": ["title_cn", "title_en"],
        "output_fields": ["translated_title"]
      }
    ]
  }
}
```

---

## 8. 技术选型

### 8.1 LLM Provider 配置

```json
{
  "agent": {
    "default_provider": "openai",
    "providers": {
      "openai": {
        "api_key": "sk-xxx",
        "api_url": "https://api.openai.com",
        "models": {
          "default": "gpt-4o-mini",
          "batch": "gpt-4o",
          "reasoning": "o1-mini"
        }
      },
      "deepseek": {
        "api_key": "sk-xxx",
        "api_url": "https://api.deepseek.com",
        "models": {
          "default": "deepseek-chat",
          "batch": "deepseek-chat",
          "reasoning": "deepseek-reasoner"
        }
      },
      "custom": {
        "api_key": "",
        "api_url": "http://localhost:11434",
        "models": {
          "default": "qwen2.5:7b"
        }
      }
    }
  }
}
```

### 8.2 模型选择策略

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| 文件名解析 | gpt-4o-mini / deepseek-chat | 低延迟、低成本、简单推理 |
| 季集映射 | gpt-4o / deepseek-reasoner | 多步推理、需要 Function Calling |
| 批量识别 | deepseek-chat / gpt-4o | 高吞吐、Batch API 支持 |
| 消息模板 | gpt-4o-mini / qwen2.5:7b | 简单任务，本地模型足够 |

### 8.3 成本估算

| 模型 | 输入价格 | 输出价格 | 单次识别成本 | 日批量(1000次) |
|------|---------|---------|------------|--------------|
| gpt-4o-mini | $0.15/M | $0.60/M | ~$0.0003 | ~$0.30 |
| deepseek-chat | ¥1/M | ¥2/M | ~¥0.002 | ~¥2.00 |
| qwen2.5:7b (本地) | 免费 | 免费 | 免费 | 免费 |

---

## 9. 实施计划

### 9.1 阶段一：基础设施 (P0)

1. `app/agent/` 目录结构搭建
2. `BaseAgent` / `AgentRegistry` 实现
3. LLM Provider 抽象层 (OpenAI / DeepSeek / Custom)
4. 配置界面集成（前端 `setting/agent` 页面）
5. 现有 `OpenAiHelper` 迁移到 Agent 框架

### 9.2 阶段二：媒体识别 (P0)

1. `MediaRecognizerAgent` 实现
2. `SeasonMapperAgent` 实现（带 TMDB Function Calling）
3. 批量识别 API 支持（RSS 集成）
4. 集成到 `MetaInfo()` 工厂函数（优先 LLM，回退传统）
5. 缓存层（Redis 缓存识别结果）

### 9.3 阶段三：搜索与通知 (P1)

1. `SearchParserAgent` — 搜索意图解析
2. `TemplateAgent` — 消息模板
3. 集成到搜索/订阅/下载流程

### 9.4 阶段四：生态扩展 (P2)

1. 插件化 Agent 配置
2. `QualityJudge` / `SubtitleSync` / `WeeklyReport` Agent
3. 前端 Agent 管理页面

---

## 10. 配置示例

### 10.1 完整配置

```json
{
  "agent": {
    "enabled": true,
    "default_provider": "deepseek",
    "providers": {
      "deepseek": {
        "api_key": "sk-xxx",
        "api_url": "https://api.deepseek.com",
        "models": {
          "default": "deepseek-chat",
          "batch": "deepseek-chat"
        }
      }
    },
    "agents": {
      "media_recognizer": {
        "enabled": true,
        "provider": "deepseek",
        "model": "deepseek-chat",
        "batch_size": 20,
        "cache_ttl": 86400,
        "fallback_to_legacy": true
      },
      "season_mapper": {
        "enabled": true,
        "provider": "deepseek",
        "model": "deepseek-chat",
        "cache_ttl": 604800
      },
      "template": {
        "enabled": true,
        "provider": "deepseek",
        "model": "deepseek-chat"
      }
    }
  }
}
```

### 10.2 环境变量

```bash
# LLM Provider
AGENT_OPENAI_API_KEY=sk-xxx
AGENT_OPENAI_API_URL=https://api.openai.com
AGENT_DEEPSEEK_API_KEY=sk-xxx
AGENT_DEEPSEEK_API_URL=https://api.deepseek.com
AGENT_CUSTOM_API_KEY=
AGENT_CUSTOM_API_URL=http://localhost:11434

# Agent 开关
AGENT_MEDIA_RECOGNIZER_ENABLED=true
AGENT_SEASON_MAPPER_ENABLED=true
AGENT_BATCH_RECOGNIZE_ENABLED=true
AGENT_TEMPLATE_ENABLED=true
```
