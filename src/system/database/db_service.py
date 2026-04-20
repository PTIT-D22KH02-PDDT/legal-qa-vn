import logging
from typing import List, Tuple, Optional
from pathlib import Path
from sqlalchemy.orm import Session

from src.core.models import DocumentMetadata, DocumentRelation
from .db import (
    DocumentMetadataDB,
    DocumentRelationDB
)
from .db_respository import (
    get_session,
    DocumentMetadataRepository,
    DocumentRelationRepository,
)
from src.system.schemas import DocumentInfo
logger = logging.getLogger(__name__)

class DocumentDatabaseService:
    """Service để lưu và query documents + relations từ database"""
    
    def __init__(self, session: Optional[Session] = None):
        """
        Initialize service
        
        Args:
            session: SQLAlchemy session (nếu None, sẽ tạo mới)
        """
        self.session = session or get_session()
        self.metadata_repo = DocumentMetadataRepository(self.session)
        self.relation_repo = DocumentRelationRepository(self.session)
    
    def save_documents(
        self,
        documents: List[DocumentInfo]
    ) -> Tuple[int, List[str]]:
        """
        Lưu danh sách documents vào database
        
        Args:
            documents: List[DocumentInfo] từ relationship_builder.scan_folder_structure()
        
        Returns:
            (total_saved, saved_so_hieu_list)
        """
        saved_count = 0
        saved_so_hieu = []
        
        for doc_info in documents:
            try:
                # Lấy metadata từ DocumentInfo
                info = doc_info.metadata
                metadata=DocumentMetadata.model_validate(info) if info else None
                if not metadata:
                    logger.warning(f"Skip document: {doc_info.file_path.name} (no metadata)")
                    continue
                
                # Check if already exists
                if self.metadata_repo.exists(metadata.so_hieu):
                    # Update existing
                    self.metadata_repo.update(metadata.so_hieu)
                    logger.info(f"Updated metadata: {metadata.so_hieu}")
                else:
                    # Create new
                    self.metadata_repo.create(metadata)
                    logger.info(f"Saved metadata: {metadata.so_hieu}")
                
                saved_count += 1
                saved_so_hieu.append(metadata.so_hieu)
            
            except Exception as e:
                logger.error(f"Error saving document {doc_info.file_path}: {e}")
        
        return saved_count, saved_so_hieu
    
    def save_relations(self, relations: List[DocumentRelation]) -> Tuple[int, int]:
        """
        Lưu danh sách relations vào database
        Args:
            relations: List[DocumentRelation] từ relationship_builder.build_relations()
        Returns:
            (total_saved, skipped_count)
        """
        saved_count = 0
        skipped_count = 0
        for relation in relations:
            try:
                # Verify both entities exist
                if not self.metadata_repo.exists(relation.entity_start):
                    logger.warning(f"Skip relation: {relation.entity_start} not found in DB")
                    skipped_count += 1
                    continue
                
                if not self.metadata_repo.exists(relation.entity_end):
                    logger.warning(f"Skip relation: {relation.entity_end} not found in DB")
                    skipped_count += 1
                    continue
                
                # Save relation
                self.relation_repo.create(relation)
                saved_count += 1
            
            except Exception as e:
                logger.error(f"Error saving relation: {e}")
                skipped_count += 1
        
        return saved_count, skipped_count
    
    def get_related_documents(self, so_hieu: str) -> dict:
        """
        Lấy tất cả tài liệu liên quan đến một tài liệu
        Args:
            so_hieu: Document identifier
        Returns:
            {
                'document': DocumentMetadata,
                'related_from': [
                    {'source': so_hieu, 'target': so_hieu, 'type': relation_type, 'description': str}
                ],
                'related_to': [...]
            }
        """
        metadata = self.metadata_repo.get_by_so_hieu(so_hieu)
        if not metadata:
            return None
        relations = self.relation_repo.get_related_documents(so_hieu)
        return {
            'document': {
                'so_hieu': metadata.so_hieu,
                'ten_van_ban': metadata.ten_van_ban,
                'loai': metadata.loai,
                'co_quan_ban_hanh': metadata.co_quan_ban_hanh,
                'ngay_ban_hanh': metadata.ngay_ban_hanh,
                'ngay_co_hieu_luc': metadata.ngay_co_hieu_luc,
                'so_dieu': metadata.so_dieu,
                'file_path': metadata.file_path,
                'indexed': metadata.indexed
            },
            'related_from': [
                {
                    'source': r.entity_start,
                    'target': r.entity_end,
                    'type': r.relation_type.value,
                    'description': r.description
                }
                for r in relations['related_from']
            ],
            'related_to': [
                {
                    'source': r.entity_start,
                    'target': r.entity_end,
                    'type': r.relation_type.value,
                    'description': r.description
                }
                for r in relations['related_to']
            ]
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
    
    def get_all_relations(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """Lấy tất cả relations"""
        relations = self.relation_repo.get_all(limit=limit, offset=offset)
        return [
            {
                'id': rel.id,
                'entity_start': rel.entity_start,
                'entity_end': rel.entity_end,
                'type': rel.relation_type.value,
                'description': rel.description
            }
            for rel in relations
        ]
    
    def get_stats(self) -> dict:
        """Lấy thống kê database"""
        total_docs = self.session.query(DocumentMetadataDB).count()
        indexed_docs = self.session.query(DocumentMetadataDB).filter_by(indexed=1).count()
        total_relations = self.relation_repo.count_all()
        
        return {
            'total_documents': total_docs,
            'indexed_documents': indexed_docs,
            'total_relations': total_relations
        }
    
    def close(self):
        """Close database session"""
        self.session.close()
