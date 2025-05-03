from typing import List, Optional
from pydantic import BaseModel


class Message(BaseModel):
    """聊天訊息模型"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """聊天完成請求模型"""
    model: Optional[str]
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 20000
    top_p: Optional[float] = 0.95
    response_format: Optional[str] = "story"
