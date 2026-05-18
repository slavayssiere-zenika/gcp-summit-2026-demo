FROM locustio/locust

# Ajout de pydantic pour valider les contrats d interface via shared/schemas/.
# Le repertoire shared/ est monte en volume (PYTHONPATH=/shared) dans docker-compose.
USER root
RUN pip install --no-cache-dir pydantic
USER locust
