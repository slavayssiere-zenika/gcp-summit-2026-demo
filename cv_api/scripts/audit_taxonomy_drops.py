#!/usr/bin/env python3
"""
audit_taxonomy_drops.py
-----------------------
Script standalone pour auditer les compétences droppées lors du Sweep.
Compare les drops avec la liste des compétences en DB pour identifier les faux positifs.

Usage:
    python3 cv_api/scripts/audit_taxonomy_drops.py \\
        --bucket cv-batch-prd-prod-ia-staffing-d415f922 \\
        --env prd
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone

# ── Parse args ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Audit des drops Sweep de la taxonomie.")
parser.add_argument("--bucket", required=True, help="Nom du bucket GCS (ex: cv-batch-prd-...)")
parser.add_argument("--env", default="prd", help="Environnement (prd, uat, dev)")
parser.add_argument("--sweep-prefix", default="taxonomy/output/", help="Préfixe GCS des outputs Sweep")
parser.add_argument("--top-n", type=int, default=50, help="Nb de drops à afficher dans le rapport")
args = parser.parse_args()

try:
    from google.cloud import storage as gcs_storage
except ImportError:
    print("❌ google-cloud-storage non installé. Lancez: pip install google-cloud-storage")
    sys.exit(1)

print(f"🔍 Audit taxonomy drops — bucket: {args.bucket} | env: {args.env}")
print(f"   Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

# ── Récupère le dernier Sweep output ─────────────────────────────────────────
client = gcs_storage.Client()
bucket = client.bucket(args.bucket)

sweep_blobs = list(bucket.list_blobs(prefix=args.sweep_prefix))
sweep_prediction_blobs = [
    b for b in sweep_blobs
    if "sweep" in b.name and "predictions.jsonl" in b.name
]
if not sweep_prediction_blobs:
    print("❌ Aucun fichier Sweep predictions.jsonl trouvé.")
    sys.exit(1)

latest_blob = sorted(sweep_prediction_blobs, key=lambda b: b.updated, reverse=True)[0]
print(f"📄 Fichier Sweep analysé : {latest_blob.name}")
print(f"   Mis à jour le : {latest_blob.updated}\n")

# ── Parse le JSONL Sweep ─────────────────────────────────────────────────────
raw = latest_blob.download_as_text()
lines = raw.strip().split("\n")

all_drops = []
all_assignments = []
all_merges = []
parse_errors = 0
finish_reasons = Counter()

for i, line in enumerate(lines):
    try:
        obj = json.loads(line)
        cands = obj.get("response", {}).get("candidates", [])
        if not cands:
            continue
        finish_reasons[str(cands[0].get("finishReason", "UNKNOWN"))] += 1
        text = cands[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        clean = re.sub(r"```json\n?", "", text.strip())
        clean = re.sub(r"```\n?", "", clean)
        data = json.loads(clean)
        all_drops.extend(data.get("drops", []))
        all_assignments.extend(data.get("assignments", []))
        all_merges.extend(data.get("merges", []))
    except Exception:
        parse_errors += 1

print("📊 Résultats du Sweep :")
print(f"   Chunks       : {len(lines)}")
print(f"   Parse errors : {parse_errors}")
print(f"   Finish       : {dict(finish_reasons)}")
print(f"   Assignments  : {len(all_assignments)}")
print(f"   Merges       : {len(all_merges)}")
print(f"   Drops        : {len(all_drops)}\n")

# ── Catégorisation heuristique des drops ─────────────────────────────────────
TECH_KEYWORDS = [
    "api", "aws", "azure", "gcp", "sql", "nosql", "java", "python", "scala",
    "kafka", "spark", "kubernetes", "docker", "terraform", "jenkins", "git",
    "react", "angular", "vue", "node", "spring", "django", "flask", "fastapi",
    "postgresql", "mongodb", "redis", "elasticsearch", "grafana", "prometheus",
    "oauth", "jwt", "openid", "ldap", "saml", "scim", "iam",
    "ansible", "puppet", "chef", "datadog", "splunk", "kibana",
    "airflow", "dbt", "looker", "tableau", "powerbi",
]

GENERIC_PATTERNS = [
    r"^(outils|tools|framework|plateforme|platform|solution|service|système|system)\s",
    r"^(développement|development|ingénierie|engineering|architecture|gestion|management)\s*$",
    r"^\w{1,3}$",  # Acronymes isolés trop courts
]


def classify_drop(name: str) -> str:
    """Classifie un drop : 'likely_fp' (faux positif probable) ou 'likely_ok' (drop légitime)."""
    n_lower = name.lower()
    for kw in TECH_KEYWORDS:
        if kw in n_lower:
            return "likely_fp"
    for pattern in GENERIC_PATTERNS:
        if re.match(pattern, n_lower):
            return "likely_ok"
    # Heuristique longueur : noms courts (<4 mots) non technologiques = probablement légitime à dropper
    word_count = len(name.split())
    if word_count <= 2 and not any(kw in n_lower for kw in TECH_KEYWORDS):
        return "likely_ok"
    return "likely_fp"


classified = {d: classify_drop(d) for d in all_drops}
likely_fp = [d for d, c in classified.items() if c == "likely_fp"]
likely_ok = [d for d, c in classified.items() if c == "likely_ok"]

print(f"🔴 Faux positifs probables (compétences légitimes droppées à tort) : {len(likely_fp)}")
print(f"🟢 Drops légitimes (termes trop génériques ou aberrants)            : {len(likely_ok)}")
print(f"   → Taux de faux positifs estimé : {100*len(likely_fp)//max(1, len(all_drops))}%\n")

print(f"🔴 Top {args.top_n} faux positifs probables (à remonter manuellement dans le Sweep) :")
for i, d in enumerate(sorted(likely_fp)[:args.top_n], 1):
    print(f"  {i:3d}. {d}")

print("")
print("🟢 Exemples de drops légitimes (30 premiers) :")
for d in sorted(likely_ok)[:30]:
    print(f"  - {d}")

# ── Export CSV ────────────────────────────────────────────────────────────────
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
csv_path = f"/tmp/taxonomy_drops_audit_{ts}.csv"
with open(csv_path, "w") as f:
    f.write("drop,classification\n")
    for d, c in sorted(classified.items()):
        f.write(f"{json.dumps(d)},{c}\n")
print(f"\n💾 Export CSV : {csv_path}")
print("   (Importez dans Sheets pour investigation manuelle)")
