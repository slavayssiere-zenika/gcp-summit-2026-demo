"""
Fixtures Testcontainers pour les tests d'intégration de drive_api.

L'émulateur Pub/Sub GCP est la seule solution pour tester réellement la logique
de publication/souscription sans mocker PublisherClient — ce mock actuel ne
valide pas la sérialisation des payloads, les paths de topic, ni le comportement
de `publisher.publish()` en cas d'erreur réseau.

Note technique : pas d'image Testcontainers officielle pour Pub/Sub — on utilise
DockerContainer directement avec l'image officielle Google Cloud SDK.
"""
import os
import time

import pytest
from google.cloud import pubsub_v1
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer

PUBSUB_PROJECT = "test-project"
PUBSUB_TOPIC = "cv-import-events"
PUBSUB_SUBSCRIPTION = "cv-import-events-sub"


@pytest.fixture(scope="session")
def postgres_container_drive():
    """Démarre PostgreSQL 16 pour les tables drive_api (DriveFolder, DriveSyncState)."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def pubsub_emulator():
    """
    Démarre l'émulateur Pub/Sub GCP via l'image officielle google/cloud-sdk.

    L'émulateur expose le port 8085 et est compatible avec le SDK Python
    via la variable d'environnement PUBSUB_EMULATOR_HOST.
    """
    container = (
        DockerContainer("gcr.io/google.com/cloudsdktool/cloud-sdk:emulators")
        .with_command(
            "gcloud beta emulators pubsub start "
            "--project=test-project "
            "--host-port=0.0.0.0:8085"
        )
        .with_exposed_ports(8085)
    )
    container.start()

    host = container.get_container_host_ip()
    port = container.get_exposed_port(8085)
    emulator_host = f"{host}:{port}"

    # Attendre que l'émulateur soit prêt (max 30s)
    os.environ["PUBSUB_EMULATOR_HOST"] = emulator_host
    _wait_for_pubsub_emulator(emulator_host)

    yield emulator_host

    container.stop()


def _wait_for_pubsub_emulator(host: str, timeout: int = 30):
    """Attend que l'émulateur Pub/Sub soit prêt à accepter des connexions."""
    import grpc
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            channel = grpc.insecure_channel(host)
            grpc.channel_ready_future(channel).result(timeout=2)
            channel.close()
            return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"L'émulateur Pub/Sub n'est pas démarré après {timeout}s sur {host}")


@pytest.fixture(scope="session")
def pubsub_topic_and_sub(pubsub_emulator):
    """
    Crée le topic et la souscription dans l'émulateur.

    Doit être appelé après que PUBSUB_EMULATOR_HOST est positionné.
    """
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(PUBSUB_PROJECT, PUBSUB_TOPIC)
    sub_path = subscriber.subscription_path(PUBSUB_PROJECT, PUBSUB_SUBSCRIPTION)

    # Créer le topic (idempotent)
    try:
        publisher.create_topic(request={"name": topic_path})
    except Exception:
        pass  # Déjà existant

    # Créer la souscription (idempotent)
    try:
        subscriber.create_subscription(request={"name": sub_path, "topic": topic_path})
    except Exception:
        pass

    subscriber.close()

    yield topic_path, sub_path


@pytest.fixture(scope="session")
def integration_env_drive(postgres_container_drive, pubsub_emulator):
    """Injecte les URLs dynamiques dans les variables d'environnement."""
    pg_sync_url = postgres_container_drive.get_connection_url()
    pg_async_url = pg_sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    os.environ["DATABASE_URL"] = pg_async_url
    os.environ["GCP_PROJECT_ID"] = PUBSUB_PROJECT
    os.environ["PUBSUB_CV_IMPORT_TOPIC"] = PUBSUB_TOPIC
    os.environ["PUBSUB_EMULATOR_HOST"] = pubsub_emulator
    yield


@pytest.fixture
def wipe_drive_db(postgres_container_drive, integration_env_drive):
    """Recrée le schéma drive_api avant chaque test."""
    from src.models import Base
    sync_url = postgres_container_drive.get_connection_url()
    engine = create_engine(sync_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    yield
