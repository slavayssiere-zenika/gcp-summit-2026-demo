import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.google_auth import get_drive_service
from src.redis_client import get_redis

from src.discovery_service import DiscoveryService
from src.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


class DriveService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.drive = get_drive_service()
        self.redis = get_redis()

        self.discovery_service = DiscoveryService(self.db, self.drive, self.redis)
        self.ingestion_service = IngestionService(self.db)

    def invalidate_roots_cache(self) -> None:
        """Invalide le cache des folders racines (appeler sur POST/DELETE /folders)."""
        self.discovery_service.invalidate_roots_cache()

    async def discover_files(self, force_full: bool = False) -> int:
        """
        Orchestrateur de la découverte.
        - force_full=True : Top-Down récursif sur tous les dossiers (rapide pour reconstruire l'arbre)
        - force_full=False : Top-Down pour les nouveaux dossiers, puis Bottom-Up (Delta) pour le reste.
        """
        return await self.discovery_service.discover_files(force_full=force_full)

    async def ingest_batch(self) -> int:
        """
        Étape 2 : Publication des fichiers PENDING dans Pub/Sub (zenika-cv-import-events).
        """
        return await self.ingestion_service.ingest_batch()
