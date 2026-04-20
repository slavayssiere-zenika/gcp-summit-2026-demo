# ---- Build Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 1. Service dependencies
COPY agent_missions_api/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# 2. Shared package agent_commons
COPY agent_commons/ /agent_commons/
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels /agent_commons/

# ---- Runtime Stage ----
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY agent_missions_api/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt agent_commons \
    && rm -rf /wheels

# Copy service sources (context is repo root)
COPY agent_missions_api/ ./

# ── Comportement applicatif (Level 1 — safe defaults) ─────────────────────────
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=none
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318

ENV OTEL_SERVICE_NAME=agent-missions-api
ENV ROOT_PATH=/agent-missions-api
ENV APP_VERSION=dev
ENV GEMINI_MODEL=gemini-2.5-flash

# ── MCP Sidecars — internal, no JWT (Level 1) ─────────────────────────────────
ENV MISSIONS_MCP_URL=http://missions_mcp:8000
ENV CV_MCP_URL=http://cv_mcp:8000
ENV USERS_MCP_URL=http://users_mcp:8000
ENV COMPETENCIES_MCP_URL=http://competencies_mcp:8000

# ── Services support (Level 1) ─────────────────────────────────────────────────
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV MARKET_MCP_URL=http://market_mcp:8080

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
