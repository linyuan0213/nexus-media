# LLM Agent 集成设计文档

## 1. 设计目标

将 LLM（大语言模型）作为可选增强层集成到 Nexus Media 媒体识别管道中，遵循以下设计原则：

- **Parser 优先**：LLM 只参与文件名解析阶段（`Parser` 层），不参与 Lookup/TMDB 查询阶段。
- **透明降级**：LLM 不可用时，整个识别管道自动回退到正则解析，业务模块无感知。
- **单点收敛**：所有 LLM 调用通过 `AgentService` 门面收敛，业务模块不直接引用 Provider SDK。
- **配置热感知**：Provider 切换、功能开关变更无需重启进程。

## 2. 架构分层

```
业务层 (app/services/, app/plugin_framework/)
    │
    ├─ MetaInfo() ──→ 纯本地正则解析（轻量级，高频调用）
    ├─ MediaService.identify() ──→ Parser(LLM可选) → Lookup → Mapper
    ├─ MediaService.identify_batch() ──→ Parser.parse_batch() 批量识别
    ├─ search_torrents ──→ SearchIntentAgent 解析自然语言
    ├─ autosignin plugins ──→ QuestionAnswerAgent
    └─ autosub plugin ──→ ChatAgent.translate_to_zh()
    │
    ▼
门面层  AgentService（单例，配置/缓存/可用性管理）
    │
    ▼
Agent 层  MediaRecognizer / ChatAgent / SearchIntentAgent / QuestionAnswerAgent
    │
    ▼
Provider 层  OpenAIProvider / OllamaProvider / GeminiProvider
```

## 3. 媒体识别管道中的 Agent 角色

### 3.1 MetaInfo() 保持纯正则解析

`MetaInfo()` 是项目中调用频率最高的解析入口（60+ 处调用），被 `ResultFilter.local_filter()` 等高频场景逐条调用。**不集成 Agent**，保持纯本地正则解析，避免每个搜索结果都单独发 LLM 请求。

```
MetaInfo(title)
    │
    ├── WordsHelper().process(title) ──→ rev_title
    │
    └── 正则解析
           _is_anime(rev_title) ? parse_anime_title() : parse_video_title()
```

### 3.2 Agent 识别入口：MediaService.identify() / identify_batch()

Agent 识别只在这两个入口中使用，由 `MediaService._build_parser()` 选择 Parser：

```
identify(title)                    identify_batch(items)
    │                                  │
    ├── _build_parser()              ├── _build_parser()
    │      LLMParser (若配置启用)     │      LLMParser (若配置启用)
    │      或 RegexParser (默认)      │      或 RegexParser (默认)
    │                                  │
    ├── parser.parse(title)          ├── parser.parse_batch(titles)
    │      MediaRecognizer.          │      MediaRecognizer.
    │      recognize()               │      recognize_batch()
    │                                  │
    ├── TmdbLookup.lookup()          ├── TmdbLookup.lookup_batch()
    │                                  │
    └── EpisodeMapper.map()          └── EpisodeMapper.map_batch()
```

**关键设计**：
- `MetaInfo()` 只做轻量级本地解析，用于 `local_filter` 阶段的名称提取和规则过滤
- `identify()`/`identify_batch()` 做完整的 TMDB 查询 + 可选的 LLM 解析
- `identify_batch()` 使用 `recognize_batch()` 一次处理多条，减少 API 调用次数

### 3.3 为什么删除 _search_ai

原设计中 `identify()` 在 Lookup 失败后有一个 `_search_ai()` fallback，直接调用 `MediaRecognizer` 重新解析文件名并查 TMDB。该设计被删除，原因：

1. **重复解析**：Parser 阶段已经完成文件名解析，`_search_ai` 再调用 LLM 是冗余的。
2. **职责错位**：Lookup 阶段的 fallback 应该是"换个策略查 TMDB"，而不是"重新解析文件名"。
3. **成本翻倍**：同一条文件名在单次 `identify()` 中可能被 LLM 解析两次。

当前设计：Parser 层已包含 LLM 解析（`LLMParser`），Lookup 层只负责用 Parser 产出的结构化数据查询 TMDB，不再单独调用 LLM。

## 4. 非识别场景中的 Agent

| 场景 | 调用点 | Agent | 功能 |
|------|--------|-------|------|
| 搜索意图 | `search_torrents.py:search_medias_for_web()` | `SearchIntentAgent` | 将自然语言查询（"我想看最新的一拳超人第三季"）解析为结构化参数 |
| 消息机器人 | `search_torrents.py` | `ChatAgent.chat_with_session()` | 非搜索/下载/订阅开头的用户输入进入对话模式 |
| 站点签到 | `autosignin/chdbits.py` 等 | `QuestionAnswerAgent.answer()` | 验证码选择题答题 |
| 字幕翻译 | `autosub/plugin.py` | `ChatAgent.translate_to_zh()` | 字幕文本翻译 |

### 4.1 SearchIntentAgent 集成

```python
# search_medias_for_web() 中的集成点
intent_agent = SearchIntentAgent()
if intent_agent.ready:
    intent = intent_agent.parse(content)
    if intent and intent.is_specific:
        key_word = intent.keywords or key_word
        mtype = _map_media_type(intent.media_type) or mtype
        season_num = intent.season or season_num
        episode_num = intent.episode or episode_num
        year = str(intent.year) or year
```

Agent 解析结果**覆盖**而非替换 `StringUtils.get_keyword_from_string()` 的结果，只有当 Agent 提取的信息更具体时才生效。

## 5. 接口契约

### 5.1 AgentService 门面

```python
class AgentService:
    @property
    def ready: bool
    def chat(messages, system_prompt, temperature, response_format, use_cache) -> str
    def structured_chat(messages, system_prompt, response_model, temperature) -> BaseModel | None
```

**错误语义**：

| 场景 | `chat()` | `structured_chat()` |
|------|---------|---------------------|
| 未配置 / Provider 不可用 | `""` | `None` |
| API 超时 | `""` | `None` |
| JSON 解析失败 | 原始文本 | `None` |

### 5.2 领域 Agent 契约

所有领域 Agent **必须**：
- 实现 `ready` 属性（代理 `AgentService.ready`）
- 同步方法，异常内部捕获
- 不直接访问 `Config()`

### 5.3 LLMParser 契约

```python
class LLMParser(BaseParser):
    @property
    def ready: bool
    def parse(title, subtitle) -> ParserResult | None
    def parse_batch(titles) -> list[ParserResult | None]
```

- `ready=False`（Agent 未配置）时，`parse()` 和 `parse_batch()` 返回 `None`
- `parse_batch()` 内部调用 `MediaRecognizer.recognize_batch()`，使用 `BatchResult` 一次处理多条
- `_convert()` 将 `MediaResult` 映射为 `ParserResult`，包含 `end_season`/`end_episode`

## 6. 缓存策略

### 6.1 AgentService 对话缓存

- `lru_cache_with_ttl(ttl=300, maxsize=256)`
- 仅 `chat()` 启用，`structured_chat()` 不缓存（避免复杂 JSON 命中错误缓存）
- 键：`tuple(messages), system_prompt, temperature`

### 6.2 EpisodeMapper 映射缓存

- 实例级内存字典 `_blocks`
- 键：`tmdb_id`（合并季）/ `f"abs:{tmdb_id}"`（绝对集号）
- 进程存活期间有效

### 6.3 MediaService 识别缓存

- Redis / 内存缓存（`cacheman["media_info"]`）
- **防碰撞**：返回缓存前验证 `season/episode` 与当前解析结果匹配

## 7. 配置格式

```json
{
  "agent": {
    "enabled": true,
    "default_provider": "deepseek",
    "media_recognizer_enabled": true,
    "providers": {
      "deepseek": {
        "api_key": "sk-xxx",
        "api_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
      },
      "ollama": {
        "api_key": "",
        "api_url": "http://localhost:11434/v1",
        "model": "llama3.2"
      }
    }
  }
}
```

- `agent.enabled`：总开关，控制 AgentService 是否初始化 Provider
- `agent.media_recognizer_enabled`：控制 `MediaService._build_parser()` 是否选择 `LLMParser`
- 两者同时为 `true` 时，Parser 层才会使用 LLM

## 8. 扩展规范

### 8.1 新增 Provider

1. 继承 `BaseProvider`，实现 `chat()` 和 `is_available()`
2. 文件放入 `app/agent/providers/`
3. 在 `app/agent/config.py:get_provider()` 中添加构造逻辑
4. 无需修改 `AgentService`

### 8.2 新增领域 Agent

1. 文件放入 `app/agent/agents/`，从 `AgentService` 获取 Provider
2. 提示词放入 `app/agent/prompts/`
3. 实现 `ready` 属性
4. 在 `app/agent/agents/__init__.py` 和 `app/agent/__init__.py` 导出

### 8.3 新增 Parser

1. 继承 `BaseParser`，实现 `parse()` 和 `parse_batch()`
2. 文件放入 `app/media/parser/`
3. 在 `MediaService._build_parser()` 中添加选择逻辑

## 9. 已知限制

1. **identify() 的单条调用成本**：`MediaService.identify()` 在单条模式下使用 `LLMParser.parse()`，每次调用产生一次 LLM 请求。虽然 `AgentService.chat()` 有缓存（ttl=300），但首次识别的长尾延迟（通常 3-15 秒）仍需关注。
2. **identify_batch() 的 batch 收益**：`recognize_batch()` 使用 `BatchResult` 一次处理最多 20 条，相比单条调用大幅减少 API 请求次数。但 LLM 的 batch 响应时间随条目数增加而延长。
3. **索引器搜索的两阶段模型**：`ResultFilter.local_filter()` 调用 `MetaInfo()`（纯正则，无 LLM），`BatchIdentifier.identify()` 调用 `identify_batch()`（可选 LLM）。Agent 只介入阶段2，不影响阶段1的性能。
4. **无异步接口**：所有 Agent 方法为同步。若未来 RSS/搜索批次量极大，需考虑引入异步改造。

## 10. 测试覆盖

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_llm_parser.py` | `LLMParser` 接口契约、`ready` 降级、`_convert` 映射、`_map_type` |
| `tests/test_irregular_titles.py` | 正则解析器各种格式 |
| `tests/test_media_service_identify.py` | `identify()`/`identify_batch()`/`identify_files()` 流水线 |
