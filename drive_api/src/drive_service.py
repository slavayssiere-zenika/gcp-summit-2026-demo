from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.redis_client import get_redis
from src.google_auth import get_drive_service, get_m2m_jwt_token, get_google_access_token
import httpx
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CV_API_URL = os.getenv("CV_API_URL", "http://cv_api:8004")
MAX_DRIVE_CV_IMPORT = int(os.getenv("MAX_DRIVE_CV_IMPORT", "10"))

class DriveService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.drive = get_drive_service()
        self.redis = get_redis()
    
    async def _resolve_root_tag(self, start_parent_id: str) -> DriveFolder:
        """
        Ascendant traversal with Redis Cache.
        Walks up the Google Drive parent tree until it matches a configured root folder.
        """
        current_id = start_parent_id
        path_traversed = []
        
        while current_id:
            logger.info(f"[_resolve_root_tag] Evaluating current_id: {current_id}")
            # 1. Check if it's already a Root in DB (support partial matches like URLs)
            db_folder = (await self.db.execute(select(DriveFolder).filter(DriveFolder.google_folder_id.like(f"%{current_id}%")))).scalars().first()
            if db_folder:
                logger.info(f"[_resolve_root_tag] Found {current_id} as mapped DB root (tag: {db_folder.tag}).")
                self._cache_path(path_traversed, db_folder.id)
                return db_folder
            
            # 2. Check Redis Cache
            cached_root_id = self.redis.get(f"drive:graph:{current_id}")
            if cached_root_id:
                logger.info(f"[_resolve_root_tag] Cache HIT for {current_id} -> root_id: {cached_root_id}")
                # Cache Hit!
                db_folder = (await self.db.execute(select(DriveFolder).filter(DriveFolder.id == int(cached_root_id)))).scalars().first()
                if db_folder:
                    self._cache_path(path_traversed, db_folder.id)
                    return db_folder
            
            # 3. API Call to get parent
            try:
                logger.info(f"[_resolve_root_tag] API call to Drive to get parent for ID: {current_id}...")
                folder_meta = self.drive.files().get(
                    fileId=current_id, 
                    fields="parents, name",
                    supportsAllDrives=True
                ).execute()
                logger.info(f"[_resolve_root_tag] Meta for {current_id}: {folder_meta}")
                parents = folder_meta.get("parents", [])
                
                if not parents:
                    logger.info(f"[_resolve_root_tag] Hit absolute root for {current_id}. No more parents.")
                    break # Hit the absolute root of the account, nowhere else to go
                    
                path_traversed.append(current_id)
                current_id = parents[0] # Usually there's only 1 parent in typical setups
            except Exception as e:
                logger.error(f"Error fetching parent metadata for {current_id}: {e}")
                break
                
        # If we loop out and find nothing, it's not in our target directories
        return None
        
    def _cache_path(self, path: list, root_folder_id: int):
        """Saves intermediate folders mapping to the root in Redis for 1 month"""
        for intermediate_id in path:
            self.redis.set(f"drive:graph:{intermediate_id}", str(root_folder_id), ex=2592000)

    async def discover_files(self):
        """
        Step 1: Global Delta. Find exactly what changed since the last known time.
        """
        # Find the latest tracked modified_time
        latest_file = (await self.db.execute(select(func.max(DriveSyncState.modified_time)))).scalar()
        
        # If we have no history, we fall back to a reasonable date (e.g., last 1 month) to avoid fetching millions.
        # Alternatively, for the very first initialization, it fetches everything.
        if latest_file:
            # Add a 1 minute overlap for safety
            safe_time = latest_file - timedelta(minutes=1)
            date_query = f" and modifiedTime > '{safe_time.isoformat()}Z'"
        else:
            # First execution initialization: pull the last year or maybe everything.
            date_query = ""
            
        # Find out WHO we are authenticated as, so we can check permissions in Drive
        try:
            about = self.drive.about().get(fields="user").execute()
            sa_email = about.get('user', {}).get('emailAddress', 'Unknown')
            logger.info(f"Authentifié sur Google Drive en tant que : {sa_email}")
        except Exception as e:
            logger.error(f"[DRIVE_API_AUTH_LOSS] Le Service Account a perdu l'accès au Drive: {e}")
            raise e
            
        q = f"mimeType='application/vnd.google-apps.document' and trashed=false{date_query}"
        
        logger.info(f"Running Global Delta Query: {q}")
        
        new_discoveries = 0
        for corpus in ["allDrives", "user"]:
            page_token = None
            while True:
                results = self.drive.files().list(
                    q=q,
                    spaces="drive",
                    corpora=corpus,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    fields="nextPageToken, files(id, name, modifiedTime, version, parents)",
                    pageToken=page_token,
                    pageSize=100
                ).execute()
                
                files = results.get('files', [])
                logger.info(f"Page fetched from corpus '{corpus}' with {len(files)} files.")
            
                for file in files:
                    file_id = file.get('id')
                    name = file.get('name', 'Unknown')
                    mod_time_str = file.get('modifiedTime')
                    version = str(file.get('version', '1'))
                    parents = file.get('parents', [])
                    
                    logger.info(f"Evaluating file: {name} ({file_id}) - Parents: {parents}")
                    
                    if not parents:
                        logger.info(f"File {file_id} has no parents, skipping.")
                        continue
                        
                    mod_time = datetime.fromisoformat(mod_time_str.replace("Z", "+00:00"))
                    
                    # Check Ascendant Mapping
                    root_folder = await self._resolve_root_tag(parents[0])
                    
                    # If it's valid for our application
                    if root_folder:
                        logger.info(f"File '{name}' mapped to valid root folder ID {root_folder.id} (tag: {getattr(root_folder, 'tag', 'unknown')}). Queuing.")
                        # Upsert into Queue
                        state = (await self.db.execute(select(DriveSyncState).filter(DriveSyncState.google_file_id == file_id))).scalars().first()
                        if not state:
                            state = DriveSyncState(
                                google_file_id=file_id,
                                folder_id=root_folder.id,
                                file_name=name,
                                revision_id=version,
                                modified_time=mod_time.replace(tzinfo=None),
                                status=DriveSyncStatus.PENDING
                            )
                            self.db.add(state)
                            new_discoveries += 1
                        else:
                            # Update name if changed or missing
                            if state.file_name != name:
                                state.file_name = name
                            
                            if state.revision_id != version:
                                state.revision_id = version
                                state.modified_time = mod_time.replace(tzinfo=None)
                                state.status = DriveSyncStatus.PENDING # Re-evaluate
                                new_discoveries += 1
                    else:
                        logger.info(f"File '{name}' was not mapped to any valid root folder (parent was {parents[0]}).")
                
                await self.db.commit()
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
                
        logger.info(f"Global Delta Discovery complete. {new_discoveries} files queued.")

    async def ingest_batch(self):
        """
        Step 2: Throttling & CV Importer execution.
        """
        base_query = select(DriveSyncState).filter(
            DriveSyncState.status == DriveSyncStatus.PENDING
        ).order_by(DriveSyncState.modified_time.asc()).limit(MAX_DRIVE_CV_IMPORT)
        pending_files = (await self.db.execute(base_query)).scalars().all()
        
        if not pending_files:
            return 0
            
        m2m_jwt = get_m2m_jwt_token()
        headers = {"Authorization": f"Bearer {m2m_jwt}"}
        google_access_token = get_google_access_token()
        
        processed_count = 0
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            for state in pending_files:
                # We need to get the tag
                folder = (await self.db.execute(select(DriveFolder).filter(DriveFolder.id == state.folder_id))).scalars().first()
                if not folder:
                    state.status = DriveSyncStatus.ERROR
                    continue
                    
                # The CV URL
                doc_url = f"https://docs.google.com/document/d/{state.google_file_id}"
                
                payload = {
                    "url": doc_url,
                    "source_tag": folder.tag,
                    "google_access_token": google_access_token
                }
                
                # Tracing injection (Golden Rule #4)
                from opentelemetry.propagate import inject
                inject(headers)
                
                try:
                    logger.info(f"CV trouvé (Nom: '{state.file_name}', Tag: {folder.tag}). Appel de l'API CV...")
                    state.status = DriveSyncStatus.PROCESSING
                    await self.db.commit()
                    res = await http_client.post(f"{CV_API_URL.rstrip('/')}/import", json=payload, headers=headers)
                    if res.status_code < 400:
                        data = res.json()
                        state.status = DriveSyncStatus.IMPORTED_CV
                        state.user_id = data.get("user_id")
                        processed_count += 1
                        logger.info(f"File {state.google_file_id} ({state.file_name}) imported successfully. Assigned user_id: {state.user_id}")
                    else:
                        # Assuming 400 with a specific error if it's not a CV or failed parsing
                        error_detail = res.json().get("detail", "")
                        if "LLM Parsing failed" in error_detail or "Not a CV" in error_detail:
                            state.status = DriveSyncStatus.IGNORED_NOT_CV
                            logger.info(f"File {state.google_file_id} ignored (Not a CV or parsing error)")
                        else:
                            state.status = DriveSyncStatus.ERROR
                            logger.error(f"Failed to import '{state.file_name}' ({state.google_file_id}): {error_detail}")
                except Exception as e:
                    state.status = DriveSyncStatus.ERROR
                    logger.error(f"Network error sending '{state.file_name}' ({state.google_file_id}) to CV API: {e}")
                    
                state.last_processed_at = datetime.utcnow()
                await self.db.commit()
                
        return processed_count
