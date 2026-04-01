# Stage 1: Build Python dependencies
FROM python:3.11-slim as py-builder
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev gcc
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Node setup and promptfoo installation
FROM node:20-slim as node-builder
ENV NPM_CONFIG_PREFIX=/opt/promptfoo-env
RUN npm install -g promptfoo

# Stage 3: Final runtime image
FROM python:3.11-slim
WORKDIR /app

# Install runtime dependencies (PostgreSQL client libs) and Node.js
RUN apt-get update && apt-get install -y libpq-dev curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy promptfoo globally installed files and symlinks from node-builder
COPY --from=node-builder /opt/promptfoo-env /opt/promptfoo-env
ENV PATH="/opt/promptfoo-env/bin:${PATH}"

# Install Python wheels
COPY --from=py-builder /app/wheels /wheels
COPY --from=py-builder /app/requirements.txt .
RUN pip install --no-cache /wheels/*

COPY . .
ENV PYTHONPATH=/app

ENV PORT=8000
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port $PORT"]
