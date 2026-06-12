# ============================================================
# Production Dockerfile — Multi-stage, < 500 MB, non-root
# ============================================================

# Stage 1: Builder — cài dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Cài vào /install để copy sang runtime stage dễ dàng
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Runtime — chỉ có những gì cần chạy
FROM python:3.11-slim AS runtime

# Non-root user cho security
RUN groupadd -r agent && useradd -r -g agent -d /app -s /sbin/nologin agent

WORKDIR /app

# Copy packages từ builder vào system Python path
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY utils/ ./utils/

# Set ownership
RUN chown -R agent:agent /app

USER agent

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check — platform dùng để verify container healthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Shell form để $PORT được expand từ env var (Railway inject PORT tự động)
CMD sh -c "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
