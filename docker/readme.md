# Nexus Media Docker 部署

## 镜像特点

- 基于 Alpine，镜像体积小
- 支持 amd64 / arm64 架构
- 非 root 用户运行（nexus:nexus）
- s6-overlay 进程管理，支持优雅退出
- 数据库迁移在启动时自动执行（alembic upgrade head）

## 快速开始

项目根目录的 `docker-compose.yml` 提供三种部署模式，通过 `--profile` 切换。

默认执行 `docker compose up -d` 即为基础 MySQL 模式，其余模式需显式指定 `--profile`：

### 模式一：基础模式（默认）

包含前端、后端、Redis 和数据库（默认 MySQL，也可切换为 PostgreSQL）。

**MySQL**

```bash
docker compose --profile basic-mysql up -d
```

**PostgreSQL**

```bash
docker compose --profile basic-postgresql up -d
```

### 模式二：完整模式

在基础模式之上增加 OCR 和 Chrome 组件。

**MySQL**

```bash
docker compose --profile full-mysql up -d
```

**PostgreSQL**

```bash
docker compose --profile full-postgresql up -d
```

### 模式三：仅前后端

只启动前端和后端，后端使用 SQLite，无需 Redis 和数据库。

```bash
docker compose --profile app-only up -d
```

## 单独部署后端

**docker cli**

```bash
docker run -d \
  --name nexus-media \
  --hostname nexus-media \
  -p 3001:3000 \
  -v $(pwd)/data:/data \
  -v /你的媒体目录:/media \
  -e PUID=0 \
  -e PGID=0 \
  -e UMASK=000 \
  linyuan0213/nexus-media:latest
```

**docker-compose**

```yaml
services:
  nexus-media:
    image: linyuan0213/nexus-media:latest
    ports:
      - 3001:3000
    volumes:
      - ./data:/data
      - /你的媒体目录:/media
    environment:
      - PUID=0
      - PGID=0
      - UMASK=000
      - NEXUS_PORT=3000
    restart: always
    hostname: nexus-media
    container_name: nexus-media
```

## 环境变量

环境变量优先级：`环境变量 > .env > config.yaml`。除 Docker 镜像专用变量外，其余变量对应 `src/app/core/settings.py` 中的配置节点，使用 `__` 作为嵌套分隔符，例如 `APP__WEB_HOST`、`DATABASE__TYPE`、`REDIS__HOST`。

### Docker 镜像专用变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PUID` | 0 | 运行用户 UID |
| `PGID` | 0 | 运行用户 GID |
| `UMASK` | 000 | 文件权限掩码 |
| `NEXUS_PORT` | 3000 | 容器内部服务端口 |
| `SKIP_MIGRATION` | false | 设为 `true` 跳过启动时数据库迁移 |
| `TZ` | Asia/Shanghai | 时区 |

### 前后端配置变量（`app` 节点）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP__WEB_HOST` | :: | Web 监听地址 |
| `APP__WEB_PORT` | 3000 | Web 监听端口 |
| `APP__LOGIN_USER` | admin | 默认登录用户名 |
| `APP__LOGIN_PASSWORD` | password | 默认登录密码 |
| `APP__TMDB_DOMAIN` | api.themoviedb.org | TMDB API 域名 |

### 数据库配置变量（`database` 节点）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE__TYPE` | sqlite | 数据库类型：`sqlite` / `mysql` / `postgresql` |
| `DATABASE__HOST` | localhost | 数据库地址 |
| `DATABASE__PORT` | 0 | 数据库端口 |
| `DATABASE__USERNAME` | — | 数据库用户名 |
| `DATABASE__PASSWORD` | — | 数据库密码 |
| `DATABASE__DATABASE` | nas_tools | 数据库名称 |

### Redis 配置变量（`redis` 节点）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS__HOST` | 127.0.0.1 | Redis 地址 |
| `REDIS__PORT` | 6379 | Redis 端口 |
| `REDIS__PASSWORD` | — | Redis 密码 |
| `REDIS__DB` | 0 | Redis 数据库索引 |

### 其他常用变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NEXUS_MEDIA_CONFIG` | — | 配置文件路径（可选，默认自动发现） |
| `NEXUS_MEDIA_DATA` | — | 数据目录路径（可选，默认 `./data`） |
| `LOG__FORMAT` | text | 设为 `json` 输出 ELK 兼容日志 |

## PUID / PGID 说明

- 若同时使用 Emby / Jellyfin / Plex / qBittorrent 等 Docker 镜像，建议保持 PUID / PGID 一致
- 在宿主机上执行 `id -u` 和 `id -g` 获取对应值
