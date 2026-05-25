# 贡献指南

感谢你对 Nexus Media 项目的关注！本指南将帮助你快速了解如何参与项目开发。

## 分支模型

采用简化 Git Flow，每个仓库（backend / frontend）独立管理：

| 分支 | 用途 | 保护策略 |
|------|------|----------|
| `master` | 稳定发布分支，仅接收 release 合并 | 禁止直接推送 |
| `dev` | 日常开发分支，所有功能提交至此 | 建议 PR 合并 |
| `release` | 预发布分支，从 dev 切出，仅做 bug 修复 | 禁止直接推送 |
| `feature/*` | 功能分支（可选），从 dev 切出 | 无 |

## 提交流程

1. **日常开发**：在 `dev` 分支直接提交或从 `dev` 切出 `feature/*` 分支开发，完成后合并回 `dev`。
2. **发布准备**：从 `dev` 切出 `release` 分支，进行最终测试和 bug 修复，禁止引入新功能。
3. **正式发布**：`release` 分支合并到 `master` 并打 tag，同时合并回 `dev` 保持同步。
4. **热修复**：从 `master` 切出 `hotfix/*`，修复后合并到 `master` 和 `dev`。

## 提交规范

- 使用 Conventional Commits 格式：`<type>: <中文描述>`
- 常用 type：`feat`、`fix`、`refactor`、`perf`、`test`、`docs`、`chore`
- 示例：`feat: 添加 SMB 存储后端支持`、`fix: 修复跨后端移动文件时的权限问题`

## 代码规范

- **所有 `import`/`from` 必须放在文件顶部**，严禁在函数/方法/类内部导入依赖
- 所有修改必须通过 **ruff** 和 **pyright** 检查
- 运行命令：
  ```bash
  uv run ruff check <文件>
  uv run pyright <文件>
  ```

## 本地开发

1. 安装依赖：`uv sync --dev`
2. 配置 `config/config.yaml`（最小配置见 `docs/development.md`）
3. 启动：`uv run python run.py`
4. 运行测试：`uv run pytest tests/ -v`

## PR 规范

- PR 标题遵循提交规范
- 确保 CI 通过（lint + typecheck + test）
- 大型变更请先开 issue 讨论

## 前后端协同

- 后端 (`backend/`) 和前端 (`frontend/`) 为两个独立 git 仓库
- API 变更时，后端先行提交并确保接口稳定，前端再对接
