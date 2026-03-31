FROM python:3.11-slim

WORKDIR /app

COPY agent_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY users_api/ ./users_api/
COPY items_api/ ./items_api/
COPY competencies_api/ ./competencies_api/
COPY agent_api/ ./agent_api/

ENV PYTHONPATH=/app
ENV USERS_API_URL=http://users_api:8000
ENV ITEMS_API_URL=http://items_api:8001

EXPOSE 8002

CMD ["uvicorn", "agent_api.main:app", "--host", "0.0.0.0", "--port", "8002"]
