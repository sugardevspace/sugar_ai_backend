from typing import Optional


def extract_ai_id(channel_id: str) -> Optional[str]:
    """
    從 channel_id 中提取 ai-XXXX 部分
    Args:
        channel_id (str): 格式為 "XXXXXXX-ai-XXXX" 的頻道 ID
    Returns:
        str: 提取出的 "ai-XXXX" 部分，如果沒有找到則返回 None
    """
    if not channel_id or not isinstance(channel_id, str):
        return None

    # 使用 split 方法按 "-" 分割字串
    parts = channel_id.split("-")

    # 查找 "ai" 的位置
    try:
        ai_index = parts.index("ai")
        # 如果找到 "ai"，則返回 "ai-XXXX" 格式
        if ai_index < len(parts) - 1:
            return f"ai-{parts[ai_index + 1]}"
        else:
            return "ai"  # 如果 "ai" 是最後一部分
    except ValueError:
        # 如果沒有找到 "ai"
        return None
