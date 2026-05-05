from src.cvs.schemas import CVProfileResponse, PaginationResponse

try:
    CVProfileResponse(user_id=1, source_url=None)
    print("CVProfileResponse with source_url=None passed")
except Exception as e:
    print("CVProfileResponse failed:", e)

try:
    pr = PaginationResponse[dict](items=[{"title": "Dev", "company": "Zenika", "competencies": []}], total=1, skip=0, limit=10)
    print("PaginationResponse[dict] passed:", pr.model_dump())
except Exception as e:
    print("PaginationResponse[dict] failed:", e)
