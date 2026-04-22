# ---- Build Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .

ENV PYTHONPATH=/app
ENV GEMINI_MODEL=gemini-2.5-flash
ENV GEMINI_PRO_MODEL=gemini-2.5-pro
ENV GEMINI_EMBEDDING_MODEL=gemini-embedding-001
ENV PORT=8004
ENV MCP_SIDECAR_URL=http://cv_mcp:8000
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/cv-api
ENV APP_VERSION=dev
ENV USE_IAM_AUTH=false
ENV USERS_API_URL=http://users_api:8000
ENV COMPETENCIES_API_URL=http://competencies_api:8003
ENV ITEMS_API_URL=http://items_api:8001
ENV DRIVE_API_URL=http://drive_api:8080
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV MARKET_MCP_URL=http://market_mcp:8080
ENV PUBSUB_INVOKER_SA_EMAIL=sa-pubsub-invoker-dev@your-project.iam.gserviceaccount.com
ENV GCP_PROJECT_ID=your-gcp-project-id
EXPOSE 8004


RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--no-server-header"]
