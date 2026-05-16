# ---- Build Stage ----
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 1. Service dependencies
COPY agent_hr_api/requirements.txt .
RUN grep -v "zenika-shared-schemas" requirements.txt > /tmp/req_public.txt \
    && pip wheel --no-cache-dir --wheel-dir /app/wheels -r /tmp/req_public.txt


# 2. Shared package agent_commons (built as a wheel for clean installation)
COPY agent_commons/ /agent_commons/
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels /agent_commons/

# zenika-shared-schemas : pull depuis Artifact Registry via token éphémère (BuildKit secret)
# Le token n'est JAMAIS persisté dans les layers Docker (--mount=type=secret)
ARG PYTHON_AR_REPO
ENV PYTHON_AR_REPO=${PYTHON_AR_REPO}
ARG SHARED_VERSION
ENV SHARED_VERSION=${SHARED_VERSION}
RUN --mount=type=secret,id=ar_token \
    sh -c 'PIP_EXTRA_INDEX_URL="https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" pip wheel --no-cache-dir --wheel-dir /app/wheels "zenika-shared-schemas${SHARED_VERSION:+==$SHARED_VERSION}"'

# ---- Runtime Stage ----
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# Install service deps + agent_commons wheel in one pass
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt agent_commons zenika-shared-schemas \
    && rm -rf /wheels

# Copy service sources (context is repo root)
COPY agent_hr_api/ ./

ENV PYTHONPATH=/app
ENV GEMINI_MODEL=gemini-3.1-flash-lite-preview
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/agent-hr-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=agent-hr
ENV USERS_API_URL=http://users_api:8000
ENV ITEMS_API_URL=http://items_api:8001
ENV COMPETENCIES_API_URL=http://competencies_api:8003
ENV CV_API_URL=http://cv_api:8004
ENV MISSIONS_API_URL=http://missions_api:8009
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV ANALYTICS_MCP_URL=http://analytics_mcp:8080
# MCP Sidecars — internal, no JWT required on /mcp/tools and /mcp/call
ENV USERS_MCP_URL=http://users_mcp:8000
ENV ITEMS_MCP_URL=http://items_mcp:8000
ENV COMPETENCIES_MCP_URL=http://competencies_mcp:8000
ENV CV_MCP_URL=http://cv_mcp:8000
ENV MISSIONS_MCP_URL=http://missions_mcp:8000
ENV DRIVE_MCP_URL=http://drive_api:8080
ENV LOKI_MCP_URL=http://loki:3100/mcp
ENV MONITORING_MCP_URL=http://monitoring_mcp:8010
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
