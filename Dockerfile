# AIOW 生产 Dockerfile - 多阶段构建
# Stage 1: builder - 安装依赖到独立 venv
# Stage 2: runtime - 精简运行时镜像

ARG PYTHON_VERSION=3.12.7-slim

# ===== Builder =====
FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 系统依赖（构建期需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖到独立目录（便于运行时镜像只复制 venv）
COPY backend/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ===== Runtime =====
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PYTHONPATH=/app

# 运行时系统依赖（psycopg2 需要 libpq，bcrypt 不需要额外）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r aiow && useradd -r -g aiow -d /app -s /usr/sbin/nologin aiow

# 复制 venv
COPY --from=builder /opt/venv /opt/venv

# 复制应用代码 + 部署配置
WORKDIR /app
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/scripts ./scripts
COPY docker/gunicorn_conf.py ./docker/gunicorn_conf.py
COPY docker/nginx.conf ./docker/nginx.conf

# 运行时数据/日志目录
RUN mkdir -p /app/logs /app/data && chown -R aiow:aiow /app

USER aiow

EXPOSE 8000

# 健康检查（K8s/Docker 的 healthcheck）
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# tini 作为 PID 1 处理信号转发，避免僵尸进程
ENTRYPOINT ["/usr/bin/tini", "--"]

# Gunicorn + uvicorn workers
CMD ["gunicorn", "app.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--access-logformat", "%(h)s %(l)t %(s)s %(b)s %(L)s", \
     "--config", "/app/docker/gunicorn_conf.py"]
