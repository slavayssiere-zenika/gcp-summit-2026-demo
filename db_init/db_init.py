#!/usr/bin/env python3
"""
DB Init — Zenika Console Agent
================================
Initialise les bases de données AlloyDB et octroie les permissions IAM
aux service accounts de chaque microservice.

Ce script est exécuté dans un Cloud Run Job dédié (image: db_init).
Il est conçu pour être idempotent : relancer le job sur un environnement
déjà initialisé ne provoquera aucune erreur.

Variables d'environnement requises :
  ROOT_DB_URL  — Mot de passe root AlloyDB (depuis Secret Manager)
  DB_IP        — IP privée de l'instance AlloyDB primary
  PROJECT_ID   — GCP Project ID
  ENV_VAL      — Nom de l'environnement (dev, uat, prd)
  SA_SUFFIX    — Suffixe hex du random_id.sa_suffix Terraform
  ADMIN_USER   — Email de l'admin humain à provisionner (optionnel)
"""

import os
import sys
import asyncio
import urllib.parse

import asyncpg


def get_env(key: str, required: bool = True) -> str:
    """Lit une variable d'environnement; lève une erreur si obligatoire et absente."""
    val = os.environ.get(key, "")
    if required and not val:
        print(f"[DB INIT] FATAL: Variable d'environnement '{key}' manquante.", flush=True)
        sys.exit(1)
    return val


# ─────────────────────────────────────────────────────────────────────────────
# Liste des microservices avec leur propre base de données AlloyDB
# ─────────────────────────────────────────────────────────────────────────────
SERVICES = ["users", "items", "competencies", "cv", "prompts", "drive", "missions"]


async def grant_permissions(conn: asyncpg.Connection, user: str, db_name: str, label: str = "service") -> None:
    """Octroie toutes les permissions sur le schéma public à un utilisateur IAM.

    Idempotent : GRANT sur un droit déjà accordé est silencieux en PostgreSQL.
    """
    grants = [
        f'GRANT ALL ON SCHEMA public TO "{user}";',
        f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{user}";',
        f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{user}";',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO "{user}";',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO "{user}";',
    ]
    errors = []
    for stmt in grants:
        try:
            await conn.execute(stmt)
        except Exception as e:
            errors.append(f"    WARN ({stmt[:40]}...): {e}")

    if errors:
        for err in errors:
            print(err, flush=True)
    else:
        print(f"  ✓ Permissions accordées sur '{db_name}' → {label} '{user}'", flush=True)


async def main() -> None:
    root_pw = get_env("ROOT_DB_URL")
    db_ip = get_env("DB_IP")
    project_id = get_env("PROJECT_ID")
    env_name = get_env("ENV_VAL")
    sa_suffix = get_env("SA_SUFFIX")
    admin_user = get_env("ADMIN_USER", required=False)

    root_pw_encoded = urllib.parse.quote(root_pw, safe="")
    master_dsn = f"postgresql://postgres:{root_pw_encoded}@{db_ip}:5432/postgres?sslmode=require"

    # ─────────────────────────────────────────────────────────────────────────
    # Étape 1 : Création des bases de données (connexion master)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[DB INIT] ═══ Étape 1 : Création des bases de données ═══", flush=True)
    try:
        master_conn = await asyncpg.connect(master_dsn)
    except Exception as e:
        print(f"[DB INIT] FATAL: Impossible de se connecter à AlloyDB ({db_ip}): {e}", flush=True)
        sys.exit(1)

    for svc in SERVICES:
        try:
            await master_conn.execute(f'CREATE DATABASE "{svc}";')
            print(f"  ✓ Création de la base '{svc}'", flush=True)
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg:
                print(f"  = Base '{svc}' déjà existante — ignoré", flush=True)
            else:
                print(f"  ! Erreur création base '{svc}': {e}", flush=True)

    await master_conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Étape 2 : Attribution des permissions par base de données
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[DB INIT] ═══ Étape 2 : Attribution des permissions IAM ═══", flush=True)

    for svc in SERVICES:
        # Convention de nommage des SA (alignée sur cloudrun.tf + random_id.sa_suffix)
        # drive_api : suffixe fixe "-v2" (SA non-régénérable, legacy)
        if svc == "drive":
            iam_user = f"sa-drive-{env_name}-v2@{project_id}.iam"
        else:
            iam_user = f"sa-{svc}-{env_name}-{sa_suffix}@{project_id}.iam"

        svc_dsn = f"postgresql://postgres:{root_pw_encoded}@{db_ip}:5432/{svc}?sslmode=require"
        print(f"\n  → Base '{svc}' / SA '{iam_user}'", flush=True)

        try:
            svc_conn = await asyncpg.connect(svc_dsn)
        except Exception as e:
            print(f"  ! Connexion impossible à la base '{svc}': {e}", flush=True)
            continue

        try:
            await grant_permissions(svc_conn, iam_user, svc, label="service")
            if admin_user:
                await grant_permissions(svc_conn, admin_user, svc, label="admin")
        finally:
            await svc_conn.close()

    print("\n[DB INIT] ✓ Initialisation terminée avec succès.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
