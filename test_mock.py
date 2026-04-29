import asyncio
from unittest.mock import AsyncMock

async def main():
    mock_db = AsyncMock()
    mock_db.execute.return_value.all.return_value = [(1, "Contenu brut CV", 42)]
    
    res = await mock_db.execute()
    rows = res.all()
    print(rows)
    for a, b, c in rows:
        print(a, b, c)

asyncio.run(main())
