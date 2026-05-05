from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.cvs.schemas import PaginationResponse, CVProfileResponse

app = FastAPI()

@app.get("/dict", response_model=PaginationResponse[dict])
def get_dict():
    return {"items": [{"a": 1}], "total": 1, "skip": 0, "limit": 10}

@app.get("/cv", response_model=PaginationResponse[CVProfileResponse])
def get_cv():
    return {
        "items": [
            CVProfileResponse(user_id=1, source_url=None)
        ],
        "total": 1, "skip": 0, "limit": 10
    }

client = TestClient(app)

print("GET /dict:", client.get("/dict").status_code, client.get("/dict").json())
print("GET /cv:", client.get("/cv").status_code, client.get("/cv").json())

