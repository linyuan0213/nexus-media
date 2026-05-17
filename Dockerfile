# NAS-Tools Docker 多阶段构建
# Stage 1: 编译前端
# Stage 2: 构建 Python 虚拟环境
# Stage 3: 运行时（Alpine + s6-overlay + nginx）

# ==================== Stage 1: 前端编译 ====================
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# 安装 pnpm
RUN npm install -g pnpm@10.28.2

# 复制 monorepo 配置文件（利用缓存层）
COPY web/frontend/package.json web/frontend/pnpm-lock.yaml web/frontend/pnpm-workspace.yaml ./
COPY web/frontend/tsconfig*.json web/frontend/turbo.json web/frontend/*.yaml ./
COPY web/frontend/scripts ./scripts
COPY web/frontend/internal ./internal
COPY web/frontend/packages ./packages

# 复制应用层 package.json
COPY web/frontend/apps/nas-tools/package.json ./apps/nas-tools/

# 安装依赖
RUN pnpm install --frozen-lockfile

# 复制前端源码并编译
COPY web/frontend/apps/nas-tools ./apps/nas-tools
RUN pnpm --filter @nas-tools/frontend run build

# ==================== Stage 2: Python 依赖构建 ====================
FROM python:3.11-alpine3.19 AS python-builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 安装编译依赖
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    openssl-dev \
    postgresql-dev \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY third_party ./third_party

# 创建虚拟环境并安装依赖
RUN uv venv .venv \
    && uv sync --frozen --no-cache

# ==================== Stage 3: 运行时 ====================
FROM python:3.11-alpine3.19

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 安装运行时系统依赖
RUN apk add --no-cache \
    nginx \
    curl \
    bash \
    sudo \
    su-exec \
    shadow \
    tzdata \
    wget \
    libxml2 \
    libxslt \
    libffi \
    openssl \
    postgresql-libs \
    && curl -sSL https://rclone.org/install.sh | bash \
    && ARCH=$(case "$(uname -m)" in x86_64) echo "amd64";; aarch64) echo "arm64";; esac) \
    && curl -sSL https://dl.min.io/client/mc/release/linux-${ARCH}/mc -o /usr/bin/mc \
    && chmod +x /usr/bin/mc \
    && rm -rf /var/cache/apk/* /tmp/*

# 添加 s6-overlay rootfs（内含 s6 服务配置）
COPY --chmod=755 docker/rootfs /

# 创建必要目录
RUN mkdir -p /var/log/nginx /var/run /usr/share/nginx/html /config

# 设置环境变量
ENV S6_SERVICES_GRACETIME=30000 \
    S6_KILL_GRACETIME=60000 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    S6_SYNC_DISKS=1 \
    HOME="/nt" \
    TERM="xterm" \
    LANG="C.UTF-8" \
    TZ="Asia/Shanghai" \
    NASTOOL_CONFIG="/config/config.yaml" \
    PS1="\u@\h:\w \$ " \
    PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple" \
    ALPINE_MIRROR="mirrors.ustc.edu.cn" \
    PUID=0 \
    PGID=0 \
    UMASK=000 \
    NT_PORT=3000 \
    WORKDIR="/nas-tools"

# 创建用户
RUN addgroup -S nt -g 911 \
    && adduser -S nt -G nt -h ${HOME} -s /bin/bash -u 911 \
    && mkdir -p ${WORKDIR} ${HOME} \
    && echo "nt ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers \
    && echo 'fs.inotify.max_user_watches=5242880' >> /etc/sysctl.conf \
    && echo 'fs.inotify.max_user_instances=5242880' >> /etc/sysctl.conf \
    && echo 'vm.overcommit_memory=1' >> /etc/sysctl.conf

WORKDIR ${WORKDIR}

# 复制应用代码
COPY --chown=nt:nt . ${WORKDIR}/

# 复制编译好的前端静态文件到 nginx 目录
COPY --from=frontend-builder --chown=nt:nt /build/apps/nas-tools/dist /usr/share/nginx/html

# 复制 Python 虚拟环境
COPY --from=python-builder --chown=nt:nt /app/.venv ${WORKDIR}/.venv

# 确保启动脚本可执行
RUN chmod +x \
    ${WORKDIR}/start-prod.sh \
    ${WORKDIR}/start-dev.sh \
    ${WORKDIR}/restart-server.sh \
    ${WORKDIR}/stop-server.sh

# 设置目录权限
RUN chown -R nt:nt /var/log/nginx /usr/share/nginx/html /config

# 健康检查（通过 nginx 代理到后端）
HEALTHCHECK --interval=30s --timeout=30s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

# 暴露端口：80（nginx）+ 3000（后端直连，可选）
EXPOSE 80 3000

# 挂载配置目录
VOLUME ["/config"]

# s6-overlay init
ENTRYPOINT ["/init"]
