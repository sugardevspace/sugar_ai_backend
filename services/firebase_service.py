# services/firebase_service.py
import logging
import firebase_admin
from firebase_admin import credentials, firestore, auth
from typing import Dict, Any, List, Optional
from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin.firestore import SERVER_TIMESTAMP


class FirebaseService:
    """Firebase 服務，提供與 Firebase 交互的功能"""

    def __init__(self, credentials_path: str = None, config: Dict[str, Any] = None):
        """
        初始化 Firebase 服務

        參數:
            credentials_path: Firebase 服務帳號金鑰檔案路徑
            config: Firebase 配置字典 (當無法使用檔案路徑時)
        """
        # 設置日誌記錄器
        self.logger = logging.getLogger("firebase_service")
        # Firebase 應用實例
        self.app = None
        # Firestore 資料庫實例
        self.db = None
        # 初始化狀態標誌
        self.initialized = False
        # 保存憑證路徑
        self.credentials_path = credentials_path
        # 保存配置資訊
        self.config = config

    def initialize(self):
        """初始化 Firebase 連接"""
        try:
            # 如果已經初始化，直接返回
            if self.initialized:
                return True

            # 檢查是否已經有默認應用
            if len(firebase_admin._apps) > 0:
                # 如果已經初始化，獲取現有實例
                self.app = firebase_admin.get_app()
                self.db = firestore.client()
                self.initialized = True
                self.logger.info("使用現有 Firebase 應用實例")
                return True

            # 使用不同方式進行初始化
            if self.credentials_path:
                # 方式1: 使用服務帳號金鑰檔案初始化
                cred = credentials.Certificate(self.credentials_path)
                self.app = firebase_admin.initialize_app(cred)
            elif self.config:
                # 方式2: 使用配置字典初始化
                cred = credentials.Certificate(self.config)
                self.app = firebase_admin.initialize_app(cred)
            else:
                # 方式3: 使用應用默認憑證 (通常用於 Google Cloud 環境)
                self.app = firebase_admin.initialize_app()

            # 初始化 Firestore 資料庫客戶端
            self.db = firestore.client()

            # 標記初始化完成
            self.initialized = True
            self.logger.info("Firebase 服務初始化成功")
            return True
        except Exception as e:
            # 發生錯誤則記錄並返回 False
            self.logger.error(f"Firebase 初始化失敗: {e}")
            return False

    # === Firestore 資料庫操作方法 ===
    def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取 Firestore 文檔

        參數:
            collection: 集合名稱
            document_id: 文檔 ID

        返回:
            Dict 或 None: 文檔資料字典，不存在則返回 None
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 獲取文檔引用
            doc_ref = self.db.collection(collection).document(document_id)
            # 獲取文檔
            doc = doc_ref.get()

            # 檢查文檔是否存在
            if doc.exists:
                return doc.to_dict()
            else:
                self.logger.warning(f"文檔不存在: {collection}/{document_id}")
                return None
        except Exception as e:
            self.logger.error(f"獲取文檔失敗: {e}")
            return None

    def set_document(self, collection: str, document_id: str, data: Dict[str, Any], merge: bool = True) -> bool:
        """
        設置 Firestore 文檔 (創建或覆蓋)

        參數:
            collection: 集合名稱
            document_id: 文檔 ID
            data: 要設置的資料
            merge: 是否合併現有資料 (True) 或完全覆蓋 (False)

        返回:
            bool: 操作是否成功
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 獲取文檔引用
            doc_ref = self.db.collection(collection).document(document_id)
            # 設置文檔
            doc_ref.set(data, merge=merge)
            self.logger.info(f"設置文檔成功: {collection}/{document_id}")
            return True
        except Exception as e:
            self.logger.error(f"設置文檔失敗: {e}")
            return False

    def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> bool:
        """
        更新 Firestore 文檔 (僅更新指定欄位)

        參數:
            collection: 集合名稱
            document_id: 文檔 ID
            data: 要更新的欄位和值

        返回:
            bool: 操作是否成功
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 獲取文檔引用
            doc_ref = self.db.collection(collection).document(document_id)
            # 更新文檔
            doc_ref.update(data)
            self.logger.info(f"更新文檔成功: {collection}/{document_id}")
            return True
        except Exception as e:
            self.logger.error(f"更新文檔失敗: {e}")
            return False

    def update_dict_field_with_log(self,
                                   collection: str,
                                   document_id: str,
                                   field: str,
                                   values: dict,
                                   operation: str = "update") -> bool:
        # 驗證參數
        if field != "collectedCardIdsDict":
            self.logger.error(f"⚠️ 僅允許更新 collectedCardIdsDict，收到: {field}")
            return False

        if not isinstance(values, dict):
            self.logger.error("❌ values 必須為 dict")
            return False

        if operation != "update":
            self.logger.error(f"❌ 不支援的操作類型: {operation}")
            return False

        if not self.initialized:
            self.initialize()

        try:
            doc_ref = self.db.collection(collection).document(document_id)
            # 新增：user_cards collection 的文檔引用
            user_cards_doc_ref = self.db.collection("user_cards").document(document_id)

            @firestore.transactional
            def transaction_update(transaction):
                snapshot = doc_ref.get()
                # 新增：同時讀取 user_cards 的文檔
                user_cards_snapshot = user_cards_doc_ref.get()

                if snapshot.exists:
                    current_data = snapshot.to_dict()
                    current_cards = current_data.get("collectedCardIdsDict", {})
                    self.logger.info(f"🧾 [更新前] 目前擁有的卡牌: {current_cards}")
                else:
                    self.logger.info("🧾 [更新前] 無卡牌記錄，將建立新資料")

                # 原始 collection 的更新邏輯
                if not snapshot.exists:
                    initial_dict = {}
                    initial_log = {}
                    for card_id, value in values.items():
                        initial_dict[card_id] = value
                        initial_log[card_id] = firestore.SERVER_TIMESTAMP
                    transaction.set(doc_ref, {field: initial_dict, "collectedCardLog": initial_log})
                else:
                    updates = {}
                    for card_id, value in values.items():
                        updates[f"{field}.{card_id}"] = value
                        updates[f"collectedCardLog.{card_id}"] = firestore.SERVER_TIMESTAMP
                    transaction.update(doc_ref, updates)

                # 新增：同步更新 user_cards collection
                if not user_cards_snapshot.exists:
                    # 如果 user_cards 中沒有這個文檔，創建新的
                    initial_dict = {}
                    initial_log = {}
                    for card_id, value in values.items():
                        initial_dict[card_id] = value
                        initial_log[card_id] = firestore.SERVER_TIMESTAMP

                    user_cards_data = {
                        field: initial_dict,
                        "collectedCardLog": initial_log,
                        "userId": document_id,  # 添加 userId 欄位便於查詢
                        "createdAt": firestore.SERVER_TIMESTAMP,
                        "updatedAt": firestore.SERVER_TIMESTAMP
                    }
                    transaction.set(user_cards_doc_ref, user_cards_data)
                    self.logger.info(f"🆕 在 user_cards 中創建新文檔: {document_id}")
                else:
                    # 如果 user_cards 中已有文檔，更新它
                    user_cards_updates = {}
                    for card_id, value in values.items():
                        user_cards_updates[f"{field}.{card_id}"] = value
                        user_cards_updates[f"collectedCardLog.{card_id}"] = firestore.SERVER_TIMESTAMP
                    user_cards_updates["updatedAt"] = firestore.SERVER_TIMESTAMP

                    transaction.update(user_cards_doc_ref, user_cards_updates)
                    self.logger.info(f"🔄 更新 user_cards 中的文檔: {document_id}")

                # 讀取更新後內容（模擬，但 transaction 中不能再次讀取）
                current_cards = current_data.get("collectedCardIdsDict", {}) if snapshot.exists else {}
                final_cards = {**current_cards, **values}
                self.logger.info(f"🆕 [預期更新後] 卡牌: {final_cards}")

            transaction = self.db.transaction()
            transaction_update(transaction)

            # 新增：transaction 完成後重新讀取資料庫做確認
            try:
                # 讀取原始 collection 的最新狀態
                updated_doc = doc_ref.get()
                if updated_doc.exists:
                    updated_data = updated_doc.to_dict()
                    updated_cards = updated_data.get("collectedCardIdsDict", {})
                    updated_log = updated_data.get("collectedCardLog", {})
                    self.logger.info(f"🔍 [原始collection確認] 最新卡牌: {updated_cards}")

                    # 驗證所有更新的卡片是否都存在
                    for card_id in values.keys():
                        if card_id not in updated_cards:
                            self.logger.warning(f"⚠️ [原始collection] 卡片 {card_id} 未找到")
                        else:
                            self.logger.info(f"✓ [原始collection] 卡片 {card_id}: {updated_cards[card_id]}")
                else:
                    self.logger.error(f"❌ [原始collection確認] 文檔不存在: {document_id}")

                # 讀取 user_cards collection 的最新狀態
                updated_user_cards_doc = user_cards_doc_ref.get()
                if updated_user_cards_doc.exists:
                    updated_user_cards_data = updated_user_cards_doc.to_dict()
                    updated_user_cards = updated_user_cards_data.get("collectedCardIdsDict", {})
                    updated_user_cards_log = updated_user_cards_data.get("collectedCardLog", {})
                    self.logger.info(f"🔍 [user_cards確認] 最新卡牌: {updated_user_cards}")

                    # 驗證所有更新的卡片是否都存在
                    for card_id in values.keys():
                        if card_id not in updated_user_cards:
                            self.logger.warning(f"⚠️ [user_cards] 卡片 {card_id} 未找到")
                        else:
                            self.logger.info(f"✓ [user_cards] 卡片 {card_id}: {updated_user_cards[card_id]}")

                    # 比較兩個 collection 的數據是否一致
                    data_consistent = True
                    for card_id in values.keys():
                        if updated_cards.get(card_id) != updated_user_cards.get(card_id):
                            self.logger.error(
                                f"❌ 數據不一致! 卡片 {card_id}: 原始={updated_cards.get(card_id)}, user_cards={updated_user_cards.get(card_id)}"
                            )
                            data_consistent = False

                    if data_consistent:
                        self.logger.info("✅ 兩個 collection 數據一致性驗證通過")
                    else:
                        self.logger.error("❌ 兩個 collection 數據不一致")

                else:
                    self.logger.error(f"❌ [user_cards確認] 文檔不存在: {document_id}")

            except Exception as e:
                self.logger.error(f"❌ 確認資料庫狀態時發生錯誤: {e}")

            self.logger.info(f"✅ 成功更新卡片字典到兩個 collection: {values}")
            self.logger.info(f"📁 已同步更新: {collection} 和 user_cards")
            return True

        except Exception as e:
            self.logger.error(f"❌ 更新卡片字典失敗: {e}")
            return False

    def delete_document(self, collection: str, document_id: str) -> bool:
        """
        刪除 Firestore 文檔

        參數:
            collection: 集合名稱
            document_id: 文檔 ID

        返回:
            bool: 操作是否成功
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 獲取文檔引用
            doc_ref = self.db.collection(collection).document(document_id)
            # 刪除文檔
            doc_ref.delete()
            self.logger.info(f"刪除文檔成功: {collection}/{document_id}")
            return True
        except Exception as e:
            self.logger.error(f"刪除文檔失敗: {e}")
            return False

    def query_documents(self,
                        collection: str,
                        filters: List[tuple] = None,
                        order_by: str = None,
                        limit: int = None) -> List[Dict[str, Any]]:
        """
        查詢 Firestore 文檔

        參數:
            collection: 集合名稱
            filters: 過濾條件列表，每個條件是 (欄位, 運算符, 值) 的元組
                支持的運算符有: ==, >, <, >=, <=, array_contains, in, array_contains_any
            order_by: 排序欄位
            limit: 結果數量上限

        返回:
            List: 符合條件的文檔列表
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 開始構建查詢
            query = self.db.collection(collection)

            # 應用過濾條件
            if filters:
                for f in filters:
                    if len(f) == 3:  # (欄位, 運算符, 值)
                        query = query.where(filter=FieldFilter(f[0], f[1], f[2]))

            # 應用排序
            if order_by:
                query = query.order_by(order_by)

            # 應用結果數量限制
            if limit:
                query = query.limit(limit)

            # 執行查詢
            docs = query.stream()

            # 處理查詢結果
            results = []
            for doc in docs:
                # 獲取文檔數據
                data = doc.to_dict()
                # 添加文檔 ID
                data['id'] = doc.id
                results.append(data)

            return results
        except Exception as e:
            self.logger.error(f"查詢文檔失敗: {e}")
            return []

    # === Firebase Authentication 用戶管理方法 ===

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取 Firebase Auth 用戶信息

        參數:
            user_id: 用戶 ID

        返回:
            Dict 或 None: 用戶信息字典，不存在則返回 None
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 從 Firebase Auth 獲取用戶
            user = auth.get_user(user_id)
            # 將用戶對象轉換為字典
            return {
                'uid': user.uid,
                'email': user.email,
                'display_name': user.display_name,
                'photo_url': user.photo_url,
                'disabled': user.disabled,
                'email_verified': user.email_verified
            }
        except Exception as e:
            self.logger.error(f"獲取用戶信息失敗: {e}")
            return None

    def create_user(self, email: str, password: str, display_name: str = None) -> Optional[Dict[str, Any]]:
        """
        創建新的 Firebase Auth 用戶

        參數:
            email: 用戶電子郵件
            password: 用戶密碼
            display_name: 用戶顯示名稱 (可選)

        返回:
            Dict 或 None: 創建的用戶信息，失敗則返回 None
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 設置用戶參數
            user_args = {'email': email, 'password': password, 'email_verified': False}

            # 如果提供了顯示名稱，則添加
            if display_name:
                user_args['display_name'] = display_name

            # 創建用戶
            user = auth.create_user(**user_args)

            # 返回創建的用戶信息
            return {'uid': user.uid, 'email': user.email, 'display_name': user.display_name}
        except Exception as e:
            self.logger.error(f"創建用戶失敗: {e}")
            return None

    def update_user(self, user_id: str, properties: Dict[str, Any]) -> bool:
        """
        更新 Firebase Auth 用戶信息

        參數:
            user_id: 用戶 ID
            properties: 要更新的屬性，可包含:
                display_name, email, phone_number, photo_url, password,
                email_verified, disabled

        返回:
            bool: 操作是否成功
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 更新用戶
            auth.update_user(user_id, **properties)
            self.logger.info(f"更新用戶成功: {user_id}")
            return True
        except Exception as e:
            self.logger.error(f"更新用戶失敗: {e}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """
        刪除 Firebase Auth 用戶

        參數:
            user_id: 要刪除的用戶 ID

        返回:
            bool: 操作是否成功
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 刪除用戶
            auth.delete_user(user_id)
            self.logger.info(f"刪除用戶成功: {user_id}")
            return True
        except Exception as e:
            self.logger.error(f"刪除用戶失敗: {e}")
            return False

    def verify_id_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """
        驗證 Firebase ID Token

        參數:
            id_token: Firebase 身份驗證令牌

        返回:
            Dict 或 None: 解碼後的令牌信息，驗證失敗則返回 None
        """
        # 確保已初始化
        if not self.initialized:
            self.initialize()

        try:
            # 驗證並解碼令牌
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            self.logger.error(f"驗證令牌失敗: {e}")
            return None

    def get_server_timestamp(self):
        """
        獲取 Firestore 的伺服器時間戳記字段，用於寫入資料時記錄伺服器當下時間。

        返回:
            firestore.SERVER_TIMESTAMP: Firestore 伺服器時間戳記佔位符
        """
        return SERVER_TIMESTAMP
