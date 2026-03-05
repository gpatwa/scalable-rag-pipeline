# services/sandbox/Dockerfile

# 1. Use minimal base image to reduce attack surface
FROM python:3.10-slim

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Create a non-root user (Security Best Practice)
RUN useradd -m -u 1000 sandbox_user

# 4. Install dependencies
WORKDIR /app
COPY runner.py .
RUN pip install flask

# 5. Security Limits (Applied inside container, enforced by K8s limits.yaml)
# We limit the user process capabilities
USER sandbox_user

# 6. Network Policy
# Note: In K8s, we will apply a NetworkPolicy to deny all Egress traffic
# except returning the HTTP response to the API.

# 7. Entrypoint
EXPOSE 8080
CMD ["python", "runner.py"]