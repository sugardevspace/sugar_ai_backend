from typing import List, Optional
from pydantic import BaseModel, Field


class ImportantEvent(BaseModel):
    date: str  # YYYY-MM-DD
    title: str
    description: str
    reason: Optional[str] = None


class Promise(BaseModel):
    date: str  # YYYY-MM-DD
    content: str


class UserPersona(BaseModel):
    name: Optional[str] = None
    nickname: Optional[List[str]] = None
    birthday: Optional[str] = None  # YYYY-MM-DD
    age: Optional[int] = None
    profession: Optional[str] = None
    gender: Optional[str] = None
    personality: Optional[List[str]] = None
    likesDislikes: Optional[List[str]] = None
    promises: List[Promise] = Field(default_factory=list)
    importantEvent: List[ImportantEvent] = Field(default_factory=list)
