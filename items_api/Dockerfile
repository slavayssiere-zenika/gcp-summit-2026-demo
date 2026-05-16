FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY items_api/pyproject.toml items_api/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

ARG PYTHON_AR_REPO
ENV PYTHON_AR_REPO=${PYTHON_AR_REPO}
ARG SHARED_VERSION
ENV SHARED_VERSION=${SHARED_VERSION}
RUN --mount=type=secret,id=ar_token \
    UV_EXTRA_INDEX_URL="https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" \
    uv add "zenika-shared-schemas${SHARED_VERSION:+==$SHARED_VERSION}"

COPY items_api/ .

ENV PATH="/app/.venv/bin:$PATH"
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
