# ---- Build Stage ----
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY users_api/requirements.txt .
RUN grep -v "zenika-shared-schemas" requirements.txt > /tmp/req_public.txt \
    && pip wheel --no-cache-dir --wheel-dir /app/wheels -r /tmp/req_public.txt

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

# Installer uniquement les dépendances d'execution minimales
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt zenika-shared-schemas \
    && rm -rf /wheels

COPY users_api/ .

ENV PYTHONPATH=/app
ENV PORT=8000
ENV MCP_SIDECAR_URL=http://users_mcp:8000
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/users-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=users-api
ENV USE_IAM_AUTH=false
ENV CORS_ORIGINS=http://localhost:5173,http://localhost:80,http://localhost:8080
ENV FRONTEND_URL=http://localhost:5173
ENV SERVICE_TOKEN_TTL_MINUTES=90
EXPOSE 8000

# Création d'un utilisateur sans privilège
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
