#!/bin/bash

echo "--- DEBUT AUDIT ---"

# Fonctions utilitaires
check_file() {
    [ -f "$1" ] && echo "✅" || echo "❌"
}

check_grep() {
    grep -q "$1" "$2" 2>/dev/null && echo "✅" || echo "❌"
}

# Flake8 et Radon checks
echo "Install radon and flake8 if not exists..."
python3 -m pip install -q flake8 radon

for dir in *_api *_mcp; do
    [ -d "$dir" ] || continue
    echo "====================================="
    echo "SERVICE: $dir"
    echo "====================================="

    # 3.1. Règles communes
    MAIN_FILE="$dir/main.py"
    APP_FILE="$dir/mcp_app.py"
    if [ -f "$MAIN_FILE" ]; then
        FILE_TO_CHECK="$MAIN_FILE"
    elif [ -f "$APP_FILE" ]; then
        FILE_TO_CHECK="$APP_FILE"
    else
        FILE_TO_CHECK=""
    fi

    echo "Observabilité (Instrumentator): $(check_grep "Instrumentator().instrument(app).expose(app)" "$FILE_TO_CHECK")"
    echo "Traçabilité (FastAPIInstrumentor): $(check_grep "FastAPIInstrumentor.instrument_app" "$FILE_TO_CHECK")"
    echo "Versioning (VERSION file): $(check_file "$dir/VERSION")"
    
    # Models IA hardcoded (gemini-*)
    HARDCODED=$(grep -rE "gemini-[0-9]" "$dir/src" "$dir/main.py" "$dir/mcp_app.py" 2>/dev/null | grep -v "test" | wc -l)
    if [ "$HARDCODED" -gt 0 ]; then echo "Modèles IA (Hardcoded): ❌ ($HARDCODED trouvés)"; else echo "Modèles IA (Hardcoded): ✅"; fi

    # Container Contract
    DOCKERFILE="$dir/Dockerfile"
    echo "Container Contract (Dockerfile): $(check_file "$DOCKERFILE")"
    if [ -f "$DOCKERFILE" ]; then
        echo "  - USER non-root: $(check_grep "USER" "$DOCKERFILE")"
        echo "  - CMD sans shell: $(check_grep 'CMD \["' "$DOCKERFILE")"
    fi
    echo "Container Contract (.dockerignore): $(check_file "$dir/.dockerignore")"

    # Taille fichiers
    BIG_FILES=$(find "$dir/src" -name "*.py" 2>/dev/null | xargs wc -l 2>/dev/null | awk '$1 > 400 && $2 != "total" {print $2}' | wc -l | xargs)
    if [ "$BIG_FILES" -gt 0 ]; then
        echo "Taille des fichiers Python (<400L): ❌ ($BIG_FILES fichiers > 400L)"
    else
        echo "Taille des fichiers Python (<400L): ✅"
    fi

    # 3.2 & 3.3 Zero-Trust
    # Pour APIs Data ou Agents
    echo "Zero-Trust (Depends(verify_jwt)): $(grep -rE "Depends\(verify_jwt\)" "$dir" 2>/dev/null | wc -l | awk '{if($1>0) print "✅"; else print "❌"}')"
    
    # Injection Headers
    echo "Traçabilité sortante (inject(headers)): $(grep -rE "inject\(headers\)" "$dir" 2>/dev/null | wc -l | awk '{if($1>0) print "✅"; else print "❌"}')"
    
    # MCP
    MCP_FILE="$dir/mcp_server.py"
    if [[ "$dir" == *"agent_"* ]]; then
        echo "Interdiction MCP (mcp_server.py absent): $([ ! -f "$MCP_FILE" ] && echo "✅" || echo "❌")"
        echo "Code Mutualisé (agent_commons): $(grep -rE "from agent_commons" "$dir" 2>/dev/null | wc -l | awk '{if($1>0) print "✅"; else print "❌"}')"
    else
        echo "Interface MCP (mcp_server.py): $(check_file "$MCP_FILE")"
        echo "Proxy MCP (/mcp/{path}): $(check_grep "/mcp/{path" "$FILE_TO_CHECK")"
    fi
    
    echo "Golden Pattern Erreur (report to prompts_api): $(grep -rE "report_exception_to_prompts_api|app.exception_handler" "$dir" 2>/dev/null | wc -l | awk '{if($1>0) print "✅"; else print "❌"}')"

    # Readiness
    if [ -f "$dir/database.py" ] || [ -f "$dir/src/database.py" ]; then
        DB_FILE="$dir/database.py"
        [ -f "$dir/src/database.py" ] && DB_FILE="$dir/src/database.py"
        echo "Readiness Anti-Pool-Starvation (timeout=5.0): $(check_grep "timeout=5.0" "$DB_FILE")"
    fi
    
done

echo "--- FIN AUDIT ---"
