import logging
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from core.routers.levels_router import router as levels_router_router
from core.routers.test_router import router as test_router
from plugins.plugin_manager import PluginManager
from config.settings import settings
from services.auto_registry import AutoServiceRegistry

# 設定日誌
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s - %(module)s:%(lineno)d - %(levelname)s - %(message)s")
                    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")

    # 初始化服務（非同步）
    services = await AutoServiceRegistry.load_services_from_config()

    # 初始化插件管理器
    plugin_manager = PluginManager()

    # 自動註冊所有 service
    for name, service in services.items():
        plugin_manager.register_service(name, service)

    # 載入所有插件
    await plugin_manager.load_plugins()

    # 將服務和插件管理器存儲在應用程序狀態中
    app.state.services = services
    app.state.plugin_manager = plugin_manager

    yield

    logger.info("Shutting down application...")
    # 關閉非同步服務
    for s in services.values():
        if hasattr(s, 'close') and callable(s.close):
            close_func = s.close
            if hasattr(close_func, '__await__'):
                await close_func()


# 創建 FastAPI 應用，使用 lifespan
app = FastAPI(title="Sugar AI Backend", lifespan=lifespan)
app.include_router(test_router)
app.include_router(levels_router_router)


@app.post("/webhook/stream-chat")
async def stream_chat_webhook(request: Request):
    """處理來自 Stream Chat 的 webhook 請求"""
    try:
        # 解析請求數據
        webhook_data = await request.json()

        # 從請求中獲取事件類型
        event_type = webhook_data.get("type", "unknown")
        logger.info(f"收到 Stream Chat webhook: {event_type}")

        # 使用 StreamChatPlugin 處理事件
        result = await request.app.state.plugin_manager.handle_event(event_type=event_type,
                                                                     event_data=webhook_data,
                                                                     target_plugin="async_stream_chat_plugin")

        return result.get("async_stream_chat_plugin", {"status": "error", "reason": "插件未回應"})
    except Exception as e:
        logger.error(f"處理 webhook 時發生錯誤: {e}")
        return {"status": "error", "reason": str(e)}


@app.post("/api/character/create")
async def create_ai_character(request: Request):
    """創建 AI 角色"""
    try:
        # 解析請求數據
        data = await request.json()

        # 使用 StreamChatPlugin 處理創建請求
        result = await request.app.state.plugin_manager.handle_event(
            event_type="create_character",
            event_data=data,
            target_plugin="async_stream_chat_plugin"  # 注意：使用非同步版本的插件名稱
        )

        return result.get("async_stream_chat_plugin", {"status": "error", "reason": "插件未回應"})
    except Exception as e:
        logger.error(f"處理創建 AI 角色請求時發生錯誤: {e}")
        return {"status": "error", "reason": str(e)}


@app.get("/plugins")
async def list_plugins(request: Request):
    """列出所有已載入的插件及其狀態"""
    return await request.app.state.plugin_manager.list_plugins()


@app.get("/services")
async def list_services(request: Request):
    # 回傳所有註冊到 app.state.services 裡面的 key list
    return {"available_services": list(request.app.state.services.keys())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
