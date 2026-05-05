import logging
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session

from src.core.models import DocumentMetadata
from .db import DocumentMetadataDB
from .db_respository import (
    get_session,
    DocumentMetadataRepository,
)
from src.system.schemas import DocumentInfo

logger = logging.getLogger(__name__)

class DocumentDatabaseService:
    """Service để lưu và query documents từ database"""
    
    def __init__(self, session: Optional[Session] = None):
        """
        Initialize service
        
        Args:
            session: SQLAlchemy session (nếu None, sẽ tạo mới)
        """
        self.session = session or get_session()
        self.metadata_repo = DocumentMetadataRepository(self.session)
    
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
                    self.metadata_repo.update(metadata.so_hieu)
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
