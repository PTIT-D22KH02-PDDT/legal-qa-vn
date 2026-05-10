"""
Database models and operations cho lưu trữ Metadata, Content và Legacy
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

# Database base
Base = declarative_base()

class DocumentContentDB(Base):
    """Lưu trữ nội dung HTML của văn bản"""
    __tablename__ = 'document_content'
    
    id = Column(Integer, primary_key=True)  # ID từ dataset
    content_html = Column(Text, nullable=True)

class DocumentMetadataDB(Base):
    """ORM model cho DocumentMetadata (Dữ liệu chính)"""
    __tablename__ = 'document_metadata'
    
    # Primary key
    so_hieu = Column(String(255), primary_key=True, nullable=False, unique=True)
    
    # Basic info
    ten_van_ban = Column(String(500), nullable=True)
    loai = Column(String(100), nullable=True)
    co_quan_ban_hanh = Column(String(255), nullable=True)
    ngay_ban_hanh = Column(String(20), nullable=True)
    ngay_co_hieu_luc = Column(String(20), nullable=True)
    so_dieu = Column(Integer, default=0)
    linh_vuc = Column(String(255), nullable=True)
    
    # File tracking
    file_path = Column(String(500), nullable=True)
    
    # Metadata quản lý
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed = Column(Integer, default=0)

    # Trạng thái hiệu lực: 1 = Còn hiệu lực, 0 = Hết hiệu lực
    trang_thai = Column(Integer, default=1, nullable=True)

    def __repr__(self):
        return f"<DocumentMetadata({self.so_hieu}, {self.ten_van_ban})>"

class DocumentLegacyDB(Base):
    """ORM model cho DocumentMetadata (Dữ liệu cũ - Legacy)"""
    __tablename__ = 'document_legacy'
    
    # Primary key
    so_hieu = Column(String(255), primary_key=True, nullable=False, unique=True)
    
    # Basic info (Giữ nguyên các trường hiện tại như yêu cầu)
    ten_van_ban = Column(String(500), nullable=True)
    loai = Column(String(100), nullable=True)
    co_quan_ban_hanh = Column(String(255), nullable=True)
    ngay_ban_hanh = Column(String(20), nullable=True)
    ngay_co_hieu_luc = Column(String(20), nullable=True)
    so_dieu = Column(Integer, default=0)
    
    # File tracking
    file_path = Column(String(500), nullable=True)
    
    # Metadata quản lý
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<DocumentLegacy({self.so_hieu}, {self.ten_van_ban})>"

class DocumentRelationDB(Base):
    """ORM model cho DocumentRelation (Quan hệ giữa các văn bản)"""
    __tablename__ = 'document_relation'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_start = Column(String(255), nullable=True)
    entity_end = Column(String(255), nullable=True)
    relation_type = Column(String(100), nullable=True)
    description = Column(String(1000), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DocumentRelation({self.entity_start} -> {self.entity_end})>"
