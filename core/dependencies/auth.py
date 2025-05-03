from fastapi import Request, Header, HTTPException
from services.async_firebase_service import AsyncFirebaseService


async def verify_token(request: Request, authorization: str = Header(..., description="Bearer <Firebase ID Token>")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少或無效的 Authorization header")
    id_token = authorization.split(" ", 1)[1]
    firebase_svc: AsyncFirebaseService = request.app.state.services["firebase"]
    decoded = await firebase_svc.verify_id_token(id_token)
    if not decoded:
        raise HTTPException(401, "Token 驗證失敗")
    return decoded
