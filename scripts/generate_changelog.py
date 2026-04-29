import json
import os
import subprocess
from datetime import datetime

def get_recent_changes():
    try:
        commits = subprocess.check_output(["git", "log", "origin/main..HEAD", "--pretty=format:- %s"]).decode("utf-8").strip()
    except Exception:
        commits = ""
        
    try:
        status = subprocess.check_output(["git", "status", "-s"]).decode("utf-8").strip()
    except Exception:
        status = ""
        
    changes = []
    if commits:
        changes.append("#### Commits non pushés\n" + commits)
    else:
        changes.append("#### Commits non pushés\n- Aucun commit local en attente")
        
    if status:
        files = "\n".join(["- `" + line[3:] + "` (" + line[:2].strip() + ")" for line in status.split("\n")])
        changes.append("#### Fichiers (non commités)\n" + files)
        
    return "\n\n".join(changes)

def get_test_dirs():
    dirs = []
    for entry in os.scandir("."):
        if entry.is_dir() and entry.name not in ["test_env", "frontend", "bootstrap"] and not entry.name.startswith("."):
            has_tests = False
            for root, _, files in os.walk(entry.path):
                # Don't go too deep, 3 levels max
                if root.count(os.sep) - entry.path.count(os.sep) > 3:
                    continue
                if any((f.startswith("test_") or f.endswith("_test.py")) and f.endswith(".py") for f in files) or "pytest.ini" in files:
                    has_tests = True
                    break
            if has_tests:
                dirs.append(entry.name)
    return sorted(dirs)

apis = get_test_dirs()
table_rows = []

for api in apis:
    path = os.path.join(api, "coverage.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            t = data.get("totals", {})
            stmts = t.get("num_statements", "N/A")
            # pytest-cov coverage.json usually has missing_lines
            # but sometimes missing_branches, we just use missing_lines
            miss = t.get("missing_lines", "N/A")
            pct = t.get("percent_covered_display", "0")
            table_rows.append(f"| {api:<16} | {stmts:<5} | {miss:<4} | {pct:>3}% |")
    except Exception as e:
        table_rows.append(f"| {api:<16} | N/A   | N/A  | N/A  |")

table = (
    "| Microservice     | Stmts | Miss | Cover |\n"
    "|------------------|-------|------|-------|\n" +
    "\n".join(table_rows)
)

today = datetime.now().strftime("%Y-%m-%d")

changelog_path = "changelog.md"
existing_content = ""
if os.path.exists(changelog_path):
    with open(changelog_path, "r", encoding="utf-8") as f:
        existing_content = f.read()

# Pour éviter de dupliquer la date si plusieurs push le même jour, 
# on ajoute l'heure ou on recrée simplement le bloc en en-tête.
now = datetime.now().strftime("%H:%M:%S")
header = f"## Mise à jour automatique - {today} {now}\n"

summary_text = os.environ.get("CHANGELOG_SUMMARY", "")
if summary_text:
    summary_text = f"### Résumé des Changements\n\n{summary_text}\n\n"

new_entry = f"{header}\n{summary_text}### Couverture de Code\n\n{table}\n\n### Modifications depuis le dernier push\n\n{get_recent_changes()}\n\n---\n\n"

with open(changelog_path, "w", encoding="utf-8") as f:
    f.write(new_entry + existing_content)

print(f"Changelog mis à jour avec la couverture de {len(apis)} microservices.")
