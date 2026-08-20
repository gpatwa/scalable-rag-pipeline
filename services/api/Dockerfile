# services/api/Dockerfile
# Standalone support/RAG API image. Product web apps are built and deployed
# independently from apps/support-web and apps/analytics-web.

# ── Stage 1: Python deps ─────────────────────────────────────────────
FROM python:3.10-slim AS python-builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.10-slim

# Security: don't run as root
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 -d /app appuser

# Prevent .pyc + buffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Python deps
COPY --from=python-builder /install /usr/local

# App source
COPY . .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/liveness')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
