from fastapi import FastAPI
from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar("T")

class PaginationResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int

class User(BaseModel):
    name: str

app = FastAPI()

@app.get("/users", response_model=PaginationResponse)
def get_users():
    return {"items": [{"name": "Seb"}], "total": 1, "skip": 0, "limit": 10}

from fastapi.testclient import TestClient
client = TestClient(app)
try:
    resp = client.get("/users")
    print("Status:", resp.status_code)
    print("Text:", resp.text)
except Exception as e:
    print("Exception:", e)
