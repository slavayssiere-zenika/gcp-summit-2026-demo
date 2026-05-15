# ---- Build Stage ----
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY items_api/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# zenika-shared-schemas : pull depuis Artifact Registry via token éphémère (BuildKit secret)
# Le token n'est JAMAIS persisté dans les layers Docker (--mount=type=secret)
ARG PYTHON_AR_REPO
RUN --mount=type=secret,id=ar_token \
    pip wheel --no-cache-dir --wheel-dir /app/wheels \
      --index-url "https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" \
      "zenika-shared-schemas"

# ---- Runtime Stage ----
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt zenika-shared-schemas \
    && rm -rf /wheels

COPY items_api/ .

ENV PYTHONPATH=/app
ENV PORT=8001
ENV MCP_SIDECAR_URL=http://items_mcp:8000
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/items-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=items-api
ENV USE_IAM_AUTH=false
ENV USERS_API_URL=http://users_api:8000
EXPOSE 8001

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--no-server-header"]
