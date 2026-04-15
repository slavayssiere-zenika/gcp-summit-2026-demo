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
    && apt-get install -y --no-install-recommends libpq5 curl apt-transport-https ca-certificates gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . ./

ENV PYTHONPATH=/app
ENV GEMINI_MODEL=gemini-2.5-flash
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/agent-hr-api
ENV APP_VERSION=dev
ENV USERS_API_URL=http://users_api:8000
ENV ITEMS_API_URL=http://items_api:8001
ENV COMPETENCIES_API_URL=http://competencies_api:8003
ENV CV_API_URL=http://cv_api:8004
ENV MISSIONS_API_URL=http://missions_api:8009
ENV PROMPTS_API_URL=http://prompts_api:8000
ENV MARKET_MCP_URL=http://market_mcp:8080
# MCP Sidecars — internal, no JWT required on /mcp/tools and /mcp/call
ENV USERS_MCP_URL=http://users_mcp:8000
ENV ITEMS_MCP_URL=http://items_mcp:8000
ENV COMPETENCIES_MCP_URL=http://competencies_mcp:8000
ENV CV_MCP_URL=http://cv_mcp:8000
ENV MISSIONS_MCP_URL=http://missions_mcp:8000
ENV DRIVE_MCP_URL=http://drive_api:8080
ENV LOKI_MCP_URL=http://loki:3100/mcp
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
