from fastapi import APIRouter, Depends
from core.dependencies.auth import verify_token
from core.models.levels_model import NotifyLevelRequest, NotifyLevelResponse
from plugins.plugin_manager import PluginManager, get_plugin_manager

router = APIRouter(prefix="/api", tags=["levels"])


@router.post("/levels/notify", response_model=NotifyLevelResponse)
async def notify_level(
        body: NotifyLevelRequest,
        user: dict = Depends(verify_token),
        pm: PluginManager = Depends(get_plugin_manager),
):
    event_data = {
        "user_id": user["uid"],
        "channel_id": body.channel_id,
        "level": body.level,
    }

    result = await pm.handle_event(event_type="notify_level", event_data=event_data, target_plugin="async_level_plugin")

    return NotifyLevelResponse(status="success", details=result)
