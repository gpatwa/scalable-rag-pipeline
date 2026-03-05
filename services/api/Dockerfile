# services/api/Dockerfile
# Multi-stage build for smaller, more secure image

# --- Stage 1: Build dependencies ---
FROM python:3.10-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime image ---
FROM python:3.10-slim

# Security: Don't run as root
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 -d /app appuser

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Set ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the port uvicorn will run on
EXPOSE 8080

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/liveness')" || exit 1

# Command to run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
