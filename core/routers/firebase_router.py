from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.security import APIKeyHeader
import logging
from config.settings import settings

# Initialize router and auth
router = APIRouter(prefix="/api", tags=['cache'])
api_key_header = APIKeyHeader(name="X-API-Key")
logger = logging.getLogger("api_router")

# Auth dependency
async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.API_KEY:  # Move this to settings.py later
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return api_key

# Add this with your other endpoint definitions
@router.post("/firebase/restart")
async def restart_firebase(request: Request, api_key: str = Depends(api_key_header)):
    """Restart Firebase service and reload credentials"""
    # Verify API key
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    try:
        # Get firebase service from app state
        firebase_service = request.app.state.services.get("firebase")
        
        if not firebase_service:
            return {"status": "error", "reason": "Firebase service not found"}
        
        # Restart the service
        status = await firebase_service.restart_service()
        
        return status
            
    except Exception as e:
        logger.error(f"Error restarting Firebase service: {e}")
        return {"status": "error", "reason": str(e)}