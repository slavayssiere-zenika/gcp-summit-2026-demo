# ─────────────────────────────────────────────────────────────────────────────
# DB Init — Cloud Run Job Image
# Initialise les bases de données AlloyDB et octroie les permissions IAM.
# Golden Rules :
#   - Multi-stage build (AGENTS.md §9.2)
#   - USER non-root (AGENTS.md §9.1)
#   - CMD sans shell wrapper (AGENTS.md §9.3)
#   - python3, jamais python (AGENTS.md §1.9)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1 : Build (compilation des wheels) ─────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# asyncpg nécessite gcc pour la compilation de ses extensions C
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# ── Stage 2 : Runtime (image finale légère) ───────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Pas de libpq5 nécessaire : asyncpg utilise son propre driver pure-Python/C
COPY --from=builder /app/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY db_init.py .

# Variables d'environnement par défaut (surchargées par le Cloud Run Job)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Utilisateur non-root (AGENTS.md §9.1)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Cloud Run Job : python3 -m db_init (AGENTS.md §9.3)
CMD ["python3", "-m", "db_init"]
