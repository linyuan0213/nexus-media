# Nexus Media 后端 Dockerfile
# 纯后端构建，前端由独立服务提供

FROM python:3.14-slim-trixie AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 编译依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc libffi-dev libxml2-dev libxslt1-dev libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /nexus-media
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY third_party ./third_party
COPY alembic ./alembic
COPY alembic.ini run.py start-prod.sh start-dev.sh restart-server.sh stop-server.sh ./

RUN uv venv .venv \
    && uv sync --frozen --no-cache --no-editable --no-install-project

# ==================== 运行时 ====================
FROM python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    nginx curl bash sudo tzdata wget xz-utils netcat-openbsd \
    libxml2 libxslt1.1 libffi8 libssl3 libpq5 \
    && rm -rf /var/lib/apt/lists/* /tmp/*

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

RUN groupadd -r -g 911 nexus \
    && useradd -r -g nexus -d ${HOME} -s /bin/bash -u 911 nexus \
    && mkdir -p ${WORKDIR} ${HOME} /config/logs \
    && echo "nexus ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

WORKDIR ${WORKDIR}

COPY --chown=nexus:nexus . ${WORKDIR}/
COPY --from=builder --chown=nexus:nexus /nexus-media/.venv ${WORKDIR}/.venv

RUN chmod +x \
    ${WORKDIR}/start-prod.sh \
    ${WORKDIR}/start-dev.sh \
    ${WORKDIR}/restart-server.sh \
    ${WORKDIR}/stop-server.sh

HEALTHCHECK --interval=30s --timeout=30s --retries=3 \
    CMD wget -qO- http://localhost:8080/health || exit 1

EXPOSE 3000
VOLUME ["/config"]
ENTRYPOINT ["/init"]
