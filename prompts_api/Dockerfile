# Stage 1: Build Python dependencies
FROM python:3.11-slim as py-builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Node setup and promptfoo installation
FROM node:20-slim as node-builder
ENV NPM_CONFIG_PREFIX=/opt/promptfoo-env
# Using npm install globally for promptfoo
RUN npm install -g promptfoo

# Stage 3: Final runtime image
FROM python:3.11-slim
WORKDIR /app

# Install minimal runtime dependencies (PostgreSQL client lib) and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy promptfoo globally installed files and symlinks from node-builder
COPY --from=node-builder /opt/promptfoo-env /opt/promptfoo-env
ENV PATH="/opt/promptfoo-env/bin:${PATH}"

# Install Python wheels
COPY --from=py-builder /app/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .
ENV PYTHONPATH=/app

ENV PORT=8000
EXPOSE 8000

# Securiser l'exécution
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
