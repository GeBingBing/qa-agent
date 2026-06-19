# kb-qa-agent backend — 多阶段镜像
# 阶段 1：用 uv 把项目依赖安装到 /opt/venv
# 阶段 2：runtime，仅带 .venv + 源码

FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 装 uv（速度比 pip 快很多；与项目 README 一致）
RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /build

# 先复制依赖元数据，最大化缓存命中
COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --extra eval || uv sync --no-dev --extra eval

# ----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/backend

# 系统层依赖（onnxruntime / cryptography 偶尔需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY backend ./backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "kb_qa_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
