# services/data-plane/Dockerfile
# Multi-stage build for the data plane service.
# Copies both data-plane/ and api/app/ (shared code: agents, clients, cache, memory).

# --- Stage 1: Build dependencies ---
FROM python:3.10-slim AS builder

WORKDIR /build

# Data plane uses the same base requirements as the monolith API
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime image ---
FROM python:3.10-slim

RUN groupadd -r appuser && useradd -r -g appuser -u 1000 -d /app appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEPLOYMENT_MODE=data_plane \
    SINGLE_TENANT_MODE=true

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy shared code from the monolith (agents, clients, cache, memory)
COPY services/api/app /app/services/api/app

# Copy data plane service
COPY services/data-plane/ /app/services/data-plane/

# Set working directory to data-plane service root
WORKDIR /app/services/data-plane

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/liveness')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
