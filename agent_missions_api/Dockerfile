FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY agent_commons/ /agent_commons/
COPY agent_missions_api/pyproject.toml agent_missions_api/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

ARG PYTHON_AR_REPO
ENV PYTHON_AR_REPO=${PYTHON_AR_REPO}
ARG SHARED_VERSION
ENV SHARED_VERSION=${SHARED_VERSION}
RUN --mount=type=secret,id=ar_token \
    UV_EXTRA_INDEX_URL="https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" \
    uv add "zenika-shared-schemas${SHARED_VERSION:+==$SHARED_VERSION}"

COPY agent_missions_api/ .

# ── Comportement applicatif (Level 1 — safe defaults) ─────────────────────────
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=none
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318

ENV OTEL_SERVICE_NAME=agent-missions-api
ENV ROOT_PATH=/agent-missions-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=agent-missions
ENV GEMINI_MODEL=gemini-3.1-flash-lite-preview
ENV GEMINI_MISSIONS_MODEL=gemini-3.1-flash-lite-preview
ENV ENABLE_OUTPUT_SCHEMA=false
ENV HITL_PENDING_TTL_SECONDS=1800
ENV HITL_RESPONSE_TTL_SECONDS=86400

# ── MCP Sidecars — internal, no JWT (Level 1) ─────────────────────────────────
ENV MISSIONS_MCP_URL=http://missions_mcp:8000
ENV CV_MCP_URL=http://cv_mcp:8000
ENV USERS_MCP_URL=http://users_mcp:8000
ENV COMPETENCIES_MCP_URL=http://competencies_mcp:8000

# ── Services support (Level 1) ─────────────────────────────────────────────────
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV ANALYTICS_MCP_URL=http://analytics_mcp:8080
ENV MONITORING_MCP_URL=http://monitoring_mcp:8010

# ── Infrastructure (Level 2 — JAMAIS de valeur réelle ici, injectée par Cloud Run)
# La valeur ci-dessous est le défaut local dev (DB 12 = missions)
# En GCP : injectée par Terraform via Cloud Run env
ENV REDIS_URL=redis://redis:6379/12

# ── Comportement applicatif GCP (Level 1 — surchargé par Cloud Run)
ENV USE_GCP_LOGGING=false
ENV GCP_PROJECT_ID=local

# ── Secrets (Level 3 — JAMAIS dans Dockerfile, injectés via Secret Manager)
# SECRET_KEY     → via secret_key_ref dans cr_agent_missions.tf
# GOOGLE_API_KEY → via secret_key_ref dans cr_agent_missions.tf

EXPOSE 8080

# Zéro-Trust Non-Root (Golden Rules §9.1)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Graceful Shutdown — pas de shell wrapper (Golden Rules §9.3)
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
