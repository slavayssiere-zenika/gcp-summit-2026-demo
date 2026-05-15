# Stage 1: Build Python dependencies
FROM python:3.13-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY prompts_api/requirements.txt .
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

# Stage 2: Node setup and promptfoo installation
FROM node:22-slim AS node-builder
ENV NPM_CONFIG_PREFIX=/opt/promptfoo-env
# Using npm install globally for promptfoo
RUN npm install -g promptfoo

# Stage 3: Final runtime image
FROM python:3.13-slim
WORKDIR /app

# Install minimal runtime dependencies (PostgreSQL client lib) and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy promptfoo globally installed files and symlinks from node-builder
COPY --from=node-builder /opt/promptfoo-env /opt/promptfoo-env
ENV PATH="/opt/promptfoo-env/bin:${PATH}"

# Install Python wheels
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt zenika-shared-schemas \
    && rm -rf /wheels

COPY prompts_api/ .
ENV PYTHONPATH=/app

ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRACE_EXPORTER=grpc
ENV ROOT_PATH=/prompts-api
ENV APP_VERSION=dev
ENV SERVICE_NAME=prompts-api
ENV USE_IAM_AUTH=false
EXPOSE 8000

# Securiser l'exécution
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
