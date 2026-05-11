import logging
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session

from src.core.models import DocumentMetadata, DocumentRelation
from src.indexing.vector_store import ChromaStore
from .db import DocumentMetadataDB
from .db_respository import (
    get_session,
    DocumentMetadataRepository,
    DocumentRelationRepository
)
from system.schemas import DocumentInfo

logger = logging.getLogger(__name__)

_BATCH_SIZE = 500

class DocumentDatabaseService:
    """Service để lưu và query documents từ database"""
    
    def __init__(self, session: Optional[Session] = None, chroma_store: ChromaStore = None):
        """
        Initialize service
        
        Args:
            session: SQLAlchemy session (nếu None, sẽ tạo mới)
        """
        self.session = session or get_session()
        self.metadata_repo = DocumentMetadataRepository(self.session)
        self.relation_repo = DocumentRelationRepository(self.session)
        self.chroma_store = chroma_store
    
    def save_documents(
        self,
        documents: List[DocumentInfo]
    ) -> Tuple[int, List[str]]:
        """
        Lưu danh sách documents vào database
        """
        saved_count = 0
        saved_so_hieu = []
        
        for doc_info in documents:
            try:
                info = doc_info.metadata
                metadata = DocumentMetadata.model_validate(info) if info else None
                if not metadata:
                    logger.warning(f"Skip document: {doc_info.file_path.name} (no metadata)")
                    continue
                
                if self.metadata_repo.exists(metadata.so_hieu):
                    self.metadata_repo.update(metadata)
                    logger.info(f"Updated metadata: {metadata.so_hieu}")
                else:
                    self.metadata_repo.create(metadata)
                    logger.info(f"Saved metadata: {metadata.so_hieu}")
                
                saved_count += 1
                saved_so_hieu.append(metadata.so_hieu)
            
            except Exception as e:
                logger.error(f"Error saving document {doc_info.file_path}: {e}")
        
        return saved_count, saved_so_hieu
    
    def get_document_by_so_hieu(self, so_hieu: str) -> Optional[dict]:
        """Lấy thông tin một tài liệu"""
        metadata = self.metadata_repo.get_by_so_hieu(so_hieu)
        if not metadata:
            return None
        return {
            'so_hieu': metadata.so_hieu,
            'ten_van_ban': metadata.ten_van_ban,
            'loai': metadata.loai,
            'co_quan_ban_hanh': metadata.co_quan_ban_hanh,
            'ngay_ban_hanh': metadata.ngay_ban_hanh,
            'ngay_co_hieu_luc': metadata.ngay_co_hieu_luc,
            'so_dieu': metadata.so_dieu,
            'file_path': metadata.file_path,
            'indexed': metadata.indexed
        }
    
    def get_documents_by_type(self, loai: str) -> List[dict]:
        """Lấy tất cả documents theo loại"""
        documents = self.metadata_repo.get_by_loai(loai)
        return [
            {
                'so_hieu': doc.so_hieu,
                'ten_van_ban': doc.ten_van_ban,
                'loai': doc.loai,
                'co_quan_ban_hanh': doc.co_quan_ban_hanh,
                'ngay_ban_hanh': doc.ngay_ban_hanh,
                'ngay_co_hieu_luc': doc.ngay_co_hieu_luc,
                'so_dieu': doc.so_dieu,
                'file_path': doc.file_path,
                'indexed': doc.indexed
            }
            for doc in documents
        ]
    
    def get_all_documents(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """Lấy tất cả documents"""
        documents = self.metadata_repo.get_all(limit=limit, offset=offset)
        return [
            {
                'so_hieu': doc.so_hieu,
                'ten_van_ban': doc.ten_van_ban,
                'loai': doc.loai,
                'co_quan_ban_hanh': doc.co_quan_ban_hanh,
                'ngay_ban_hanh': doc.ngay_ban_hanh,
                'ngay_co_hieu_luc': doc.ngay_co_hieu_luc,
                'so_dieu': doc.so_dieu,
                'file_path': doc.file_path,
                'indexed': doc.indexed
            }
            for doc in documents
        ]
    
    def get_stats(self) -> dict:
        """Lấy thống kê database"""
        total_docs = self.session.query(DocumentMetadataDB).count()
        indexed_docs = self.session.query(DocumentMetadataDB).filter_by(indexed=1).count()
        
        return {
            'total_documents': total_docs,
            'indexed_documents': indexed_docs
        }
    
    def close(self):
        """Close database session"""
        self.session.close()

    def save_relations(self, relations: List[DocumentRelation]) -> int:
        """
        Lưu quan hệ; bỏ qua bản ghi trùng (entity_start, entity_end, relation_type).
        Trả về số quan hệ đã có trong DB sau lần gọi (tạo mới hoặc đã tồn tại).
        """
        ensured = 0
        for rel in relations:
            try:
                rel_type = (
                    rel.relation_type.value
                    if rel.relation_type is not None and hasattr(rel.relation_type, "value")
                    else str(rel.relation_type)
                )
                if self.relation_repo.exists_triple(rel.entity_start, rel.entity_end, rel_type):
                    ensured += 1
                    logger.debug(
                        "Relation already exists: %s -> %s [%s]",
                        rel.entity_start,
                        rel.entity_end,
                        rel_type,
                    )
                    continue
                self.relation_repo.create(rel)
                ensured += 1
            except Exception as e:
                logger.error(f"Error saving relation {rel.entity_start} -> {rel.entity_end}: {e}")
        return ensured

    def save_document_with_relations(
        self, 
        documents: List[DocumentInfo], 
        relations: List[DocumentRelation]
    ) -> Tuple[int, int]:
        """
        Lưu cả metadata tài liệu và quan hệ của chúng vào database
        Returns: (số doc đã lưu, số relation đã lưu)
        """
        saved_docs, _ = self.save_documents(documents)
        saved_rels = self.save_relations(relations)
        
        logger.info(f"Database sync complete: {saved_docs} docs, {saved_rels} relations")
        return saved_docs, saved_rels
    # Vô hiệu hóa văn bản bị thay thế / sửa đổi bổ sung

    def deactivate_document(
        self,
        so_hieu: str,
        batch_size: int = _BATCH_SIZE
    ) -> Tuple[bool, int]:
        """
        Vô hiệu hóa văn bản bị thay thế/sửa đổi bổ sung:
          1. Cập nhật document_metadata.trang_thai = 0 trong SQLite.
          2. Cập nhật trang_thai = 0 cho toàn bộ chunk của văn bản đó trong ChromaDB,
             xử lý theo lô để tránh OOM với văn bản nhiều chunk.

        Returns:
            (sqlite_ok, chunks_updated)
              sqlite_ok      – True nếu tìm thấy và cập nhật SQLite thành công
              chunks_updated – Số chunk đã cập nhật trong Chroma
        """
        #1.SQLite
        sqlite_ok = self.metadata_repo.update_trang_thai(so_hieu, 0)
        if not sqlite_ok:
            logger.warning(
                "deactivate_document: không tìm thấy '%s' trong document_metadata.", so_hieu
            )
        else:
            logger.info("SQLite: đã đặt trang_thai=0 cho '%s'.", so_hieu)

        #2.ChromaDB
        chunks_updated = self._deactivate_chunks_in_chroma(so_hieu, batch_size, self.chroma_store)

        return sqlite_ok, chunks_updated

    def _deactivate_chunks_in_chroma(self, so_hieu: str, batch_size: int, chroma_store: ChromaStore) -> int:
        """Đặt trang_thai=0 cho toàn bộ chunk của văn bản `so_hieu` trong Chroma."""
        try:
            collection = chroma_store.collection
        except Exception as exc:
            logger.error("Không thể kết nối ChromaDB: %s", exc)
            return 0

        result = collection.get(
            where={"so_hieu": {"$eq": so_hieu}},
            include=["metadatas"],
        )

        ids       = result.get("ids", [])
        metadatas = result.get("metadatas", [])

        if not ids:
            logger.warning(
                "ChromaDB: không tìm thấy chunk nào của '%s'. "
                "Kiểm tra lại field 'so_hieu' trong metadata chunk.",
                so_hieu,
            )
            return 0

        logger.info(
            "ChromaDB: tìm thấy %d chunk của '%s'. Bắt đầu cập nhật theo lô %d ...",
            len(ids), so_hieu, batch_size,
        )

        updated = 0
        for i in range(0, len(ids), batch_size):
            batch_ids   = ids[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]

            for meta in batch_metas:
                if meta is None:
                    meta = {}
                meta["trang_thai"] = 0

            collection.update(ids=batch_ids, metadatas=batch_metas)
            updated += len(batch_ids)
            logger.info("  Tiến độ: %d/%d chunks đã cập nhật.", updated, len(ids))

        logger.info(
            "ChromaDB: hoàn tất — đã đặt trang_thai=0 cho %d chunk của '%s'.",
            updated, so_hieu,
        )
        return updated