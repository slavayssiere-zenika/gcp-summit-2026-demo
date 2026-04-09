import asyncio
from drive_api.src.google_auth import get_drive_service
import sys

def main():
    service = get_drive_service()
    
    print("Testing corpora='allDrives'...")
    try:
        res1 = service.files().list(
            q="mimeType='application/vnd.google-apps.document' and trashed=false",
            spaces="drive",
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id, name)"
        ).execute()
        print(f"allDrives files: {len(res1.get('files', []))}")
    except Exception as e:
        print(f"Error: {e}")

    print("Testing corpora='user'...")
    try:
        res2 = service.files().list(
            q="mimeType='application/vnd.google-apps.document' and trashed=false",
            spaces="drive",
            corpora="user",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id, name)"
        ).execute()
        print(f"user files: {len(res2.get('files', []))}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
