# ---- Build Stage ----
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY items_api/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY shared/ /app/shared/
COPY items_api/ .

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
