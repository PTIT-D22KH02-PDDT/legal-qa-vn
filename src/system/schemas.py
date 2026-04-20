from typing import Optional
from dataclasses import dataclass
from pathlib import Path
from src.core.models import DocumentMetadata
from src.core.enums import RelationType
from .enums import FolderType


@dataclass
class DocumentInfo:
    """Thông tin tài liệu"""
    file_path: Path
    folder_type: FolderType
    metadata: Optional[DocumentMetadata] = None
    
    @property
    def doc_id(self) -> str:
        """Lấy document ID từ metadata hoặc filename"""
        if self.metadata and hasattr(self.metadata, 'so_hieu'):
            return self.metadata.so_hieu
        return self.file_path.stem

class FolderTypeDetector:
    """Phát hiện loại folder từ tên thư mục"""
    
    FOLDER_MAPPING = {
        "luat": FolderType.LUAT,
        "nghi_dinh": FolderType.NGHI_DINH,
        "nghi_quyet": FolderType.NGHI_QUYET,
        "thong_tu": FolderType.THONG_TU,
        "sua_doi_bo_sung": FolderType.SUA_DOI_BO_SUNG,
        "thay_the": FolderType.THAY_THE,
        "bai_bo": FolderType.BAI_BO,
        "dinh_chi_hieu_luc": FolderType.DINH_CHI_HIEU_LUC,
    }
    
    @classmethod
    def detect(cls, folder_name: str) -> FolderType:
        """Phát hiện loại folder từ tên"""
        folder_lower = folder_name.lower().strip()
        
        for key, folder_type in cls.FOLDER_MAPPING.items():
            if key in folder_lower or folder_lower in key:
                return folder_type
        
        return FolderType.OTHER


class RelationTypeDeterminer:
    """Xác định loại quan hệ giữa hai folder"""
    
    @staticmethod
    def get_relation_type(
        source_folder: FolderType,
        target_folder: FolderType
    ) -> Optional[RelationType]:
        """
        Xác định RelationType dựa trên loại source và target folder
        
        Args:
            source_folder: Folder chứa tài liệu gốc
            target_folder: Folder chứa tài liệu tham chiếu (thường là "luật")
        
        Returns:
            RelationType hoặc None nếu không có quan hệ
        """
        
        # Nếu target không phải "luật" thì skip
        if target_folder != FolderType.LUAT:
            return None
        
        # Xác định relation type dựa trên source folder
        relation_map = {
            FolderType.SUA_DOI_BO_SUNG: RelationType.sua_doi_bo_sung,
            FolderType.THAY_THE: RelationType.thay_the,
            FolderType.BAI_BO: RelationType.bai_bo,
            FolderType.DINH_CHI_HIEU_LUC: RelationType.dinh_chi_hieu_luc,
            FolderType.NGHI_DINH: RelationType.huong_dan_thi_hanh,
            FolderType.NGHI_QUYET: RelationType.huong_dan_thi_hanh,
            FolderType.THONG_TU: RelationType.huong_dan_thi_hanh,
        }
        
        return relation_map.get(source_folder)
