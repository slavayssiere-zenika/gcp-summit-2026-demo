# ---- Build Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY agent_api/requirements.txt .
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
COPY agent_api/requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY agent_api/ ./

ENV PYTHONPATH=/app
ENV USERS_API_URL=http://users_api:8000
ENV ITEMS_API_URL=http://items_api:8001

ENV PORT=8002
EXPOSE 8002

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
