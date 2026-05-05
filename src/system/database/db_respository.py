from src.core.enums import RelationType
from src.core.models import DocumentMetadata, DocumentRelation
from typing import List, Optional
from pathlib import Path
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker
import logging
from datetime import datetime
from .db import DocumentRelationDB, DocumentMetadataDB, Base  # ✅ Import Base từ db.py

logger = logging.getLogger(__name__)
class DatabaseConfig:
    """Database configuration"""
    
    def __init__(self, db_path: Optional[str] = None, db_type: str = "sqlite"):
        """
        Initialize database config
        Args:
            db_path: Path to database (for SQLite)
            db_type: 'sqlite', 'postgresql', etc.
        """
        self.db_type = db_type
        if db_type == "sqlite":
            if db_path is None:
                # Default: project_root/legal_documents.db
                # File này ở src/system/database/, nên cần parents[3] để ra project root
                db_path = str(Path(__file__).resolve().parents[3] / "legal_documents.db")
            self.db_url = f"sqlite:///{db_path}"
        elif db_type == "postgresql":
            if db_path is None:
                raise ValueError("PostgreSQL connection string required")
            self.db_url = db_path
        else:
            raise ValueError(f"Unsupported DB type: {db_type}")
        
        self.echo = False  # Set to True for SQL logging


class DatabaseManager:
    """Database connection and session management"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = None
        self.SessionLocal = None
        self._initialize()
    
    def _initialize(self):
        """Initialize database engine and session factory"""
        self.engine = create_engine(
            self.config.db_url,
            echo=self.config.echo,
            connect_args={"check_same_thread": False} if "sqlite" in self.config.db_url else {}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        logger.info(f"Database initialized: {self.config.db_url}")
    
    def create_tables(self):
        """Create all tables in database"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

class DocumentMetadataRepository:
    """CRUD operations for DocumentMetadata"""
    def __init__(self, session: Session):
        self.session = session
    def create(self, metadata: DocumentMetadata) -> DocumentMetadataDB:
        """
        Lưu DocumentMetadata vào database
        Args:
            metadata: DocumentMetadata object
        Returns:
            DocumentMetadataDB
        """
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
        logger.info(f"Created metadata: {metadata.so_hieu}")
        return db_metadata
    
    def get_by_so_hieu(self, so_hieu: str) -> Optional[DocumentMetadataDB]:
        """Lấy metadata theo so_hieu"""
        return self.session.query(DocumentMetadataDB).filter_by(so_hieu=so_hieu).first()
    
    def get_by_loai(self, loai: str) -> List[DocumentMetadataDB]:
        """Lấy tất cả metadata theo loại (Luật, Nghị định, etc.)"""
        return self.session.query(DocumentMetadataDB).filter_by(loai=loai).all()

    def search_by_name(
        self,
        name: str,
        limit: int = 20,
    ) -> List[DocumentMetadataDB]:
        """
        Tìm metadata theo tên văn bản HOẶC số hiệu dùng SQL LIKE (case-insensitive).

        Dùng cho workflow: người dùng nói tên dân dã ("bộ luật dân sự") →
        caller sau đó rerank bằng fuzzy matching để chọn văn bản khớp nhất.

        Args:
            name: phần tên/ từ khoá cần tìm. Sẽ tách theo khoảng trắng để
                lọc các row có chứa TẤT CẢ token (AND), giúp giảm nhiễu khi
                tên dài (vd "bộ luật dân sự" → token: bo, luat, dan, su).
            limit: số kết quả tối đa trả về (trước khi rerank phía caller).
        """
        name = (name.upper() or "").strip()
        if not name:
            return []

        query = self.session.query(DocumentMetadataDB)

        # Tách token, bỏ token quá ngắn (<2) để tránh match ngẫu nhiên
        tokens = [t for t in name.split() if len(t) >= 2]
        if not tokens:
            tokens = [name]

        # Mỗi token phải xuất hiện trong ten_van_ban HOẶC so_hieu
        for tok in tokens:
            like = f"%{tok}%"
            query = query.filter(
                or_(
                    DocumentMetadataDB.ten_van_ban.ilike(like),
                    DocumentMetadataDB.so_hieu.ilike(like),
                )
            )

        return query.limit(limit).all()

    def get_all(self, limit: int = 100, offset: int = 0) -> List[DocumentMetadataDB]:
        """Lấy tất cả metadata (có phân trang)"""
        return self.session.query(DocumentMetadataDB).limit(limit).offset(offset).all()
    
    def update(self, so_hieu: str, **kwargs) -> Optional[DocumentMetadataDB]:
        """Cập nhật metadata"""
        db_metadata = self.get_by_so_hieu(so_hieu)
        if db_metadata:
            for key, value in kwargs.items():
                if hasattr(db_metadata, key):
                    setattr(db_metadata, key, value)
            db_metadata.updated_at = datetime.utcnow()
            self.session.commit()
            logger.info(f"Updated metadata: {so_hieu}")
        return db_metadata
    
    def delete(self, so_hieu: str) -> bool:
        """Xóa metadata"""
        db_metadata = self.get_by_so_hieu(so_hieu)
        if db_metadata:
            self.session.delete(db_metadata)
            self.session.commit()
            logger.info(f"Deleted metadata: {so_hieu}")
            return True
        return False
    
    def exists(self, so_hieu: str) -> bool:
        """Kiểm tra metadata đã tồn tại"""
        return self.get_by_so_hieu(so_hieu) is not None


class DocumentRelationRepository:
    """CRUD operations for DocumentRelation"""
    def __init__(self, session: Session):
        self.session = session
    def create(self, relation: DocumentRelation) -> DocumentRelationDB:
        """
        Lưu DocumentRelation vào database
        Args:
            relation: DocumentRelation object
        Returns:
            DocumentRelationDB
        """
        db_relation = DocumentRelationDB(
            entity_start=relation.entity_start,
            entity_end=relation.entity_end,
            relation_type=relation.relation_type,
            description=relation.description
        )
        self.session.add(db_relation)
        self.session.commit()
        logger.info(f"Created relation: {relation.entity_start} --[{relation.relation_type.value}]--> {relation.entity_end}")
        return db_relation
    
    def get_by_id(self, relation_id: int) -> Optional[DocumentRelationDB]:
        """Lấy relation theo ID"""
        return self.session.query(DocumentRelationDB).filter_by(id=relation_id).first()
    
    def get_relations_from(self, entity_start: str) -> List[DocumentRelationDB]:
        """Lấy tất cả relation từ một entity"""
        return self.session.query(DocumentRelationDB).filter_by(entity_start=entity_start).all()
    
    def get_relations_to(self, entity_end: str) -> List[DocumentRelationDB]:
        """Lấy tất cả relation tới một entity"""
        return self.session.query(DocumentRelationDB).filter_by(entity_end=entity_end).all()
    
    def get_by_type(self, relation_type: RelationType) -> List[DocumentRelationDB]:
        """Lấy tất cả relation theo loại (sua_doi_bo_sung, huong_dan_thi_hanh, etc.)"""
        return self.session.query(DocumentRelationDB).filter_by(relation_type=relation_type).all()
    
    def get_related_documents(self, so_hieu: str) -> dict:
        """
        Lấy tất cả tài liệu liên quan đến một tài liệu
        Returns:
            {
                'related_from': [relations as source],
                'related_to': [relations as target]
            }
        """
        return {
            'related_from': self.get_relations_from(so_hieu),
            'related_to': self.get_relations_to(so_hieu)
        }
    
    def get_all(self, limit: int = 100, offset: int = 0) -> List[DocumentRelationDB]:
        """Lấy tất cả relation (có phân trang)"""
        return self.session.query(DocumentRelationDB).limit(limit).offset(offset).all()
    
    def delete(self, relation_id: int) -> bool:
        """Xóa relation"""
        db_relation = self.get_by_id(relation_id)
        if db_relation:
            self.session.delete(db_relation)
            self.session.commit()
            logger.info(f"Deleted relation: {relation_id}")
            return True
        return False
    
    def count_all(self) -> int:
        """Đếm tổng số relation"""
        return self.session.query(DocumentRelationDB).count()



_db_manager: Optional[DatabaseManager] = None
def init_database(db_path: Optional[str] = None, db_type: str = "sqlite") -> DatabaseManager:
    """Initialize global database instance"""
    global _db_manager
    config = DatabaseConfig(db_path=db_path, db_type=db_type)
    _db_manager = DatabaseManager(config)
    _db_manager.create_tables()
    return _db_manager
def get_database() -> DatabaseManager:
    """Get global database instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = init_database()
    return _db_manager


def get_session() -> Session:
    """Get a database session"""
    return get_database().get_session()
