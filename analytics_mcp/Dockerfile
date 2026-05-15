# ---- Build Stage ----
FROM python:3.13-slim AS builder

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY analytics_mcp/requirements.txt .
RUN grep -v "zenika-shared-schemas" requirements.txt > /tmp/req_public.txt \
    && pip wheel --no-cache-dir --wheel-dir /app/wheels -r /tmp/req_public.txt

# zenika-shared-schemas : pull depuis Artifact Registry via token éphémère (BuildKit secret)
# Le token n'est JAMAIS persisté dans les layers Docker (--mount=type=secret)
ARG PYTHON_AR_REPO
RUN --mount=type=secret,id=ar_token \
    pip wheel --no-cache-dir --wheel-dir /app/wheels \
      --index-url "https://oauth2accesstoken:$(cat /run/secrets/ar_token)@${PYTHON_AR_REPO}/simple/" \
      "zenika-shared-schemas"

# ---- Runtime Stage ----
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt zenika-shared-schemas \
    && rm -rf /wheels

COPY analytics_mcp/ .

ENV PYTHONPATH=/app
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/analytics-mcp
ENV APP_VERSION=dev
ENV ENVIRONMENT=dev
EXPOSE 8080

RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Exécute l'application FastAPI wrapper
CMD ["python3", "mcp_app.py"]
