set -e
export PATH="/opt/homebrew/bin:$PATH"

# Etape 0: READMEs
git diff --name-only HEAD 2>/dev/null | grep -E "^[a-z_]+_api/|^agent_[a-z_]+/|^[a-z_]+_mcp/" | cut -d/ -f1 | sort -u | while read svc; do echo "=== $svc ==="; [ -f "$svc/README.md" ] && head -10 "$svc/README.md" || echo "MANQUANT"; done

# Etape 0b: py_compile
echo "=== py_compile : vérification syntaxique de tous les fichiers Python ==="
SYNTAX_ERRORS=$(find . -name "*.py" \
  -not -path "*/__pycache__/*" \
  -not -path "*/test_env/*" \
  -not -path "*/.venv/*" \
  -not -path "*/node_modules/*" \
  | xargs test_env/bin/python3 -m py_compile 2>&1 || true)
if echo "$SYNTAX_ERRORS" | grep -q "SyntaxError"; then
  echo "❌ BLOQUANT : Erreurs de syntaxe Python détectées :"
  echo "$SYNTAX_ERRORS"
  exit 1
else
  echo "✅ Aucune erreur de syntaxe — tous les fichiers Python sont valides."
fi

# Etape 1: run_tests.sh
bash scripts/run_tests.sh

# Etape 1b: Flake8
MODIFIED_PY=$(git diff --name-only --diff-filter=d HEAD 2>/dev/null | grep '\.py$') || true
if [ -n "$MODIFIED_PY" ]; then
  echo "=== Flake8 PEP8 check sur les fichiers modifiés ==="
  echo "$MODIFIED_PY" | xargs test_env/bin/python3 -m flake8 --max-line-length=120 --extend-ignore=W503,E501
  echo "✅ Aucune violation PEP8 — code conforme."
else
  echo "[+] Aucun fichier Python modifié — étape ignorée."
fi

# Etape 2: manage_env
test_env/bin/pytest platform-engineering/tests/test_manage_env.py -v --tb=short

# Etape 3: specs
test_env/bin/python3 scripts/generate_specs.py

# Etape 4: changelog
test_env/bin/python3 scripts/generate_changelog.py

# Etape 5: pipeline docs
test_env/bin/python3 scripts/generate_pipeline_docs.py

# Etape 6: readmes
test_env/bin/python3 scripts/generate_readmes.py

# Etape 7: terraform fmt
terraform -chdir=bootstrap fmt -recursive || true
terraform -chdir=platform-engineering/terraform fmt -recursive

# Etape 8: cleanup
rm -rf frontend/dist frontend/node_modules
rm -f */pytest.log */coverage.json *_test.db
rm -f *.tar.gz otelcol-contrib output.log *.patch patch_*.py

# Etape 9: git add
git add .

# Etape 10: Check secrets
if [ -f "secrets.sh" ]; then
  SECRETS=$(grep "export " secrets.sh | awk -F '=' '{print $2}' | tr -d '"'\'' ')
  for SECRET in $SECRETS; do
    if [ ${#SECRET} -gt 12 ]; then
      if git diff --cached HEAD 2>/dev/null | grep '^+' | grep -v '^+++' | grep -Fq "$SECRET"; then
        echo "[!] ERREUR CRITIQUE : Une valeur extraite de secrets.sh est sur le point d'être commitée. Opération annulée."
        exit 1
      fi
    fi
  done
  echo "[+] SÉCURITÉ : Aucun ajout de secret provenant de secrets.sh détecté, le commit est autorisé."
fi

echo "=== Vérification : aucun token GCP ni wheel buildé dans le staging ==="
if git diff --cached --name-only 2>/dev/null | grep -q "^shared/dist/"; then
  echo "[!] ERREUR CRITIQUE : shared/dist/"
  exit 1
fi
if git diff --cached --name-only 2>/dev/null | grep -qE "ar_token|\.ar_token$"; then
  echo "[!] ERREUR CRITIQUE : Un fichier token Artifact Registry est dans le staging. Retirez-le immédiatement."
  exit 1
fi
if git diff --cached 2>/dev/null | grep '^+' | grep -v '^+++' | grep -qE "oauth2accesstoken:[A-Za-z0-9_\-\.]{20,}"; then
  echo "[!] ERREUR CRITIQUE : Un token oauth2accesstoken GCP semble présent dans les fichiers stagés."
  exit 1
fi
echo "[+] SÉCURITÉ AR : Aucun token GCP ni wheel buildé détecté — commit autorisé."

# Etape 11: git commit
git commit -m "Fix silent exceptions and update APIs"
