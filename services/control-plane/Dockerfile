# services/control-plane/Dockerfile
# Multi-stage build for the control plane service.
# Fully independent — no imports from services/api/.

# --- Stage 1: Build dependencies ---
FROM python:3.10-slim AS builder

WORKDIR /build

COPY services/control-plane/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime image ---
FROM python:3.10-slim

RUN groupadd -r appuser && useradd -r -g appuser -u 1000 -d /app appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEPLOYMENT_MODE=control_plane

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy control plane service
COPY services/control-plane/ /app/

# Copy Chat UI static files (served by control plane)
COPY services/api/static /app/static

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health/liveness')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
