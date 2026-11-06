# ADR-028 元数据网关：统一入口与请求复用

## 状态
设计阶段

## 背景
元数据调用分散在 API、搜索、订阅、下载、转移、刮削和消息层。同一个 provider/ref 在不同阶段重复查询，缓存键和权限策略不一致，provider 限流容易被绕过。

## 决策
1. 新增 `MetadataGateway` 作为唯一元数据入口，现有 `MetadataService` 作为内部实现。
2. 所有读取使用 `MetadataContext`，承载用户、权限、画像、策略、用途和语言。
3. 所有调用返回 `MetadataEnvelope`，包含 identity、snapshot、refs、缓存和降级信息。
4. 网关负责 L1/L2 缓存、singleflight、provider 限流、stale-while-revalidate 和指标。
5. 业务流程只消费 envelope 或 snapshot_id，不再自行调用 provider 或重复 lookup。
6. `metadata_registry.get_provider` 仅允许网关内部和管理端 descriptor 使用。

## 迁移
- 第一阶段：网关模型和门面，旧调用保持兼容。
- 第二阶段：搜索识别、订阅、详情 API 迁移。
- 第三阶段：下载、转移、刮削、消息复用 snapshot。
- 第四阶段：移除旧入口和业务层 provider 调用。

## 验收
- 同一 ref 在单次链路只调用 provider 一次。
- 并发相同 ref 只产生一次 provider 请求。
- 限流或熔断时优先返回 stale 或延迟，不穿透 provider。
- 电影、电视剧、动漫、插件编号内容矩阵测试通过。
