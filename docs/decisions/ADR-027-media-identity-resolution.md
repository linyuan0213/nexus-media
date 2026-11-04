# ADR-027：媒体身份统一解析

## 背景

媒体身份模型（`MEDIA_IDENTITY` + `MEDIA_EXTERNAL_REF`）最初只覆盖新的元数据/订阅链路；
搜索、下载、转移、生命周期等旧链路各自复制或兜底生成 `identity_id`，出现了：

- `content_id:*` / `local:*` 影子身份
- 同一作品多个规范身份
- 生命周期任务数量虚高
- 搜索结果、下载历史、转移历史身份为空

## 决策

### 1. 唯一解析入口 `IdentityResolver`

所有需要写入以下表的链路必须通过 `app/services/identity_resolver.py`：

- `SEARCH_RESULT_INFO`
- `DOWNLOAD_HISTORY`
- `TRANSFER_HISTORY`
- `MEDIA_LIFECYCLE`
- `MEDIASYNC_ITEMS`
- `MEDIA_IDENTITY` / `MEDIA_EXTERNAL_REF` 的普通业务写入

### 2. 解析顺序

```text
显式 IDENTITY_ID（合法的规范 ID 或 provider:external 影子）
→ MEDIA_EXTERNAL_REF（provider + external_id + scope）
→ anchor provider/external
→ 标题 + 年份 + 类型族（anime 与 tv 视为同族）
→ 有 anchor 时创建规范身份
→ 仅特定链路允许 local 兜底
```

- `anime` 与 `tv` 在外部引用唯一键上统一为 `tv`。
- 同一外部引用在不同 scope（default / season=N）下回退到同一身份。

### 3. 无 anchor 策略

| 场景 | 策略 |
|---|---|
| 搜索结果无 anchor | `IDENTITY_ID` 保持空，不允许标题猜测 |
| 下载/转移/生命周期无 anchor | 先按标题匹配已有身份；仍无则允许 `local:*` 兜底 |
| `MEDIASYNC_ITEMS` 无 anchor/番号 | 保持空，允许后续元数据识别补全 |

`local:*` 只用于跟踪历史任务，不代表外部 provider 身份，不进入 `MEDIA_IDENTITY`。

### 4. 写入校验

- 订阅创建：有 anchor 时必须得到规范 `IDENTITY_ID`，否则拒绝写入。
- 媒体库同步：优先 TMDB/IMDB、标题番号，解析不到则保持空。
- MetadataService：使用同一 `IdentityResolver`，元数据策略/快照逻辑保留在服务层。

### 5. CI / 数据审计

- `tests/unit/test_identity_integrity.py`：校验 anchor 解析不生成影子身份、同作品单身份、搜索不本地兜底。
- `scripts/check_identity_integrity.py` / `just identity-check`：检查
  - `local:*` / `content_id:*` 生命周期影子身份
  - 同标题/年份/类型多身份
  - 下载/转移/生命周期/订阅空身份

失败条件为上述项非零；搜索和媒体库同步的空身份属于允许空值，报告中单列。

## 历史数据

- `scripts/backfill_identity_ids.py`
- `scripts/backfill_media_sync_identity.py`
- `scripts/consolidate_lifecycle_identities.py`
- `scripts/merge_duplicate_ref_identities.py`
- `scripts/merge_local_identities.py`

均支持/建议先 dry-run，再执行 apply。

## 影响

- 运行时不再产生新的影子身份。
- 生命周期、下载、转移、订阅使用同一规范 ID。
- 无 anchor 的搜索结果和无法识别的媒体库条目允许为空，必须由后续识别补全，禁止默认猜测。
