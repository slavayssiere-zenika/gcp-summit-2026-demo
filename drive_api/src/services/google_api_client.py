import asyncio
import logging

logger = logging.getLogger(__name__)

class DriveApiClient:
    def __init__(self, drive):
        self.drive = drive

    async def get_folder_meta(self, folder_id: str, fields: str = "parents,name"):
        for attempt in range(3):
            try:
                return await asyncio.to_thread(
                    lambda: self.drive.files().get(
                        fileId=folder_id,
                        fields=fields,
                        supportsAllDrives=True,
                    ).execute()
                )
            except Exception as e:
                logger.warning(f"Erreur Drive API get pour {folder_id} (attempt {attempt + 1}): {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def list_files(self, q: str, page_token: str | None, corpora: str = "allDrives", fields: str = "nextPageToken, files(id, name, mimeType, modifiedTime, version, parents, trashed)"):
        for attempt in range(3):
            try:
                return await asyncio.to_thread(
                    lambda pt=page_token: self.drive.files().list(
                        q=q,
                        spaces="drive",
                        corpora=corpora,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        fields=fields,
                        pageToken=pt,
                        pageSize=1000,
                    ).execute()
                )
            except Exception as e:
                logger.warning(f"Erreur Drive API list (attempt {attempt + 1}): {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def get_about(self):
        return await asyncio.to_thread(
            lambda: self.drive.about().get(fields="user").execute()
        )
