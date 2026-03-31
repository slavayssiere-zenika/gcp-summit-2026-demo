# Users API

## Code Coverage

```
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
cache.py                   30     30     0%   1-40
database.py                15     15     0%   1-22
main.py                    48     48     0%   1-95
src/__init__.py             0      0   100%
src/users/__init__.py       0      0   100%
src/users/models.py        12     12     0%   1-16
src/users/router.py        62     62     0%   1-97
src/users/schemas.py       25     25     0%   1-37
-----------------------------------------------------
TOTAL                     192    192     0%
```

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /users | List users (paginated) |
| GET | /users/{id} | Get user by ID |
| POST | /users | Create user |
| PUT | /users/{id} | Update user |
| DELETE | /users/{id} | Delete user |
| GET | /health | Health check |
| GET | /metrics | Prometheus metrics |

## Pagination

```
GET /users?skip=0&limit=10
```

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
