#!/usr/bin/env python3
"""
validate_pubsub_emulator.py — Valide le contrat des messages Pub/Sub via l'API REST de l'émulateur.

Interroge l'émulateur Pub/Sub local pour inspecter les messages publiés par drive_api
et vérifier qu'ils respectent le schéma attendu par cv_api (/pubsub/import-cv).

Usage :
    python3 scripts/validate_pubsub_emulator.py
    python3 scripts/validate_pubsub_emulator.py --host localhost:8085 --project test-project
    python3 scripts/validate_pubsub_emulator.py --dlq        # inspecte aussi la DLQ
    python3 scripts/validate_pubsub_emulator.py --drive-api http://localhost:8006 --token <JWT>

Codes de retour :
    0 — tous les messages sont conformes (ou aucun message à valider)
    1 — violations de contrat détectées
    2 — émulateur inaccessible ou erreur réseau
"""
import argparse
import base64
import json
import sys
import urllib.error
import urllib.request


# ── Schéma attendu par cv_api.PubsubService.handle_pubsub_cv_import ───────────
REQUIRED_FIELDS = {"google_file_id", "url", "file_type", "action"}
OPTIONAL_FIELDS = {"source_tag", "folder_name", "google_access_token", "oidc_token", "jwt"}
VALID_FILE_TYPES = {"google_doc", "docx"}
VALID_ACTIONS = {"upsert", "delete"}


def _http_post(url: str, body: dict, timeout: int = 10) -> dict:
    """POST JSON vers l'API REST de l'émulateur. Lève urllib.error.URLError en cas d'échec."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_put(url: str, body: dict, timeout: int = 10) -> dict:
    """PUT JSON vers l'API REST de l'émulateur."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_delete(url: str, timeout: int = 5) -> None:
    """DELETE vers l'API REST de l'émulateur."""
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except urllib.error.HTTPError:
        pass  # 404 acceptable si la subscription n'existait pas


def _pull_messages(emulator: str, project: str, subscription: str, max_msgs: int = 200) -> list:
    """Pull les messages d'une subscription sans les acker (peek-only via maxMessages sans ackIds)."""
    url = f"http://{emulator}/v1/projects/{project}/subscriptions/{subscription}:pull"
    try:
        result = _http_post(url, {"maxMessages": max_msgs})
        return result.get("receivedMessages", [])
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Impossible de contacter l'émulateur ({emulator}) : {exc}") from exc


def _ensure_subscription(emulator: str, project: str, sub: str, topic: str) -> bool:
    """Crée la subscription si elle n'existe pas. Retourne True si créée, False si déjà existante."""
    url = f"http://{emulator}/v1/projects/{project}/subscriptions/{sub}"
    try:
        _http_put(url, {"topic": f"projects/{project}/topics/{topic}"})
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return False
        raise


def _delete_subscription(emulator: str, project: str, sub: str) -> None:
    """Supprime une subscription temporaire."""
    url = f"http://{emulator}/v1/projects/{project}/subscriptions/{sub}"
    _http_delete(url)


def _decode_payload(item: dict) -> tuple[dict | None, str | None]:
    """Décode le message Pub/Sub base64 → dict. Retourne (payload, error_msg)."""
    try:
        raw_b64 = item.get("message", {}).get("data", "")
        raw = base64.b64decode(raw_b64).decode("utf-8")
        return json.loads(raw), None
    except Exception as exc:
        return None, f"Décodage impossible : {exc}"


def _validate_payload(payload: dict, index: int) -> list[str]:
    """Valide un payload Pub/Sub. Retourne la liste des violations."""
    violations = []

    missing = REQUIRED_FIELDS - payload.keys()
    if missing:
        violations.append(f"Msg #{index}: champs obligatoires manquants = {sorted(missing)}")

    file_type = payload.get("file_type")
    if file_type is not None and file_type not in VALID_FILE_TYPES:
        violations.append(
            f"Msg #{index}: file_type invalide = {file_type!r} "
            f"(attendu: {sorted(VALID_FILE_TYPES)})"
        )

    action = payload.get("action")
    if action is not None and action not in VALID_ACTIONS:
        violations.append(
            f"Msg #{index}: action invalide = {action!r} "
            f"(attendu: {sorted(VALID_ACTIONS)})"
        )

    if not payload.get("google_file_id", "").strip():
        violations.append(f"Msg #{index}: google_file_id est vide ou absent")

    if not payload.get("url", "").strip():
        violations.append(f"Msg #{index}: url est vide ou absent")

    unknown = payload.keys() - REQUIRED_FIELDS - OPTIONAL_FIELDS
    if unknown:
        violations.append(f"Msg #{index}: champs inconnus (warning) = {sorted(unknown)}")

    return violations


def validate_subscription(
    emulator: str, project: str, subscription: str, label: str
) -> tuple[int, int, list[str]]:
    """
    Valide tous les messages d'une subscription.

    Retourne (nb_messages, nb_violations, liste_violations).
    """
    print(f"\n📋 Inspection de '{label}' ({subscription})...")
    try:
        messages = _pull_messages(emulator, project, subscription)
    except RuntimeError as exc:
        return 0, 1, [str(exc)]

    if not messages:
        print(f"  ℹ️  Aucun message en attente dans '{label}'.")
        return 0, 0, []

    print(f"  📨 {len(messages)} message(s) trouvé(s).")
    all_violations: list[str] = []

    for i, item in enumerate(messages):
        payload, decode_err = _decode_payload(item)
        if decode_err:
            all_violations.append(f"Msg #{i}: {decode_err}")
            continue
        violations = _validate_payload(payload, i)
        all_violations.extend(violations)

    return len(messages), len(all_violations), all_violations


def check_drive_api_statuses(drive_api_url: str, token: str) -> tuple[int, int]:
    """
    Interroge drive_api pour compter les fichiers par statut.

    Retourne (nb_imported_cv, nb_error).
    """
    url = f"{drive_api_url.rstrip('/')}/api/drive/files?limit=500"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  ⚠️  Impossible d'interroger drive_api : {exc}")
        return 0, 0

    files = data.get("files", data if isinstance(data, list) else [])
    imported = sum(1 for f in files if f.get("status") == "IMPORTED_CV")
    errors = sum(1 for f in files if f.get("status") == "ERROR")
    queued = sum(1 for f in files if f.get("status") in ("QUEUED", "PROCESSING"))

    print("\n📊 Statuts drive_api :")
    print(f"  ✅ IMPORTED_CV : {imported}")
    print(f"  ❌ ERROR       : {errors}")
    print(f"  ⏳ En cours    : {queued}")
    if errors > 0:
        print(f"  ⚠️  {errors} fichier(s) en erreur — consulter les logs cv_api.")

    return imported, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valide le contrat des messages Pub/Sub via l'API REST de l'émulateur GCP."
    )
    parser.add_argument(
        "--host",
        default="localhost:8085",
        help="Host:port de l'émulateur Pub/Sub (défaut: localhost:8085)",
    )
    parser.add_argument(
        "--project",
        default="test-project",
        help="Projet GCP de l'émulateur (défaut: test-project)",
    )
    parser.add_argument(
        "--subscription",
        default="cv-import-sub",
        help="Subscription principale à inspecter (défaut: cv-import-sub)",
    )
    parser.add_argument(
        "--dlq",
        action="store_true",
        help="Inspecte aussi la DLQ (cv-import-dlq)",
    )
    parser.add_argument(
        "--dlq-topic",
        default="cv-import-dlq",
        help="Nom du topic DLQ (défaut: cv-import-dlq)",
    )
    parser.add_argument(
        "--drive-api",
        default="",
        help="URL de drive_api pour vérification croisée des statuts (ex: http://localhost:8006)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="JWT Bearer pour authentification sur drive_api",
    )
    parsed = parser.parse_args()

    print(f"\n🔍 Validation du contrat Pub/Sub — émulateur {parsed.host}")
    print(f"   Projet      : {parsed.project}")
    print(f"   Subscription: {parsed.subscription}")

    total_msgs = 0
    total_violations = 0
    all_violations: list[str] = []

    # ── Validation subscription principale ────────────────────────────────────
    nb, viol, details = validate_subscription(
        parsed.host, parsed.project, parsed.subscription, "Subscription principale"
    )
    total_msgs += nb
    total_violations += viol
    all_violations.extend(details)

    # ── Validation DLQ (optionnel) ─────────────────────────────────────────────
    if parsed.dlq:
        dlq_sub = "dlq-inspect-tmp"
        created = _ensure_subscription(parsed.host, parsed.project, dlq_sub, parsed.dlq_topic)
        try:
            nb_dlq, viol_dlq, details_dlq = validate_subscription(
                parsed.host, parsed.project, dlq_sub, f"DLQ ({parsed.dlq_topic})"
            )
            total_msgs += nb_dlq
            total_violations += viol_dlq
            all_violations.extend(details_dlq)
            if nb_dlq > 0:
                print(f"\n  ⚠️  {nb_dlq} message(s) en DLQ — cv_api a échoué {5}x sur ces messages.")
        finally:
            if created:
                _delete_subscription(parsed.host, parsed.project, dlq_sub)

    # ── Vérification croisée drive_api (optionnel) ────────────────────────────
    if parsed.drive_api and parsed.token:
        check_drive_api_statuses(parsed.drive_api, parsed.token)
    elif parsed.drive_api and not parsed.token:
        print("\n  ⚠️  --drive-api fourni sans --token : vérification croisée ignorée.")

    # ── Résultat final ─────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    if total_msgs == 0:
        print("ℹ️  Aucun message inspecté (subscription vide ou émulateur non alimenté).")
        print("   Lancez d'abord une ingestion Drive pour peupler la queue.")
        sys.exit(0)

    if total_violations == 0:
        print(f"✅ Contrat Pub/Sub OK — {total_msgs} message(s) valide(s), 0 violation.")
        sys.exit(0)

    print(f"❌ {total_violations} violation(s) sur {total_msgs} message(s) :")
    for v in all_violations:
        print(f"  - {v}")
    print("=" * 72)
    sys.exit(1)


if __name__ == "__main__":
    main()
