# syntax=docker/dockerfile:1.9
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── builder ─────────────────────────────────────────────────────────────────
FROM base AS builder

RUN pip install hatchling

COPY pyproject.toml ./
RUN pip install --prefix=/install \
    "anthropic>=0.40.0" \
    "mcp>=1.0.0" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.10.0" \
    "python-dotenv>=1.0.0" \
    "httpx>=0.28.0"

# ── runtime ─────────────────────────────────────────────────────────────────
FROM base AS runtime

# Create non-root user
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

COPY --from=builder /install /usr/local
COPY src/ ./src/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
