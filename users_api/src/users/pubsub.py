
import os
import json
import logging
from google.cloud import pubsub_v1
from opentelemetry.propagate import inject

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
TOPIC_ID = os.getenv("USER_EVENTS_TOPIC", "zenika-user-events")

publisher = None
try:
    if PROJECT_ID:
        publisher = pubsub_v1.PublisherClient()
except Exception as e:
    logger.warning(f"Could not initialize Pub/Sub client: {e}")

async def publish_user_event(event_type: str, data: dict):
    """
    Publishes a user event to GCP Pub/Sub.
    Event types: user.merged, user.deleted, user.anonymized
    """
    # Inject OTel headers for trace propagation
    headers = {}
    inject(headers)
    
    if not publisher or not PROJECT_ID:
        logger.info(f"[MOCK-PUBSUB] Event: {event_type} TraceHeaders: {headers} Data: {data}")
        return

    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    message_json = json.dumps({
        "event": event_type,
        "data": data
    })
    message_bytes = message_json.encode("utf-8")
    
    try:
        # We pass the trace headers as attributes
        future = publisher.publish(topic_path, message_bytes, **headers)
        logger.info(f"Published event {event_type} to {topic_path} with tracing: {future.result()}")
    except Exception as e:
        logger.error(f"Failed to publish Pub/Sub event: {e}")
