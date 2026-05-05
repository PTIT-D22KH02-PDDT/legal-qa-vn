from src.core.models import DocumentMetadata
from typing import List, Optional
from pathlib import Path
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker
import logging
from datetime import datetime
from .db import DocumentMetadataDB, DocumentContentDB, DocumentLegacyDB, Base

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration"""
    
    def __init__(self, db_path: Optional[str] = None, db_type: str = "sqlite"):
        self.db_type = db_type
        if db_type == "sqlite":
            if db_path is None:
                db_path = str(Path(__file__).resolve().parents[2] / "database" / "legal_documents.db")
            self.db_url = f"sqlite:///{db_path}"
        elif db_type == "postgresql":
            if db_path is None:
                raise ValueError("PostgreSQL connection string required")
            self.db_url = db_path
        else:
            raise ValueError(f"Unsupported DB type: {db_type}")
        
        self.echo = False


class DatabaseManager:
    """Database connection and session management"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = None
        self.SessionLocal = None
        self._initialize()
    
    def _initialize(self):
        self.engine = create_engine(
            self.config.db_url,
            echo=self.config.echo,
            connect_args={"check_same_thread": False} if "sqlite" in self.config.db_url else {}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        logger.info(f"Database initialized: {self.config.db_url}")
    
    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def close(self):
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

class DocumentMetadataRepository:
    """CRUD operations for DocumentMetadata"""
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, metadata: DocumentMetadata) -> DocumentMetadataDB:
        db_metadata = DocumentMetadataDB(
            so_hieu=metadata.so_hieu,
            ten_van_ban=metadata.ten_van_ban,
            loai=metadata.loai,
            co_quan_ban_hanh=metadata.co_quan_ban_hanh,
            ngay_ban_hanh=metadata.ngay_ban_hanh,
            ngay_co_hieu_luc=metadata.ngay_co_hieu_luc,
            file_path=metadata.file_path,
            so_dieu=metadata.so_dieu
        )
        self.session.add(db_metadata)
        self.session.commit()
        return db_metadata
    
    def get_by_so_hieu(self, so_hieu: str) -> Optional[DocumentMetadataDB]:
        return self.session.query(DocumentMetadataDB).filter_by(so_hieu=so_hieu).first()
    
    def search_by_name(self, name: str, limit: int = 10) -> List[DocumentMetadataDB]:
        """Tìm kiếm văn bản theo tên (sử dụng LIKE)."""
        return self.session.query(DocumentMetadataDB).filter(
            DocumentMetadataDB.ten_van_ban.ilike(f"%{name}%")
        ).limit(limit).all()

    def get_by_loai(self, loai: str) -> List[DocumentMetadataDB]:
        """Lấy danh sách văn bản theo loại."""
        return self.session.query(DocumentMetadataDB).filter_by(loai=loai).all()

    def get_all(self, limit: int = 10) -> List[DocumentMetadataDB]:
        """Lấy danh sách văn bản."""
        return self.session.query(DocumentMetadataDB).limit(limit).all()

    def exists(self, so_hieu: str) -> bool:
        return self.get_by_so_hieu(so_hieu) is not None

class DocumentLegacyRepository:
    """CRUD operations for DocumentLegacy"""
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, metadata: DocumentMetadata) -> DocumentLegacyDB:
        db_legacy = DocumentLegacyDB(
            so_hieu=metadata.so_hieu,
            ten_van_ban=metadata.ten_van_ban,
            loai=metadata.loai,
            co_quan_ban_hanh=metadata.co_quan_ban_hanh,
            ngay_ban_hanh=metadata.ngay_ban_hanh,
            ngay_co_hieu_luc=metadata.ngay_co_hieu_luc,
            file_path=metadata.file_path,
            so_dieu=metadata.so_dieu
        )
        self.session.add(db_legacy)
        self.session.commit()
        return db_legacy
    
    def get_by_so_hieu(self, so_hieu: str) -> Optional[DocumentLegacyDB]:
        return self.session.query(DocumentLegacyDB).filter_by(so_hieu=so_hieu).first()
    
    def exists(self, so_hieu: str) -> bool:
        return self.get_by_so_hieu(so_hieu) is not None

class DocumentContentRepository:
    """CRUD operations for DocumentContent"""
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, doc_id: int, content_html: str) -> DocumentContentDB:
        db_content = DocumentContentDB(
            id=doc_id,
            content_html=content_html
        )
        self.session.add(db_content)
        self.session.commit()
        return db_content
    
    def get_by_id(self, doc_id: int) -> Optional[DocumentContentDB]:
        return self.session.query(DocumentContentDB).filter_by(id=doc_id).first()

_db_manager: Optional[DatabaseManager] = None

def init_database(db_path: Optional[str] = None, db_type: str = "sqlite") -> DatabaseManager:
    global _db_manager
    config = DatabaseConfig(db_path=db_path, db_type=db_type)
    _db_manager = DatabaseManager(config)
    _db_manager.create_tables()
    return _db_manager

def get_database() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = init_database()
    return _db_manager

def get_session() -> Session:
    return get_database().get_session()
