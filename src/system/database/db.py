"""
Database models and operations cho lưu trữ DocumentMetadata và DocumentRelation
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from src.core.enums import RelationType


# Database base
Base = declarative_base()

class DocumentMetadataDB(Base):
    """ORM model cho DocumentMetadata"""
    __tablename__ = 'document_metadata'
    
    # Primary key
    so_hieu = Column(String(255), primary_key=True, nullable=False, unique=True)
    
    # Basic info
    ten_van_ban = Column(String(500), nullable=True)
    loai = Column(String(100), nullable=True)  # Luật, Nghị định, Thông tư, etc.
    co_quan_ban_hanh = Column(String(255), nullable=True)
    ngay_ban_hanh = Column(String(20), nullable=True)  # Format: DD/MM/YYYY
    ngay_co_hieu_luc = Column(String(20), nullable=True)
    so_dieu = Column(Integer, default=0)
    
    # File tracking
    file_path = Column(String(500), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed = Column(Integer, default=0)  # 1 if indexed in ChromaDB, 0 otherwise
    
    # Relationships
    relations_from = relationship(
        "DocumentRelationDB",
        foreign_keys="DocumentRelationDB.entity_start",
        back_populates="source_doc"
    )
    relations_to = relationship(
        "DocumentRelationDB",
        foreign_keys="DocumentRelationDB.entity_end",
        back_populates="target_doc"
    )
    
    def __repr__(self):
        return f"<DocumentMetadata({self.so_hieu}, {self.ten_van_ban})>"


class DocumentRelationDB(Base):
    """ORM model cho DocumentRelation"""
    __tablename__ = 'document_relation'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    entity_start = Column(String(255), ForeignKey('document_metadata.so_hieu'), nullable=False)
    entity_end = Column(String(255), ForeignKey('document_metadata.so_hieu'), nullable=False)
    
    # Relation type
    relation_type = Column(SQLEnum(RelationType), nullable=False)
    
    # Optional fields
    description = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    source_doc = relationship(
        "DocumentMetadataDB",
        foreign_keys=[entity_start],
        back_populates="relations_from"
    )
    target_doc = relationship(
        "DocumentMetadataDB",
        foreign_keys=[entity_end],
        back_populates="relations_to"
    )
    
    def __repr__(self):
        return f"<DocumentRelation({self.entity_start} --[{self.relation_type.value}]--> {self.entity_end})>"
