import os
import json
from google.cloud import storage

def sample_outputs():
    client = storage.Client(project="prod-ia-staffing")
    bucket = client.bucket("cv-batch-prd-prod-ia-staffing-d415f922")
    
    # List latest directories in bulk-reanalyse/output/
    blobs = list(bucket.list_blobs(prefix="bulk-reanalyse/output/"))
    jsonl_blobs = [b for b in blobs if b.name.endswith('.jsonl')]
    
    if not jsonl_blobs:
        print("No jsonl found")
        return
        
    # Pick the most recent jsonl
    latest_blob = sorted(jsonl_blobs, key=lambda x: x.updated, reverse=True)[0]
    print(f"Reading from {latest_blob.name}")
    
    content = latest_blob.download_as_text()
    lines = content.splitlines()
    
    for i, line in enumerate(lines[:3]):
        record = json.loads(line)
        candidates = record.get("response", {}).get("candidates", [])
        if not candidates:
            print(f"Record {i}: NO CANDIDATES")
            continue
            
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        # Clean json text roughly like _clean_llm_json
        text = text.replace("```json\n", "").replace("\n```", "").strip()
        print(f"--- Record {i} ---")
        try:
            parsed = json.loads(text)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Parse error: {e}")
            print(text)

if __name__ == "__main__":
    sample_outputs()
