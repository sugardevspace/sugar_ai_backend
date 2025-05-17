import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple

from services.firebase_service import FirebaseService


class AsyncFirebaseService:
    """
    Firebase 服務的異步包裝器，將同步 Firebase 操作轉換為異步介面
    """

    def __init__(self,
                 firebase_service: FirebaseService = None,
                 credentials_path: str = None,
                 config: Dict[str, Any] = None):
        """
        初始化非同步 Firebase 服務

        Args:
            firebase_service: 已初始化的 FirebaseService 實例
            credentials_path: Firebase 服務帳號金鑰檔案路徑
            config: Firebase 配置字典 (當無法使用檔案路徑時)
        """
        self.logger = logging.getLogger("async_firebase_service")

        # 如果提供了現有的 FirebaseService 實例，則使用它
        if firebase_service:
            self.firebase_service = firebase_service
        else:
            # 否則，創建一個新的 FirebaseService 實例
            self.firebase_service = FirebaseService(credentials_path=credentials_path, config=config)

    async def initialize(self) -> bool:
        """
        非同步初始化 Firebase 連接

        Returns:
            bool: 初始化是否成功
        """
        return await asyncio.to_thread(self.firebase_service.initialize)

    # === Firestore 資料庫操作的非同步方法 ===

    async def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """
        非同步獲取 Firestore 文檔

        Args:
            collection: 集合名稱
            document_id: 文檔 ID

        Returns:
            Dict 或 None: 文檔資料字典，不存在則返回 None
        """
        return await asyncio.to_thread(self.firebase_service.get_document, collection, document_id)

    async def set_document(self, collection: str, document_id: str, data: Dict[str, Any], merge: bool = True) -> bool:
        """
        非同步設置 Firestore 文檔 (創建或覆蓋)

        Args:
            collection: 集合名稱
            document_id: 文檔 ID
            data: 要設置的資料
            merge: 是否合併現有資料 (True) 或完全覆蓋 (False)

        Returns:
            bool: 操作是否成功
        """
        return await asyncio.to_thread(self.firebase_service.set_document, collection, document_id, data, merge)

    async def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> bool:
        """
        非同步更新 Firestore 文檔 (僅更新指定欄位)

        Args:
            collection: 集合名稱
            document_id: 文檔 ID
            data: 要更新的欄位和值

        Returns:
            bool: 操作是否成功
        """
        return await asyncio.to_thread(self.firebase_service.update_document, collection, document_id, data)

    async def update_dict_field(self,
                                collection: str,
                                document_id: str,
                                field: str,
                                values: dict,
                                operation: str = "update") -> bool:
        """
        非同步更新文檔中的字典欄位，可以新增或更新鍵值對

        Args:
            collection: 集合名稱
            document_id: 文檔 ID
            field: 要更新的字典欄位名稱
            values: 要更新的鍵值對字典
            operation: 操作類型，目前僅支援 "update"

        Returns:
            bool: 操作是否成功
        """
        return await asyncio.to_thread(self.firebase_service.update_dict_field_with_log, collection, document_id, field,
                                       values, operation)

    async def delete_document(self, collection: str, document_id: str) -> bool:
        """
        非同步刪除 Firestore 文檔

        Args:
            collection: 集合名稱
            document_id: 文檔 ID

        Returns:
            bool: 操作是否成功
        """
        return await asyncio.to_thread(self.firebase_service.delete_document, collection, document_id)

    async def query_documents(self,
                              collection: str,
                              filters: List[Tuple] = None,
                              order_by: str = None,
                              limit: int = None) -> List[Dict[str, Any]]:
        """
        非同步查詢 Firestore 文檔

        Args:
            collection: 集合名稱
            filters: 過濾條件列表，每個條件是 (欄位, 運算符, 值) 的元組
                支持的運算符有: ==, >, <, >=, <=, array_contains, in, array_contains_any
            order_by: 排序欄位
            limit: 結果數量上限

        Returns:
            List: 符合條件的文檔列表
        """
        return await asyncio.to_thread(self.firebase_service.query_documents, collection, filters, order_by, limit)

    # === Firebase Authentication 用戶管理的非同步方法 ===

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        非同步獲取 Firebase Auth 用戶信息

        Args:
            user_id: 用戶 ID

        Returns:
            Dict 或 None: 用戶信息字典，不存在則返回 None
        """
        return await asyncio.to_thread(self.firebase_service.get_user, user_id)

    async def create_user(self, email: str, password: str, display_name: str = None) -> Optional[Dict[str, Any]]:
        """
        非同步創建新的 Firebase Auth 用戶

        Args:
            email: 用戶電子郵件
            password: 用戶密碼
            display_name: 用戶顯示名稱 (可選)

        Returns:
            Dict 或 None: 創建的用戶信息，失敗則返回 None
        """
        return await asyncio.to_thread(self.firebase_service.create_user, email, password, display_name)

    async def update_user(self, user_id: str, properties: Dict[str, Any]) -> bool:
        """
        非同步更新 Firebase Auth 用戶信息

        Args:
            user_id: 用戶 ID
            properties: 要更新的屬性，可包含:
                display_name, email, phone_number, photo_url, password,
                email_verified, disabled

        Returns:
            bool: 操作是否成功
        """
        return await asyncio.to_thread(self.firebase_service.update_user, user_id, properties)

    async def delete_user(self, user_id: str) -> bool:
        """
        非同步刪除 Firebase Auth 用戶

        Args:
            user_id: 要刪除的用戶 ID

        Returns:
            bool: 操作是否成功
        """
        return await asyncio.to_thread(self.firebase_service.delete_user, user_id)

    async def verify_id_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """
        非同步驗證 Firebase ID Token

        Args:
            id_token: Firebase 身份驗證令牌

        Returns:
            Dict 或 None: 解碼後的令牌信息，驗證失敗則返回 None
        """
        return await asyncio.to_thread(self.firebase_service.verify_id_token, id_token)

    # === 為 SugarAI 加入特定的應用函數 ===

    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        非同步獲取用戶個人資料

        Args:
            user_id: 用戶 ID

        Returns:
            Dict 或 None: 用戶個人資料，不存在則返回 None
        """
        return await asyncio.to_thread(self.firebase_service.get_document, "users", user_id)

    async def get_character_profile(self, character_id: str) -> Optional[Dict[str, Any]]:
        """
        非同步獲取 AI 角色設定

        Args:
            character_id: AI 角色 ID

        Returns:
            Dict 或 None: 角色設定資料，不存在則返回 None
        """
        return await asyncio.to_thread(self.firebase_service.get_document, "characters", character_id)

    async def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        非同步獲取聊天 meta 數據，從 channels/{channel_id} 文檔中的 meta_data 和 user_persona 欄位獲取

        Args:
            channel_id: 頻道 ID

        Returns:
            Dict 或 None: 包含 meta_data 和 user_persona 的字典，如果文檔不存在則返回 None
        """
        try:
            # 從 channels 集合讀取文檔
            channel_doc = await asyncio.to_thread(self.firebase_service.get_document, "channels", channel_id)

            # 文檔不存在，返回 None
            if not channel_doc:
                return None

            # 提取 meta_data 和 user_persona，若 user_persona 不存在則給空字典
            return {"meta_data": channel_doc.get("meta_data"), "user_persona": channel_doc.get("user_persona", {})}

        except Exception as e:
            self.logger.error(f"獲取聊天 meta 數據時發生錯誤: {e}")
            return None

    async def update_chat_meta(self, user_id: str, channel_id: str, meta: Dict[str, Any]) -> bool:
        """
        非同步更新聊天 meta 數據

        Args:
            user_id: 用戶 ID
            channel_id: 頻道 ID
            meta: 更新的 meta 數據

        Returns:
            bool: 操作是否成功
        """
        # 更新 channels 集合中的 meta_data 字段
        return await asyncio.to_thread(self.firebase_service.update_document_field, "channels", channel_id, "meta_data",
                                       meta)

    def server_timestamp(self):
        """
        獲取 Firestore 服務器時間戳

        Returns:
            object: Firestore 服務器時間戳物件
        """
        # 這不需要非同步，因為它只是返回一個物件參考
        return self.firebase_service.db.SERVER_TIMESTAMP

    async def query_documents_with_subcollection_map(self,
                                                     collection: str,
                                                     doc_id: str,
                                                     sub_collections: List[str],
                                                     sub_doc_id: str = "info") -> Optional[Dict[str, Any]]:
        """
        透過 doc_id 讀主文件，並一次拉多個子集合 (每個子集合的 doc_id 都是 sub_doc_id)。
        回傳格式：
        {
          "main_doc": {...},
          "system_prompt": { ...sub_doc_data... },
          "levels": [ ...list... ]
        }
        """
        # 1. 先拿主文件
        main_doc = await asyncio.to_thread(self.firebase_service.get_document,
                                           collection=collection,
                                           document_id=doc_id)
        if not main_doc:
            return None

        result: Dict[str, Any] = {"main_doc": main_doc}

        # 2. 依序抓每個子集合
        for sub_coll in sub_collections:
            path = f"{collection}/{doc_id}/{sub_coll}"
            sub_doc = await asyncio.to_thread(self.firebase_service.get_document,
                                              collection=path,
                                              document_id=sub_doc_id)
            # 取整個 map 結構，未命中回傳 {}
            result[sub_coll] = sub_doc or {}

        return result

        # === SugarAI：訊息用量寫入 ===
    async def upsert_channel_message_usage(
        self,
        channel_id: str,
        message_id: str,
        usage_payload: Dict[str, Any],
        merge: bool = True,
    ) -> bool:
        """
        將 LLM 用量寫入：
        channels/{channelId}/messages/{messageId}

        Args:
            channel_id    : 頻道 ID
            message_id    : 該次對話在 Stream Chat 的 message.id
            usage_payload : 字典內容，例如
                {
                  "prompt_tokens": 139,
                  "completion_tokens": 47,
                  "total_tokens": 186,
                  "costUSD": 0.00071
                }
            merge         : True=合併；False=覆蓋
        """
        # 加上伺服器時間戳
        data = {**usage_payload, "createdAt": self.firebase_service.get_server_timestamp()}

        # 呼叫同步版 set_document
        return await asyncio.to_thread(
            self.firebase_service.set_document,
            f"channels/{channel_id}/messages",  # ← 直接傳路徑
            message_id,
            data,
            merge,
        )

    async def upsert_user_spend_logs(
        self,
        user_id: str,
        message_id: str,
        usage_payload: Dict[str, Any],
        merge: bool = True,
    ) -> bool:
        """
        將 LLM 用量寫入：
        channels/{channelId}/messages/{messageId}

        Args:
            channel_id    : 頻道 ID
            message_id    : 該次對話在 Stream Chat 的 message.id
            usage_payload : 字典內容，例如
                {
                  "prompt_tokens": 139,
                  "completion_tokens": 47,
                  "total_tokens": 186,
                  "costUSD": 0.00071
                }
            merge         : True=合併；False=覆蓋
        """
        # 加上伺服器時間戳
        data = {**usage_payload, "createdAt": self.firebase_service.get_server_timestamp()}

        # 呼叫同步版 set_document
        return await asyncio.to_thread(
            self.firebase_service.set_document,
            f"users/{user_id}/spend_logs",  # ← 直接傳路徑
            message_id,
            data,
            merge,
        )

    def get_server_timestamp(self):
        """
        獲取 Firestore 服務器時間戳

        Returns:
            object: Firestore 服務器時間戳物件
        """
        # 這不需要非同步，因為它只是返回一個物件參考
        return self.firebase_service.get_server_timestamp()
