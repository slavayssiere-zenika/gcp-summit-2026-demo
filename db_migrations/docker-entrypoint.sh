#!/bin/bash
set -e

# Variables requises: DB_HOST, DB_USER, DB_PASSWORD
export DB_HOST=${DB_HOST:-postgres}
export DB_USER=${DB_USER:-postgres}
export DB_PASSWORD=${DB_PASSWORD:-postgres}

# Liste des bases de données de nos microservices
SERVICES="users items competencies cv prompts drive"

echo "Démarrage des migrations Liquibase..."

for SVC in $SERVICES; do
  echo ">>> Traitement de la base de données: $SVC"
  URL="jdbc:postgresql://${DB_HOST}:5432/${SVC}"
  
  if [ -f "/liquibase/changelogs/${SVC}/changelog.yaml" ]; then
    liquibase \
      --url="${URL}" \
      --username="${DB_USER}" \
      --password="${DB_PASSWORD}" \
      --changeLogFile="changelogs/${SVC}/changelog.yaml" \
      update || {
        echo "❌ [FAILFAST] ERREUR CRITIQUE: La migration Liquibase pour la base de données '$SVC' a échoué!" >&2
        exit 1
      }
  else
    echo "Aucun changelog trouvé pour ${SVC}. Passage..."
  fi
done

echo "✅ Toutes les migrations ont été appliquées avec succès."
