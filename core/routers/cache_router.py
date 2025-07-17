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

@router.post("/cache/clear")
async def clear_cache(request: Request, api_key: str = Depends(verify_api_key)):
    """Clear all caches in ChatCacheService"""
    try:
        chat_cache_service = request.app.state.services.get("chat_cache")
        
        if not chat_cache_service:
            return {"status": "error", "reason": "Chat cache service not found"}

        # Clear all TTL caches
        chat_cache_service.message_cache.clear()
        chat_cache_service.user_channel_data_cache.clear()
        chat_cache_service._processed_messages.clear()
        chat_cache_service.character_cache.clear()

        logger.info("All caches cleared successfully")
        return {"status": "success", "message": "All caches cleared"}
    except Exception as e:
        logger.error(f"Error clearing caches: {e}")
        return {"status": "error", "reason": str(e)}

@router.get("/cache/status")
async def get_cache_status(request: Request, api_key: str = Depends(verify_api_key)):
    """Get detailed status of all caches in ChatCacheService"""
    try:
        chat_cache_service = request.app.state.services.get("chat_cache")
        
        if not chat_cache_service:
            return {"status": "error", "reason": "Chat cache service not found"}

        cache_stats = {
            "message_cache": {
                "current_size": len(chat_cache_service.message_cache),
                "max_size": chat_cache_service.MAX_CACHE_SIZE,
                "ttl_seconds": chat_cache_service.TTL_SECONDS,
                "usage_percentage": (len(chat_cache_service.message_cache) / chat_cache_service.MAX_CACHE_SIZE) * 100
            },
            "user_channel_data_cache": {
                "current_size": len(chat_cache_service.user_channel_data_cache),
                "max_size": chat_cache_service.MAX_CACHE_SIZE,
                "ttl_seconds": chat_cache_service.TTL_SECONDS,
                "usage_percentage": (len(chat_cache_service.user_channel_data_cache) / chat_cache_service.MAX_CACHE_SIZE) * 100
            },
            "processed_messages": {
                "current_size": len(chat_cache_service._processed_messages),
                "max_size": 5000,
                "ttl_seconds": chat_cache_service.PROCESSED_REQUEST_TTL,
                "usage_percentage": (len(chat_cache_service._processed_messages) / 5000) * 100
            },
            "character_cache": {
                "current_size": len(chat_cache_service.character_cache),
                "max_size": 50,
                "ttl_seconds": 86400,
                "usage_percentage": (len(chat_cache_service.character_cache) / 50) * 100
            }
        }

        for cache_name, stats in cache_stats.items():
            ttl_hours = stats["ttl_seconds"] / 3600
            stats["ttl_human"] = f"{ttl_hours:.1f} hours"

        logger.info("Cache status retrieved successfully")
        return {
            "status": "success",
            "cache_stats": cache_stats
        }
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        return {"status": "error", "reason": str(e)}