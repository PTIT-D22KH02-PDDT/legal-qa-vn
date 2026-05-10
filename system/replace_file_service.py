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

    def process(self, new_file_path: str, replaced_so_hieu: str) -> dict:
        """
        Xử lý đầy đủ luồng sửa đổi / thay thế văn bản.

        Args:
            new_file_path:      Đường dẫn tới file văn bản mới (upload).
            replaced_so_hieu:   Số hiệu của văn bản bị thay thế (đã có trong CSDL).

        Returns:
            dict chứa kết quả từng bước.
        """
        result = {
            "new_so_hieu": None,
            "chunks_indexed": 0,
            "sqlite_saved": False,
            "sqlite_deactivated": False,
            "chroma_deactivated": 0,
            "relation_saved": False,
        }

        #1.Parse, chunk, index văn bản mới
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

        # Metadata đã được Indexing.run_single_file → save_documents (SQLite); tránh ghi trùng.
        result["sqlite_saved"] = index_result.get("metadata_saved_count", 0) > 0
        logger.info(
            "  → Metadata SQLite (trong bước indexing): %s",
            "OK" if result["sqlite_saved"] else "SKIP (không có so_hieu)",
        )

        #2.Vô hiệu hóa văn bản bị thay thế
        logger.info("[2/3] Vô hiệu hóa văn bản bị thay thế: '%s'", replaced_so_hieu)
        sqlite_ok, chunks_deactivated = self.db_service.deactivate_document(replaced_so_hieu)
        result["sqlite_deactivated"] = sqlite_ok
        result["chroma_deactivated"] = chunks_deactivated
        logger.info(
            "  → SQLite: %s | Chroma chunks vô hiệu: %d",
            "OK" if sqlite_ok else "KHÔNG TÌM THẤY",
            chunks_deactivated,
        )

        #3.Tạo quan hệ "thay_the"
        logger.info("[3/3] Tạo quan hệ thay_the: '%s' → '%s'", new_so_hieu, replaced_so_hieu)
        relation = DocumentRelation(
            entity_start=new_so_hieu,
            entity_end=replaced_so_hieu,
            relation_type=RelationType.thay_the,
            description=f"{new_so_hieu} thay thế {replaced_so_hieu}",
        )
        saved_rels = self.db_service.save_relations([relation])
        result["relation_saved"] = saved_rels > 0
        logger.info("  → Quan hệ: %s", "OK" if result["relation_saved"] else "THẤT BẠI")

        logger.info("Pipeline hoàn tất: %s", result)
        return result

    def close(self):
        self.indexing.close()
        self.db_service.close()
