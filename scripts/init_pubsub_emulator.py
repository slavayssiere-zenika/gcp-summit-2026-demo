#!/usr/bin/env python3
"""
init_pubsub_emulator.py — Initialise topics et subscriptions dans l'émulateur Pub/Sub local.

Usage :
    PUBSUB_EMULATOR_HOST=localhost:8085 python3 scripts/init_pubsub_emulator.py
    python3 scripts/init_pubsub_emulator.py  # utilise localhost:8085 par defaut

Cree :
  - Topic       : projects/test-project/topics/cv-import-topic
  - Topic DLQ   : projects/test-project/topics/cv-import-dlq
  - Subscription push : projects/test-project/subscriptions/cv-import-sub
    → push vers http://cv_api:8004/pubsub/import-cv
    → dead_letter_policy : 5 tentatives max vers cv-import-dlq
"""
import os
import sys
import time


EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST", "localhost:8085")
PROJECT = "test-project"
TOPIC = "cv-import-topic"
DLQ_TOPIC = "cv-import-dlq"
SUBSCRIPTION = "cv-import-sub"
CV_API_PUSH_URL = os.getenv("CV_API_PUSH_URL", "http://cv_api:8004/pubsub/import-cv")

os.environ["PUBSUB_EMULATOR_HOST"] = EMULATOR_HOST


def _wait_emulator(timeout: int = 60) -> None:
    """Attend que l'émulateur soit prêt via probe gRPC (list_topics).

    L'émulateur Pub/Sub n'expose pas de healthcheck HTTP — uniquement gRPC sur
    le même port. On tente list_topics jusqu'à succès ou timeout.
    """
    from google.cloud import pubsub_v1
    from google.api_core.exceptions import GoogleAPICallError

    deadline = time.monotonic() + timeout
    project_path = f"projects/{PROJECT}"
    while time.monotonic() < deadline:
        try:
            pub = pubsub_v1.PublisherClient()
            list(pub.list_topics(request={"project": project_path}))
            print(f"  ✅ Emulateur prêt ({EMULATOR_HOST})")
            return
        except GoogleAPICallError:
            # Émulateur up mais projet inexistant — c'est OK, on peut créer
            print(f"  ✅ Emulateur prêt ({EMULATOR_HOST}) — projet vierge")
            return
        except Exception:
            pass
        print(f"  ⏳ Attente gRPC {EMULATOR_HOST}...")
        time.sleep(2)
    print(f"  ❌ Emulateur non accessible après {timeout}s sur {EMULATOR_HOST}")
    sys.exit(1)


def main() -> None:
    print(f"\n🔧 Initialisation de l'émulateur Pub/Sub ({EMULATOR_HOST})...")
    _wait_emulator()

    from google.api_core.exceptions import AlreadyExists
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(PROJECT, TOPIC)
    dlq_path = publisher.topic_path(PROJECT, DLQ_TOPIC)
    sub_path = subscriber.subscription_path(PROJECT, SUBSCRIPTION)

    # Créer les topics
    for path, name in [(topic_path, TOPIC), (dlq_path, DLQ_TOPIC)]:
        try:
            publisher.create_topic(request={"name": path})
            print(f"  ✅ Topic créé : {path}")
        except AlreadyExists:
            print(f"  ℹ️  Topic déjà existant : {path}")

    # Créer la subscription push vers cv_api
    try:
        subscriber.create_subscription(
            request={
                "name": sub_path,
                "topic": topic_path,
                "push_config": {
                    "push_endpoint": CV_API_PUSH_URL,
                },
                "dead_letter_policy": {
                    "dead_letter_topic": dlq_path,
                    "max_delivery_attempts": 5,
                },
                "ack_deadline_seconds": 600,
            }
        )
        print(f"  ✅ Subscription créée : {sub_path}")
        print(f"     → push vers {CV_API_PUSH_URL}")
    except AlreadyExists:
        print(f"  ℹ️  Subscription déjà existante : {sub_path}")

    print("\n✨ Emulateur Pub/Sub initialisé.")
    print(f"   Topic    : {topic_path}")
    print(f"   DLQ      : {dlq_path}")
    print(f"   Sub push : {sub_path}")


if __name__ == "__main__":
    main()
