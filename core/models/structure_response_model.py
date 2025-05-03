from pydantic import BaseModel, Field


class ChatMessageResponse(BaseModel):
    message: str = Field(description="角色回覆內容", min_length=1, max_length=100)
    # intimacy: int = Field(description="角色親密度變化值", ge=-5, le=5)


class StoryMessageResponse(BaseModel):
    message: str = Field(description="角色回覆內容", min_length=1, max_length=100)
    action_mood: str = Field(description="角色語氣或搭配的動作描述", min_length=10, max_length=100)
    # intimacy: int = Field(description="角色親密度變化值", ge=-5, le=5)


class StimulationResponse(BaseModel):
    message: str = Field(description="角色回覆內容", min_length=1, max_length=100)
    action_mood: str = Field(description="角色語氣或搭配的動作描述", min_length=10, max_length=100)
    # intimacy: int = Field(description="角色親密度變化值", ge=-5, le=5)


class IntimacyResponse(BaseModel):
    intimacy: int = Field(description="角色親密度變化值", ge=-5, le=5)
