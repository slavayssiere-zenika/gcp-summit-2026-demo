FROM grafana/grafana:10.4.0

# Positionne le port sur 8080 pour Cloud Run
ENV GF_SERVER_HTTP_PORT=8080

# Désactive les privilèges root (UID 472 est l'utilisateur grafana par défaut)
USER 472

# Installer le plugin Google Cloud Logging (non-fourni de base)
RUN grafana-cli plugins install googlecloud-logging-datasource

# Copier le provisioning des datasources et des dashboards
COPY grafana/provisioning /etc/grafana/provisioning
COPY grafana/dashboards /etc/grafana/dashboards

# Exposer le port de Cloud Run
EXPOSE 8080
