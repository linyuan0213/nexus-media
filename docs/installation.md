# 安装指南

## Docker Compose 安装（推荐）

前后端分离部署，包含 Nexus Media 后端、前端 Web UI、Redis、OCR 和 Chrome 服务。

### 1. 创建 docker-compose.yml

```yaml
services:
  frontend:
    image: linyuan0213/nexus-media-web:latest
    ports:
      - 3000:8080
    restart: always
    container_name: nexus-media-web
    networks:
      - nexus-media-network
    depends_on:
      - backend

  backend:
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
    networks:
      - nexus-media-network
    healthcheck:
      test: "wget -qO- http://localhost:3000/health || exit 1"
      interval: 30s
      timeout: 30s
      retries: 3
      start_period: 40s
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    container_name: nexus-media-redis
    volumes:
      - ./config/redis_data:/data
      - ./config/redis.conf:/usr/local/etc/redis/redis.conf
    command: redis-server /usr/local/etc/redis/redis.conf
    restart: always
    networks:
      - nexus-media-network

  ocr:
    image: linyuan0213/nexus-media-ocr:latest
    container_name: nexus-media-ocr
    ports:
      - 9300:9300
    restart: always
    networks:
      - nexus-media-network

  chrome:
    image: linyuan0213/nexus-media-chrome:latest
    container_name: nexus-media-chrome
    shm_size: 2g
    environment:
      - VNC_PASSWORD=password
    volumes:
      - ./data:/var/lib/chromium/user_data
    ports:
      - 9850:9850
      - 6080:6080
    restart: always
    networks:
      - nexus-media-network

networks:
  nexus-media-network:
    driver: bridge
    name: nexus-media-network
```

### 2. 启动服务

```bash
docker compose up -d
```

### 3. 访问

- 前端 Web UI: http://localhost:3000
- 后端 API: http://localhost:3001

## 单独部署后端

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

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PUID` | 0 | 运行用户 UID |
| `PGID` | 0 | 运行用户 GID |
| `UMASK` | 000 | 文件权限掩码 |
| `NEXUS_PORT` | 3000 | 后端服务端口 |
| `TZ` | Asia/Shanghai | 时区 |

## 目录说明

| 容器路径 | 说明 |
|----------|------|
| `/config` | 配置文件、数据库、插件数据 |
| `/nexus-media` | 应用代码目录 |
| `/media` | 媒体目录（需自行映射） |

## 首次使用

1. 访问前端页面 http://localhost:3000
2. 默认账号密码：
   - 用户名: `admin`
   - 密码: `password`
3. **首次登录后必须修改默认密码**
4. 进入 **设置 > 基础设置 > 媒体** 配置 TMDB API Key（必须）
5. 进入 **设置 > 下载器** 添加下载器
6. 进入 **设置 > 媒体服务器** 添加 Emby/Jellyfin/Plex
7. 进入 **站点 > 站点维护** 添加 PT 站点
