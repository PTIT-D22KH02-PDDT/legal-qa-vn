"""
AmendmentService — xử lý văn bản sửa đổi / thay thế.

Luồng:
    1. Nhận file upload → parse, chunk, index vào ChromaDB + lưu metadata vào SQLite.
    2. Vô hiệu hóa văn bản bị thay thế (trang_thai=0 trong SQLite và Chroma).
    3. Tạo quan hệ "thay_the" giữa văn bản mới và văn bản bị thay thế.
"""

import logging
from src.core.models import DocumentRelation
from src.core.enums import RelationType
from src.indexing.vector_store import ChromaStore
from system.indexing_100file import Indexing
from system.database.db_respository import init_database
from system.database.db_service import DocumentDatabaseService

logger = logging.getLogger(__name__)


class ReplaceFileService:
    def __init__(self, chroma_store: ChromaStore = None):
        db_manager = init_database()
        self._session = db_manager.get_session()
        self.indexing = Indexing(chroma_store=chroma_store, session=self._session)
        self.db_service = DocumentDatabaseService(self._session, chroma_store=chroma_store)

    def process(self, new_file_path: str, replaced_so_hieu: str, relation_type: str = "Thay thế") -> dict:
        """
        Xử lý luồng liên kết văn bản mới với văn bản cũ.

        Args:
            new_file_path:      Đường dẫn tới file văn bản mới (upload).
            replaced_so_hieu:   Số hiệu của văn bản quan hệ (đã có trong CSDL).
            relation_type:      Loại quan hệ (Thay thế, Sửa đổi, Hướng dẫn...).
        """
        result = {
            "new_so_hieu": None,
            "chunks_indexed": 0,
            "sqlite_saved": False,
            "sqlite_deactivated": False,
            "chroma_deactivated": 0,
            "relation_saved": False,
        }

        # 1. Parse, chunk, index văn bản mới
        logger.info("[1/3] Indexing văn bản mới: %s", new_file_path)
        index_result = self.indexing.run_single_file(new_file_path)

        if not index_result.get("success"):
            logger.error("Indexing thất bại, dừng pipeline.")
            return result

        result["chunks_indexed"] = index_result["chunks_count"]
        metadata = index_result.get("metadata", {})
        new_so_hieu = metadata.get("so_hieu")
        result["new_so_hieu"] = new_so_hieu
        logger.info("  → %d chunks, so_hieu='%s'", result["chunks_indexed"], new_so_hieu)

        result["sqlite_saved"] = index_result.get("metadata_saved_count", 0) > 0

        # 2. Vô hiệu hóa văn bản cũ CHỈ KHI quan hệ là "Thay thế"
        if relation_type == "Thay thế":
            logger.info("[2/3] Vô hiệu hóa văn bản bị thay thế: '%s'", replaced_so_hieu)
            sqlite_ok, chunks_deactivated = self.db_service.deactivate_document(replaced_so_hieu)
            result["sqlite_deactivated"] = sqlite_ok
            result["chroma_deactivated"] = chunks_deactivated
            logger.info("  → Đã vô hiệu hóa văn bản cũ.")
        else:
            logger.info("[2/3] Giữ nguyên hiệu lực văn bản cũ (Loại quan hệ: %s)", relation_type)

        # 3. Tạo quan hệ
        logger.info("[3/3] Tạo quan hệ %s: '%s' → '%s'", relation_type, new_so_hieu, replaced_so_hieu)
        # Sử dụng so_hieu làm start/end entities
        from system.database.db import DocumentRelationDB
        
        db_rel = DocumentRelationDB(
            entity_start=new_so_hieu,
            entity_end=replaced_so_hieu,
            relation_type=relation_type,
            description=f"{new_so_hieu} {relation_type} {replaced_so_hieu}"
        )
        self._session.add(db_rel)
        self._session.commit()
        result["relation_saved"] = True
        logger.info("  → Quan hệ: OK")

        logger.info("Pipeline hoàn tất: %s", result)
        return result

    def close(self):
        self.indexing.close()
        self.db_service.close()
