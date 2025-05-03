from pydantic import BaseModel


class NotifyLevelRequest(BaseModel):
    channel_id: str
    level: int


class NotifyLevelResponse(BaseModel):
    status: str
    details: dict  # 回傳 plugin 處理結果
