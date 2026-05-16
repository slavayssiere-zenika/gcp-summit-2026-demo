FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY drive_api/pyproject.toml drive_api/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

ARG PYTHON_AR_REPO
ENV PYTHON_AR_REPO=${PYTHON_AR_REPO}
ARG SHARED_VERSION
ENV SHARED_VERSION=${SHARED_VERSION}
RUN --mount=type=secret,id=ar_token \
    UV_EXTRA_INDEX_URL="https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" \
    uv add "zenika-shared-schemas${SHARED_VERSION:+==$SHARED_VERSION}"

COPY drive_api/ .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PORT=8006
ENV MCP_SIDECAR_URL=http://drive_mcp:8000
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/drive-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=drive-api
ENV USE_IAM_AUTH=false
ENV USERS_API_URL=http://users_api:8000
ENV PUBSUB_CV_IMPORT_TOPIC=zenika-cv-import-events-dev
ENV GCP_PROJECT_ID=your-gcp-project-id
ENV MAX_DRIVE_CV_IMPORT=10
ENV REDIS_URL=redis://redis:6379/6
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
