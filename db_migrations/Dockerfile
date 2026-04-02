FROM liquibase/liquibase:4.30.0

USER root

# Copie du script de démarrage et des changelogs
COPY docker-entrypoint.sh /liquibase/docker-entrypoint.sh
COPY changelogs/ /liquibase/changelogs/

# Rendre le script exécutable et corriger les droits pour l'utilisateur non-root
RUN chmod +x /liquibase/docker-entrypoint.sh \
    && chown -R liquibase:liquibase /liquibase/changelogs /liquibase/docker-entrypoint.sh

# Revenir à l'utilisateur non-root (conforme aux golden rules)
USER liquibase

ENTRYPOINT ["/liquibase/docker-entrypoint.sh"]
