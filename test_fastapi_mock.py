import asyncio
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

app = FastAPI()

async def get_db():
    yield "real_db"

@app.get("/")
async def root(db=Depends(get_db)):
    res = (await db.execute("foo")).scalars().first()
    return {"res": res}

mock_db = AsyncMock()
mock_result = MagicMock()
mock_result.scalars.return_value.first.return_value = "hello"
mock_db.execute.return_value = mock_result

app.dependency_overrides[get_db] = lambda: mock_db

client = TestClient(app)
try:
    response = client.get("/")
    print(response.json())
except Exception as e:
    import traceback
    traceback.print_exc()
