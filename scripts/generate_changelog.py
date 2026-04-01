import json
import os
from datetime import datetime

apis = ["agent_api", "competencies_api", "cv_api", "items_api", "prompts_api", "users_api"]
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

new_entry = f"{header}\n### Couverture de Code\n\n{table}\n\n---\n\n"

with open(changelog_path, "w", encoding="utf-8") as f:
    f.write(new_entry + existing_content)

print(f"Changelog mis à jour avec la couverture de {len(apis)} microservices.")
