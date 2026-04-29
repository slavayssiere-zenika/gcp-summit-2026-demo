import asyncio
from sqlalchemy import create_engine, text

engine = create_engine("postgresql://admin:admin123@localhost:5432/cv_api_db")
with engine.connect() as conn:
    result = conn.execute(text("SELECT user_id, source_tag, created_at FROM cv_profiles ORDER BY user_id, created_at DESC"))
    for row in result:
        print(f"User {row[0]}: {row[1]} ({row[2]})")
