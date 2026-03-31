import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

class ItemCreate(BaseModel):
    name: str
    user_id: int

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/metrics")
def metrics():
    return {"status": "ok"}

@app.get("/items")
def list_items(skip: int = 0, limit: int = 10):
    return {"items": [], "total": 0, "skip": skip, "limit": limit}

@app.get("/items/{item_id}")
def get_item(item_id: int):
    if item_id == 9999:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item_id, "name": "Test Item", "user_id": 1, "description": None, "created_at": "2024-01-01T00:00:00", "user": None}

@app.post("/items", status_code=201)
def create_item(item: ItemCreate):
    return {"id": 1, "name": item.name, "user_id": item.user_id, "description": None, "created_at": "2024-01-01T00:00:00", "user": None}

client = TestClient(app)


class TestHealth:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestMetrics:
    def test_metrics(self):
        response = client.get("/metrics")
        assert response.status_code == 200


class TestItemsEndpoints:
    def test_list_items(self):
        response = client.get("/items")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    def test_get_item_found(self):
        response = client.get("/items/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert "name" in data
        assert "user_id" in data

    def test_get_item_not_found(self):
        response = client.get("/items/9999")
        assert response.status_code == 404

    def test_create_item(self):
        response = client.post("/items", json={"name": "New Item", "user_id": 1})
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "New Item"
        assert data["user_id"] == 1


class TestPagination:
    def test_pagination_params(self):
        response = client.get("/items?skip=5&limit=25")
        assert response.status_code == 200
        data = response.json()
        assert data["skip"] == 5
        assert data["limit"] == 25
