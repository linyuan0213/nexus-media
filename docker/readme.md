## 镜像特点

- 基于 Alpine，镜像体积小
- 支持 amd64/arm64 架构
- 非 root 用户运行，降低权限风险
- 支持 umask 文件权限掩码设置

## 快速开始

推荐使用项目根目录的 `docker-compose.yml` 完整部署（包含前端、后端、Redis、OCR、Chrome）。

```bash
docker compose up -d
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
| `TZ` | Asia/Shanghai | 时区 |

## PUID/PGID 说明

- 若同时使用 Emby/Jellyfin/Plex/qBittorrent 等 Docker 镜像，建议保持 PUID/PGID 一致
- 在宿主机上执行 `id -u` 和 `id -g` 获取对应值
- PUID=0 PGID=0 为 root 用户，媒体文件所有者非 root 时不建议设置

## 硬链接映射

参考下图（由 imogel@telegram 制作）：

![如何映射](volume.png)
