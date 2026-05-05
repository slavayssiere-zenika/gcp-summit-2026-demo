#!/bin/bash
echo "=== AUDIT OF SERVICES ==="
SERVICES="competencies_api cv_api drive_api items_api missions_api prompts_api users_api agent_hr_api agent_missions_api agent_ops_api agent_router_api analytics_mcp monitoring_mcp"

for svc in $SERVICES; do
  echo ">>> Auditing $svc"
  cd $svc
  
  echo "3.1. Observabilité: "
  grep -q "Instrumentator().instrument(app).expose(app)" main.py mcp_server.py mcp_app.py 2>/dev/null && echo "✅" || echo "❌"
  
  echo "3.1. Traçabilité: "
  grep -q "FastAPIInstrumentor.instrument_app(app" main.py mcp_server.py mcp_app.py 2>/dev/null && echo "✅" || echo "❌"
  
  echo "3.1. Versioning: "
  [ -f "VERSION" ] && echo "✅" || echo "❌"
  
  echo "3.1. Modèles IA (pas hardcodé): "
  grep -rnE "(gemini-[0-9.]+-(pro|flash)|claude-[0-9.]+)" src/ 2>/dev/null && echo "❌" || echo "✅"
  
  echo "3.1. Container Contract: "
  if [ -f "Dockerfile" ]; then
    grep -q "AS builder" Dockerfile && grep -q "USER " Dockerfile && grep -q 'CMD \[.*python3' Dockerfile && [ -f ".dockerignore" ] && echo "✅" || echo "❌"
  else
    echo "❌ No Dockerfile"
  fi
  
  echo "3.1. Gestion des erreurs (pas de except Exception: pass): "
  grep -rn "except Exception: pass" src/ 2>/dev/null && echo "❌" || echo "✅"

  echo "3.1. Bonnes Pratiques Cloud Run (PYTHONUNBUFFERED): "
  grep -q "ENV PYTHONUNBUFFERED=1" Dockerfile 2>/dev/null && echo "✅" || echo "❌"

  echo "3.1. Anti-Fallback JWT: "
  grep -rnE "SECRET_KEY.*=.*None|return.*sub.*dev-user" src/ main.py agent.py 2>/dev/null && echo "❌" || echo "✅"

  echo "3.1. Taille des fichiers Python (400 lignes max): "
  # Exclude test files
  LARGE_FILES=$(find src/ main.py agent.py mcp_server.py mcp_app.py -name "*.py" 2>/dev/null | grep -v "test_" | xargs wc -l 2>/dev/null | awk '$1 > 400 {print $2}' | grep -v "total")
  if [ -z "$LARGE_FILES" ]; then echo "✅"; else echo "❌ $LARGE_FILES"; fi

  echo "3.1. Pagination lors de la consommation d'APIs: "
  grep -rn "\.list(" src/ main.py agent.py 2>/dev/null | grep -v "pageToken" | grep "\.execute()" && echo "❌" || echo "✅"

  echo "3.1. Contrats d'interface inter-services: "
  grep -rn '\.json()\.\.get(\|res\.json()\.get(' src/ main.py agent.py 2>/dev/null | grep -v '# Contrat intentionnel' | grep -v '# Fallback intentionnel' && echo "❌" || echo "✅"

  echo "3.2 / 3.3 Zero-Trust (verify_jwt): "
  grep -q "verify_jwt" main.py mcp_app.py 2>/dev/null && echo "✅" || echo "❌"

  cd ..
done
