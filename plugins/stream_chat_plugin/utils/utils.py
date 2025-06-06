from typing import Any, Dict


def get_current_level_title(levels: Dict[str, Dict[str, Any]], total_intimacy: int) -> str:
    matched_title = ""
    max_level = -1

    for key, value in levels.items():
        if total_intimacy >= value.get("intimacy", 0) and int(key) > max_level:
            max_level = int(key)
            matched_title = value.get("title", "")

    return matched_title


def get_next_level_title(levels: Dict[str, Dict[str, Any]], total_intimacy: int) -> str:
    next_candidates = []
    highest_level = ("", 0, "")  # (level_key, intimacy, title)

    for key, value in levels.items():
        intimacy = value.get("intimacy", 0)
        title = value.get("title", "")

        # 記錄最高等級
        if intimacy > highest_level[1]:
            highest_level = (key, intimacy, title)

        # 尋找下一個等級的候選項
        if total_intimacy < intimacy:
            next_candidates.append((intimacy, title))

    # 如果有下一個等級的候選項，返回最接近的
    if next_candidates:
        return sorted(next_candidates)[0][1]

    # 如果沒有更高等級，返回最高等級的標題
    return highest_level[2]


def collect_usage(result: Any) -> Dict[str, Any]:
    """
    擷取 model 及 usage，若缺則全部給預設值。
    """
    if isinstance(result, dict) and result.get("usage"):
        u = result["usage"]
        return {
            "model": result.get("model", "unknown"),
            "prompt_tokens": u.get("prompt_tokens", 0),
            "completion_tokens": u.get("completion_tokens", 0),
            "total_tokens": u.get("total_tokens", 0),
        }
    # 回傳全 0，model 設 unknown
    return {
        "model": "unknown",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def aggregate_usage(*usages: Dict[str, Any]) -> Dict[str, Any]:
    """
    將多筆 usage 相加，假設 model 都相同 → 取第一筆 model。
    """
    if not usages:
        return {}

    model_name = usages[0]["model"]  # 全部請求同一個 model
    total_prompt = sum(u["prompt_tokens"] for u in usages)
    total_completion = sum(u["completion_tokens"] for u in usages)
    total_tokens = total_prompt + total_completion

    return {
        "model": model_name,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_tokens,
    }


# def get_prompt_by_intimacy(levels: Dict[str, Dict[str, Any]], total_intimacy: int) -> str:
#     """
#     根據總親密度 total_intimacy，在角色 levels 中找出對應等級的 scene_prompt

#     Args:
#         levels: 角色的 levels dict（例如 {"1": {...}, "2": {...}}）
#         total_intimacy: 當前親密度

#     Returns:
#         scene_prompt 字串（預設空字串）
#     """
#     selected_prompt = ""
#     max_matched_level = -1

#     for level_key, level_data in levels.items():
#         intimacy_threshold = level_data.get("intimacy", 0)
#         if total_intimacy >= intimacy_threshold:
#             # 持續更新找到的最大等級
#             if int(level_key) > max_matched_level:
#                 max_matched_level = int(level_key)
#                 selected_prompt = level_data.get("scene_prompt", "")

#     return selected_prompt
