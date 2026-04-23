# ---- Build Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY agent_router_api/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl apt-transport-https ca-certificates gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY agent_router_api/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY agent_router_api/ ./

ENV PYTHONPATH=/app
ENV GEMINI_MODEL=gemini-2.5-flash
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/api
ENV APP_VERSION=dev
ENV USERS_API_URL=http://users_api:8000
ENV AGENT_HR_API_URL=http://agent_hr_api:8080
ENV AGENT_OPS_API_URL=http://agent_ops_api:8080
ENV AGENT_MISSIONS_API_URL=http://agent_missions_api:8080
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV ANALYTICS_MCP_URL=http://analytics_mcp:8080
ENV MONITORING_MCP_URL=http://monitoring_mcp:8010
ENV REDIS_URL=redis://redis:6379/1
# SEC-F06 — Semantic Cache LLM
ENV SEMANTIC_CACHE_ENABLED=true
ENV SEMANTIC_CACHE_THRESHOLD=0.95
ENV SEMANTIC_CACHE_TTL=900
ENV GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
