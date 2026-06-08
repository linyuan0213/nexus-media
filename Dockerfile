# Nexus Media 后端 Dockerfile
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
    nginx curl bash sudo su-exec shadow tzdata wget xz \
    libxml2 libxslt libffi openssl postgresql-libs \
    && rm -rf /var/cache/apk/* /tmp/*

ARG S6_OVERLAY_VERSION=3.2.3.0
RUN S6_ARCH=$(case "$(uname -m)" in x86_64) echo "x86_64";; aarch64) echo "aarch64";; esac) \
    && curl -sSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" | tar -Jxpf - -C / \
    && curl -sSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" | tar -Jxpf - -C / \
    && curl -sSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-symlinks-noarch.tar.xz" | tar -Jxpf - -C / \
    && curl -sSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-symlinks-arch.tar.xz" | tar -Jxpf - -C /

COPY --chmod=755 docker/rootfs /
RUN mkdir -p /var/log/nginx /var/run

ENV S6_SERVICES_GRACETIME=30000 \
    S6_KILL_GRACETIME=60000 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    HOME="/nexus" \
    TERM="xterm" \
    LANG="C.UTF-8" \
    TZ="Asia/Shanghai" \
    NEXUS_MEDIA_CONFIG="/config/config.yaml" \
    PS1="\u@\h:\w \$ " \
    PUID=0 \
    PGID=0 \
    UMASK=000 \
    NEXUS_PORT=3000 \
    WORKDIR="/nexus-media"

RUN addgroup -S nexus -g 911 \
    && adduser -S nexus -G nexus -h ${HOME} -s /bin/bash -u 911 \
    && mkdir -p ${WORKDIR} ${HOME} /config/logs \
    && echo "nexus ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

WORKDIR ${WORKDIR}

COPY --chown=nexus:nexus . ${WORKDIR}/
COPY --from=builder --chown=nexus:nexus /app/.venv ${WORKDIR}/.venv

RUN chmod +x \
    ${WORKDIR}/start-prod.sh \
    ${WORKDIR}/start-dev.sh \
    ${WORKDIR}/restart-server.sh \
    ${WORKDIR}/stop-server.sh

HEALTHCHECK --interval=30s --timeout=30s --retries=3 \
    CMD wget -qO- http://localhost:80/health || exit 1

EXPOSE 3000
VOLUME ["/config"]
ENTRYPOINT ["/init"]
