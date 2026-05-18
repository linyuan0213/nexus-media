# NAS-Tools 后端 Dockerfile
# 纯后端构建，前端由独立服务提供

FROM python:3.11-alpine3.19 AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 编译依赖
RUN apk add --no-cache \
    gcc musl-dev libffi-dev libxml2-dev libxslt-dev openssl-dev postgresql-dev \
    && rm -rf /var/cache/apk/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY third_party ./third_party

RUN uv venv .venv \
    && uv sync --frozen --no-cache

# ==================== 运行时 ====================
FROM python:3.11-alpine3.19

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apk add --no-cache \
    nginx curl bash sudo su-exec shadow tzdata wget \
    libxml2 libxslt libffi openssl postgresql-libs \
    && curl -sSL https://rclone.org/install.sh | bash \
    && ARCH=$(case "$(uname -m)" in x86_64) echo "amd64";; aarch64) echo "arm64";; esac) \
    && curl -sSL https://dl.min.io/client/mc/release/linux-${ARCH}/mc -o /usr/bin/mc \
    && chmod +x /usr/bin/mc \
    && rm -rf /var/cache/apk/* /tmp/*

COPY --chmod=755 docker/rootfs /
RUN mkdir -p /var/log/nginx /var/run

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
    PUID=0 \
    PGID=0 \
    UMASK=000 \
    NT_PORT=3000 \
    WORKDIR="/nas-tools"

RUN addgroup -S nt -g 911 \
    && adduser -S nt -G nt -h ${HOME} -s /bin/bash -u 911 \
    && mkdir -p ${WORKDIR} ${HOME} \
    && echo "nt ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

WORKDIR ${WORKDIR}

COPY --chown=nt:nt . ${WORKDIR}/
COPY --from=builder --chown=nt:nt /app/.venv ${WORKDIR}/.venv

RUN chmod +x \
    ${WORKDIR}/start-prod.sh \
    ${WORKDIR}/start-dev.sh \
    ${WORKDIR}/restart-server.sh \
    ${WORKDIR}/stop-server.sh

HEALTHCHECK --interval=30s --timeout=30s --retries=3 \
    CMD wget -qO- http://localhost:3000/health || exit 1

EXPOSE 3000
VOLUME ["/config"]
ENTRYPOINT ["/init"]
