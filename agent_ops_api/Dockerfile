FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY agent_commons/ /agent_commons/
COPY agent_ops_api/pyproject.toml agent_ops_api/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

ARG PYTHON_AR_REPO
ENV PYTHON_AR_REPO=${PYTHON_AR_REPO}
ARG SHARED_VERSION
ENV SHARED_VERSION=${SHARED_VERSION}
RUN --mount=type=secret,id=ar_token \
    UV_EXTRA_INDEX_URL="https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" \
    uv add "zenika-shared-schemas${SHARED_VERSION:+==$SHARED_VERSION}"

COPY agent_ops_api/ .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV GEMINI_MODEL=gemini-3.1-flash-lite-preview
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/agent-ops-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=agent-ops
ENV USERS_API_URL=http://users_api:8000
ENV ITEMS_API_URL=http://items_api:8001
ENV COMPETENCIES_API_URL=http://competencies_api:8003
ENV CV_API_URL=http://cv_api:8004
ENV MISSIONS_API_URL=http://missions_api:8009
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV ANALYTICS_MCP_URL=http://analytics_mcp:8008
ENV USERS_MCP_URL=http://users_mcp:8000
ENV ITEMS_MCP_URL=http://items_mcp:8000
ENV COMPETENCIES_MCP_URL=http://competencies_mcp:8000
ENV CV_MCP_URL=http://cv_mcp:8000
ENV MISSIONS_MCP_URL=http://missions_mcp:8000
ENV DRIVE_MCP_URL=http://drive_mcp:8000
ENV PROMPTS_MCP_URL=http://prompts_mcp:8000
ENV MONITORING_MCP_URL=http://monitoring_mcp:8010
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
