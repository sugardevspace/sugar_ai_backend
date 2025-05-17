# Firebase 資料庫陣列轉字典自動化程式
# 用於將 user_card_collections 集合中的 collectedCardIds 陣列轉換為字典

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import logging

# 設定日誌記錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)


def initialize_firebase():
    """初始化 Firebase 連接"""
    try:
        # 使用您的憑證檔案路徑
        cred = credentials.Certificate("/Users/lipinze/dev/sugar_ai_backend/config/sugarAI_Firebase_Admin_SDK.json")
        firebase_admin.initialize_app(cred)
        logger.info("Firebase 初始化成功")
        return True
    except Exception as e:
        logger.error(f"Firebase 初始化失敗: {str(e)}")
        return False


def convert_array_to_dict(user_id):
    """
    將特定用戶的卡片收集陣列複製一份轉換為字典，同時保留原始陣列
    
    Args:
        user_id (str): 用戶 ID
        
    Returns:
        bool: 操作是否成功
    """
    # 檢查用戶 ID 是否有效
    if not user_id or not isinstance(user_id, str) or len(user_id) < 10:
        logger.error("無效的用戶 ID")
        return False

    logger.info(f"開始處理用戶 ID: {user_id}")

    try:
        # 獲取 Firestore 資料庫
        db = firestore.client()

        # 獲取用戶文檔
        user_ref = db.collection('user_card_collections').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            logger.error(f"找不到 ID 為 {user_id} 的用戶收集文檔")
            return False

        # 獲取現有的卡片收集陣列
        user_data = user_doc.to_dict()
        collected_card_ids = user_data.get('collectedCardIds', [])

        # 檢查是否已經有字典版本
        if 'collectedCardIdsDict' in user_data:
            logger.info("已存在字典格式的卡片收集，檢查是否需要更新")

            # 檢查是否有新的卡片需要添加到字典中
            existing_dict = user_data.get('collectedCardIdsDict', {})
            need_update = False

            for card_id in collected_card_ids:
                if card_id not in existing_dict:
                    existing_dict[card_id] = True
                    need_update = True

            if not need_update:
                logger.info("字典格式已是最新，無需更新")
                return True

            collected_card_ids_dict = existing_dict
        else:
            # 將陣列轉換為字典
            collected_card_ids_dict = {card_id: True for card_id in collected_card_ids}

        logger.info(f"轉換後的字典: {collected_card_ids_dict}")

        # 使用事務確保資料一致性
        @firestore.transactional
        def update_in_transaction(transaction, user_ref, collected_dict):
            # 再次讀取文檔以確保它沒有被其他進程修改
            user_snapshot = user_ref.get(transaction=transaction)

            # 更新文檔，新增字典格式但保留原始陣列
            transaction.update(
                user_ref,
                {'collectedCardIdsDict': collected_dict
                 # 保留原始的 collectedCardIds 陣列不變
                 })

            return True

        # 執行事務
        transaction = db.transaction()
        result = update_in_transaction(transaction, user_ref, collected_card_ids_dict)

        if result:
            logger.info(f"成功為用戶 {user_id} 新增卡片收集字典版本")
        else:
            logger.error(f"為用戶 {user_id} 新增卡片收集字典版本失敗")

        return result

    except Exception as e:
        logger.error(f"處理用戶 {user_id} 時出錯: {str(e)}")
        return False


def process_all_users():
    """處理所有用戶的卡片收集轉換"""
    try:
        db = firestore.client()
        users = db.collection('user_card_collections').stream()

        success_count = 0
        fail_count = 0

        for user in users:
            user_id = user.id
            result = convert_array_to_dict(user_id)

            if result:
                success_count += 1
            else:
                fail_count += 1

        logger.info(f"處理完成: 成功 {success_count} 個，失敗 {fail_count} 個")
        return True
    except Exception as e:
        logger.error(f"處理所有用戶時出錯: {str(e)}")
        return False


def main():
    """主函數"""
    if not initialize_firebase():
        return

    # # 測試指定的文檔 ID
    # test_doc_id = "oLPTvBOQoVfh6mJhmkhVRAz7j233"
    # logger.info(f"測試文檔 ID: {test_doc_id}")

    # # 轉換特定用戶的卡片收集
    # result = convert_array_to_dict(test_doc_id)

    # if result:
    #     logger.info(f"測試成功: 已成功處理用戶 {test_doc_id}")
    # else:
    #     logger.error(f"測試失敗: 處理用戶 {test_doc_id} 時出錯")

    # 如果需要處理所有用戶，請取消下面的註釋
    # process_all_users()


if __name__ == "__main__":
    main()
