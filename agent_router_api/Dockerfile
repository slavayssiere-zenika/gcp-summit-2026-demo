# ---- Build Stage ----
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY agent_router_api/requirements.txt .
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

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt agent_commons zenika-shared-schemas \
    && rm -rf /wheels

COPY agent_router_api/ ./

ENV PYTHONPATH=/app
ENV GEMINI_MODEL=gemini-3.1-flash-lite-preview
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/api
ENV APP_VERSION=dev
ENV SERVICE_NAME=agent-router
ENV USERS_API_URL=http://users_api:8000
ENV AGENT_HR_API_URL=http://agent_hr_api:8080
ENV AGENT_OPS_API_URL=http://agent_ops_api:8080
ENV AGENT_MISSIONS_API_URL=http://agent_missions_api:8080
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV ANALYTICS_MCP_URL=http://analytics_mcp:8080
ENV MONITORING_MCP_URL=http://monitoring_mcp:8010
ENV REDIS_URL=redis://redis:6379/2
# SEC-F06 — Semantic Cache LLM
ENV SEMANTIC_CACHE_ENABLED=true
ENV SEMANTIC_CACHE_THRESHOLD=0.95
ENV SEMANTIC_CACHE_TTL=900
ENV GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
