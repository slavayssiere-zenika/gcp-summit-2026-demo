import asyncio
import os
import re
import sys
import logging
from datetime import datetime, timedelta

import httpx
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("remediate")

# Config (Local dev par défaut)
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "cv")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_dev_key")

COMPETENCIES_API = os.getenv("COMPETENCIES_API_URL", "http://localhost:8004")
DRIVE_API = os.getenv("DRIVE_API_URL", "http://localhost:8006")

# Engine & Session
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

def generate_admin_token() -> str:
    """Génère un JWT Admin valide pour passer l'auth interne des APIs."""
    payload = {
        "sub": "admin",
        "email": "admin@zenika.com",
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

async def main():
    logger.info("🚀 Démarrage du script de remédiation des erreurs silencieuses de taxonomie.")
    
    token = generate_admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    async with AsyncSessionLocal() as db:
        # On évite d'importer les modèles complets si PYTHONPATH n'est pas bien set,
        # on utilise directement SQLAlchemy Core / Table reflection ou texte.
        from sqlalchemy import text
        
        logger.info("📦 Récupération de tous les CV Profiles...")
        result = await db.execute(text("SELECT id, user_id, source_url, extracted_competencies FROM cv_profiles WHERE source_url IS NOT NULL"))
        profiles = result.fetchall()
        
        logger.info(f"🔍 {len(profiles)} profils trouvés à vérifier.")
        
        fixed_count = 0
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for p_id, user_id, source_url, extracted_competencies in profiles:
                llm_comps = extracted_competencies if extracted_competencies else []
                nb_extracted = len([c for c in llm_comps if c.get("name")])
                
                # S'il n'y avait aucune compétence dans le CV d'origine, on ignore.
                if nb_extracted == 0:
                    continue
                
                # 1. Vérifier les compétences assignées
                try:
                    res = await client.get(f"{COMPETENCIES_API}/user/{user_id}", headers=headers)
                    if res.status_code == 200:
                        comps = res.json()
                        nb_assigned = len(comps)
                        
                        if nb_assigned >= nb_extracted:
                            # Tout va bien (ou l'utilisateur en a même plus grâce à d'autres imports)
                            continue
                except Exception as e:
                    logger.error(f"❌ Erreur réseau lors de la vérification des compétences pour user_id={user_id}: {e}")
                    continue
                
                # 2. Arrivé ici = échec partiel ou total
                logger.warning(f"⚠️ user_id={user_id} a {nb_assigned} compétence(s) assignée(s) sur {nb_extracted} extraite(s). Remédiation en cours...")
                
                error_msg = f"Legacy: Échec partiel ou total d'assignation ({nb_assigned}/{nb_extracted} compétences assignées)."
                
                # 3. Patch Drive API
                google_file_id = None
                doc_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", source_url)
                if doc_id_match:
                    google_file_id = doc_id_match.group(1)
                else:
                    id_param_match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", source_url)
                    if id_param_match:
                        google_file_id = id_param_match.group(1)

                if google_file_id:
                    try:
                        patch_res = await client.patch(
                            f"{DRIVE_API}/files/{google_file_id}",
                            json={"status": "ERROR", "error_message": error_msg},
                            headers=headers
                        )
                        if patch_res.status_code >= 400:
                            logger.error(f"  ❌ Échec du PATCH Drive API pour file_id={google_file_id}")
                        else:
                            logger.info(f"  ✅ Fichier Google Drive {google_file_id} marqué en ERROR.")
                    except Exception as e:
                        logger.error(f"  ❌ Erreur réseau lors du PATCH Drive: {e}")
                else:
                    logger.warning(f"  ⚠️ Impossible d'extraire un ID Google Drive de l'URL: {source_url}")
                
                # 4. Mettre à jour en base
                try:
                    import json
                    json_err = json.dumps([error_msg])
                    await db.execute(
                        text("UPDATE cv_profiles SET processing_errors = :err WHERE id = :p_id"),
                        {"err": json_err, "p_id": p_id}
                    )
                    await db.commit()
                    logger.info(f"  ✅ Profil BDD mis à jour (processing_errors).")
                    fixed_count += 1
                except Exception as e:
                    logger.error(f"  ❌ Échec de la mise à jour en BDD: {e}")
                    await db.rollback()
        
    logger.info(f"🎉 Remédiation terminée ! {fixed_count} profil(s) mis à jour en erreur visible.")
    logger.info("👉 Allez dans l'interface DriveErrorsPanel pour cliquer sur 'Réessayer Tout'.")

if __name__ == "__main__":
    asyncio.run(main())
