# Nexus Media Docker 部署

## 镜像特点

- 基于 Alpine，镜像体积小
- 支持 amd64 / arm64 架构
- 非 root 用户运行（nexus:nexus）
- s6-overlay 进程管理，支持优雅退出
- 数据库迁移在启动时自动执行（alembic upgrade head）

## 快速开始

推荐使用项目根目录的 `docker-compose.yml` 完整部署：

```bash
docker compose up -d
```

MySQL 版本：

```bash
docker compose -f docker-compose.mysql.yml up -d
```

## 单独部署后端

**docker cli**

```bash
docker run -d \
  --name nexus-media \
  --hostname nexus-media \
  -p 3001:3000 \
  -v $(pwd)/config:/config \
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
      - ./config:/config
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

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PUID` | 0 | 运行用户 UID |
| `PGID` | 0 | 运行用户 GID |
| `UMASK` | 000 | 文件权限掩码 |
| `NEXUS_PORT` | 3000 | 服务端口 |
| `NEXUS_MEDIA_CONFIG` | — | 配置文件路径（可选，默认自动发现） |
| `LOG_FORMAT` | — | 设为 `json` 输出 ELK 兼容日志 |
| `TZ` | Asia/Shanghai | 时区 |

### 数据库环境变量（可选）

以下变量仅在需要使用外部数据库时设置：

| 变量 | 说明 |
|------|------|
| `DB_TYPE` | 数据库类型：`sqlite` / `mysql` / `postgresql` |
| `DB_HOST` | 数据库地址 |
| `DB_PORT` | 数据库端口 |
| `DB_USERNAME` | 数据库用户名 |
| `DB_PASSWORD` | 数据库密码 |
| `DB_NAME` | 数据库名称 |

## PUID / PGID 说明

- 若同时使用 Emby / Jellyfin / Plex / qBittorrent 等 Docker 镜像，建议保持 PUID / PGID 一致
- 在宿主机上执行 `id -u` 和 `id -g` 获取对应值
