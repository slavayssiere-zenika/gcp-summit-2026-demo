from google.cloud import logging

client = logging.Client(project="prod-ia-staffing")
filter_str = 'resource.type="cloud_run_revision" AND resource.labels.service_name="cv-api-prd" AND timestamp >= "2026-05-12T23:01:00Z" AND timestamp <= "2026-05-12T23:03:00Z"'
entries = list(client.list_entries(filter_=filter_str, max_results=1000, order_by=logging.ASCENDING))
for entry in entries:
    if type(entry.payload) == str and ("Error:" in entry.payload or "Exception:" in entry.payload):
        print(entry.payload)
