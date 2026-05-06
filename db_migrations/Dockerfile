FROM liquibase/liquibase:5.0.2

USER root

# Copie du script de démarrage et des changelogs
# Note : deploy.sh build avec le contexte racine du monorepo (-f db_migrations/Dockerfile .)
# Les chemins COPY sont donc relatifs à la racine du monorepo.
COPY db_migrations/docker-entrypoint.sh /liquibase/docker-entrypoint.sh
COPY db_migrations/changelogs/ /liquibase/changelogs/

# Rendre le script exécutable et corriger les droits pour l'utilisateur non-root
RUN chmod +x /liquibase/docker-entrypoint.sh \
    && chown -R liquibase:liquibase /liquibase/changelogs /liquibase/docker-entrypoint.sh

# Revenir à l'utilisateur non-root (conforme aux golden rules)
USER liquibase

ENTRYPOINT ["/liquibase/docker-entrypoint.sh"]
