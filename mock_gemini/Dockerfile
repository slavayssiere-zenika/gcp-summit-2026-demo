FROM python:3.13-slim

WORKDIR /app

# Install dependencies in one layer
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx

COPY main.py .

EXPOSE 8099

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099", "--workers", "4"]
