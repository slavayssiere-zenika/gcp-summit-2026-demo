# Items API

## Code Coverage

```
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
cache.py                   30     30     0%   1-40
database.py                15     15     0%   1-22
main.py                    43     43     0%   1-78
src/__init__.py             0      0   100%
src/items/__init__.py       0      0   100%
src/items/models.py        11     11     0%   1-15
src/items/router.py        67     67     0%   1-107
src/items/schemas.py       26     26     0%   1-38
-----------------------------------------------------
TOTAL                     192    192     0%
```

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /items | List items (paginated) |
| GET | /items/{id} | Get item by ID |
| POST | /items | Create item (requires user_id) |
| GET | /health | Health check |
| GET | /metrics | Prometheus metrics |

## Pagination

```
GET /items?skip=0&limit=10
```

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001
```
