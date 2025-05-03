from fastapi import APIRouter, Depends
from core.dependencies.auth import verify_token

router = APIRouter(prefix="/api", tags=["test"])


@router.get("/test")
async def api_test(user: dict = Depends(verify_token)):
    return {"status": "ok", "uid": user["uid"], "email": user.get("email"), "message": "Token 驗證成功！"}
