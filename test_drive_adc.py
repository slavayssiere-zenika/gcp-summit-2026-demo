import google.auth
from googleapiclient.discovery import build
import json

def main():
    try:
        credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        
        service = build("drive", "v3", credentials=credentials)
        
        # Test bare query
        print("Testing bare list for user...")
        res = service.files().list(
            pageSize=10, 
            fields="files(id, name, mimeType)"
        ).execute()
        files = res.get('files', [])
        print(f"Found {len(files)} files.")
        for f in files:
            print(f"- {f.get('name')} ({f.get('mimeType')})")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
