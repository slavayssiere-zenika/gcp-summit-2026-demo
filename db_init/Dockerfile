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
FROM python:3.13-slim
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY db_init.py .

# Variables d'environnement par défaut (surchargées par le Cloud Run Job)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Utilisateur non-root (AGENTS.md §9.1)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Cloud Run Job : python3 -m db_init (AGENTS.md §9.3)
CMD ["python3", "-m", "db_init"]
