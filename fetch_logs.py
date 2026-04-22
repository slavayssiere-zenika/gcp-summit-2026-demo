import os
from google.cloud import logging

def fetch_logs():
    try:
        client = logging.Client(project="slavayssiere-sandbox-462015")
        filter_str = 'resource.type="cloud_run_revision" AND resource.labels.service_name="cv-api-dev" AND severity>=WARNING'
        print(f"Fetching logs with filter: {filter_str}")
        for entry in client.list_entries(filter_=filter_str, order_by=logging.DESCENDING, max_results=10):
            print(f"[{entry.severity}] {entry.timestamp}: {entry.payload}")
    except Exception as e:
        print(f"Error fetching logs: {e}")

fetch_logs()
