from fastapi.testclient import TestClient
from main import app
import json

client = TestClient(app)
response = client.get("/cv-api/user/2/missions")
print("Status:", response.status_code)
print("Data:", json.dumps(response.json(), indent=2))
