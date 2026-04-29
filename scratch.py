import os
from google.cloud import logging

def get_logs():
    client = logging.Client(project="prod-ia-staffing")
    filter_str = 'resource.type="cloud_run_revision" AND resource.labels.service_name="competencies-api-prd" AND timestamp >= "2026-04-26T21:50:00Z" AND severity >= WARNING'
    
    entries = client.list_entries(filter_=filter_str, order_by=logging.DESCENDING, max_results=30)
    for entry in entries:
        r = entry.to_api_repr()
        payload = r.get('textPayload', '')
        if not payload and 'jsonPayload' in r:
            payload = str(r['jsonPayload'])
        print(f"[{entry.timestamp}] {entry.severity}: {payload}")

get_logs()
