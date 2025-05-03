# plugins/stream_chat_plugin/utils/stream_chat_utils.py
from typing import Dict, Any, List, Tuple
from stream_chat import StreamChat
import logging

logger = logging.getLogger(__name__)


def create_ai_user(chat_client: StreamChat,
                   user_id: str,
                   user_name: str,
                   user_image: str = "",
                   additional_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """在 Stream Chat 中創建 AI 用戶

    Args:
        api_key: Stream Chat API 金鑰
        api_secret: Stream Chat API 密鑰
        user_id: AI 用戶的 ID
        user_name: AI 用戶的名稱
        user_image: AI 用戶的頭像 URL
        additional_data: 額外的用戶數據

    Returns:
        包含操作狀態的字典
    """
    logger = logging.getLogger(__name__)

    try:

        # 準備用戶數據
        user_data = {
            "id": user_id,
            "name": user_name,
        }

        if user_image:
            user_data["image"] = user_image

        # 添加額外數據
        if additional_data:
            user_data.update(additional_data)

        # 創建用戶
        response = chat_client.upsert_user(user_data)

        logger.info(f"成功創建 AI 用戶: {user_id}")
        return {"status": "success", "user": response}

    except Exception as e:
        logger.error(f"創建 AI 用戶失敗: {str(e)}")
        return {"status": "error", "reason": str(e)}


def is_ai_message(user_id: str) -> bool:
    """判斷是否是 AI 角色發送的消息"""
    # 這裡實現具體的邏輯，判斷 user_id 是否為 AI 角色
    # 例如檢查 user_id 前綴、查詢資料庫等
    # 簡單示例: 假設 AI 用戶 ID 以 'ai-' 開頭
    return user_id and user_id.startswith('ai-')


def get_receiver_user_id(members: list, sender_user_id: str):
    """"取得接收者的id"""
    for member in members:
        if member['user_id'] != sender_user_id:
            return member['user_id']


def get_character_id(members: list) -> str:
    """
    First prints all members, then extracts user_id that starts with 'ai-' from the list.

    Args:
        members: A list of member dictionaries containing 'user_id' keys

    Returns:
        The user_id string if found, otherwise an empty string
    """
    for member in members:
        if member.get('user_id', '').startswith("ai-"):
            ai_id = member['user_id']
            print(f"找到 AI ID: {ai_id}")
            return ai_id
    print("未找到以 ai- 開頭的 ID")
    return ''


def identify_channel_members(members: List[Dict[str, Any]]) -> Tuple[str, str, str, str]:
    """
    從成員列表中識別 AI 和人類用戶
    
    Args:
        members: 頻道成員列表
        
    Returns:
        Tuple[str, str, str, str]: (ai_user_id, human_user_id, ai_name, user_name)
    """
    ai_user_id = None
    human_user_id = None
    ai_name = "AI"
    user_name = "用戶"

    for member in members:
        user_info = member.get("user", {})
        user_id = member.get("user_id") or user_info.get("id")

        if not user_id:
            continue

        if user_id.startswith("ai-"):
            ai_user_id = user_id
            ai_name = user_info.get("name") or user_info.get("first_name") or ai_name
        else:
            human_user_id = user_id
            user_name = user_info.get("name") or user_info.get("first_name") or user_name

    return ai_user_id, human_user_id, ai_name, user_name
