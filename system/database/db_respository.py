from src.core.models import DocumentMetadata
from typing import List, Optional
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import logging
from datetime import datetime
from .db import DocumentMetadataDB, DocumentContentDB, DocumentLegacyDB, DocumentRelationDB, Base
from src.core.models import DocumentRelation

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration"""
    
    def __init__(self, db_path: Optional[str] = None, db_type: str = "sqlite"):
        self.db_type = db_type
        if db_type == "sqlite":
            if db_path is None:
                db_path = str(Path(__file__).resolve().parents[2] / "database" / "legal_documents.db")
            
            # Đảm bảo thư mục chứa file db tồn tại
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
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
            so_dieu=metadata.so_dieu, 
            linh_vuc = getattr(metadata, 'linh_vuc', 'chưa xác định')
        )
        self.session.add(db_metadata)
        self.session.commit()
        return db_metadata
    
    def get_by_so_hieu(self, so_hieu: str) -> Optional[DocumentMetadataDB]:
        return self.session.query(DocumentMetadataDB).filter_by(so_hieu=so_hieu).first()
    
    def search_by_name(self, name: str, limit: int = 10) -> List[DocumentMetadataDB]:
        """Tìm kiếm văn bản theo tên (sử dụng LIKE). Bổ sung fallback upper/lower cho tiếng Việt."""
        # Query 1: ilike mặc định
        results = self.session.query(DocumentMetadataDB).filter(
            DocumentMetadataDB.ten_van_ban.ilike(f"%{name}%")
        ).limit(limit).all()
        
        # Nếu không có kết quả, thử chuyển toàn bộ sang chữ in hoa 
        # (do SQLite ilike không hỗ trợ case-insensitive tiếng Việt có dấu)
        if not results:
            results = self.session.query(DocumentMetadataDB).filter(
                DocumentMetadataDB.ten_van_ban.like(f"%{name.upper()}%")
            ).limit(limit).all()
            
        # Thử chuyển toàn bộ sang chữ thường
        if not results:
            results = self.session.query(DocumentMetadataDB).filter(
                DocumentMetadataDB.ten_van_ban.like(f"%{name.lower()}%")
            ).limit(limit).all()
            
        # Thử viết hoa chữ cái đầu (Title Case)
        if not results:
            results = self.session.query(DocumentMetadataDB).filter(
                DocumentMetadataDB.ten_van_ban.like(f"%{name.title()}%")
            ).limit(limit).all()
            
        return results

    def get_by_loai(self, loai: str) -> List[DocumentMetadataDB]:
        """Lấy danh sách văn bản theo loại."""
        return self.session.query(DocumentMetadataDB).filter_by(loai=loai).all()

    def search_by_linh_vuc(self, linh_vuc: str, limit: int = 10) -> List[DocumentMetadataDB]:
        """Tìm kiếm văn bản theo lĩnh vực (sử dụng ILIKE để không phân biệt hoa thường)."""
        return self.session.query(DocumentMetadataDB).filter(
            DocumentMetadataDB.linh_vuc.ilike(f"%{linh_vuc}%")
        ).limit(limit).all()

    def get_all(self, limit: int = 10) -> List[DocumentMetadataDB]:
        """Lấy danh sách văn bản."""
        return self.session.query(DocumentMetadataDB).limit(limit).all()

    def exists(self, so_hieu: str) -> bool:
        return self.get_by_so_hieu(so_hieu) is not None

    def update(self, metadata: DocumentMetadata) -> Optional[DocumentMetadataDB]:
        db_metadata = self.get_by_so_hieu(metadata.so_hieu)
        if db_metadata:
            db_metadata.ten_van_ban = metadata.ten_van_ban
            db_metadata.loai = metadata.loai
            db_metadata.co_quan_ban_hanh = metadata.co_quan_ban_hanh
            db_metadata.ngay_ban_hanh = metadata.ngay_ban_hanh
            db_metadata.ngay_co_hieu_luc = metadata.ngay_co_hieu_luc
            db_metadata.file_path = metadata.file_path
            db_metadata.so_dieu = metadata.so_dieu
            self.session.commit()
        return db_metadata

    def update_trang_thai(self, so_hieu: str, trang_thai: int) -> bool:
        """Cập nhật trạng thái hiệu lực của văn bản (1=còn hiệu lực, 0=hết hiệu lực)."""
        db_metadata = self.get_by_so_hieu(so_hieu)
        if not db_metadata:
            return False
        db_metadata.trang_thai = trang_thai
        self.session.commit()
        return True

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

class DocumentRelationRepository:
    """CRUD operations for DocumentRelation"""
    def __init__(self, session: Session):
        self.session = session

    def exists_triple(
        self,
        entity_start: Optional[str],
        entity_end: Optional[str],
        relation_type: str,
    ) -> bool:
        row = (
            self.session.query(DocumentRelationDB)
            .filter_by(
                entity_start=entity_start,
                entity_end=entity_end,
                relation_type=relation_type,
            )
            .first()
        )
        return row is not None
    
    def create(self, relation: DocumentRelation) -> DocumentRelationDB:
        # Xử lý enum relation_type nếu cần
        rel_type = relation.relation_type.value if hasattr(relation.relation_type, 'value') else str(relation.relation_type)
        
        db_relation = DocumentRelationDB(
            entity_start=relation.entity_start,
            entity_end=relation.entity_end,
            relation_type=rel_type,
            description=relation.description
        )
        self.session.add(db_relation)
        self.session.commit()
        return db_relation

    def delete_by_id(self, relation_id: int) -> bool:
        """Xóa một quan hệ theo khóa chính `id`. Trả về True nếu đã xóa được bản ghi."""
        row = self.session.query(DocumentRelationDB).filter_by(id=relation_id).first()
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def delete_by_triple(
        self,
        entity_start: Optional[str],
        entity_end: Optional[str],
        relation_type: str,
    ) -> int:
        """
        Xóa mọi quan hệ trùng bộ (entity_start, entity_end, relation_type).
        Trả về số dòng đã xóa.
        """
        deleted = (
            self.session.query(DocumentRelationDB)
            .filter_by(
                entity_start=entity_start,
                entity_end=entity_end,
                relation_type=relation_type,
            )
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return deleted

    def get_relations_by_entity(self, so_hieu: str):
        """Lấy tất cả các quan hệ mà văn bản tham gia (cả start và end)."""
        relations_start = self.session.query(DocumentRelationDB).filter(DocumentRelationDB.entity_start == so_hieu).all()
        relations_end = self.session.query(DocumentRelationDB).filter(DocumentRelationDB.entity_end == so_hieu).all()
        return relations_start, relations_end

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
