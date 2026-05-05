from typing import Optional
from dataclasses import dataclass
from pathlib import Path
from .enums import FolderType


@dataclass
class DocumentInfo:
    """Thông tin tài liệu"""
    file_path: Path
    folder_type: FolderType
    metadata: Optional[dict] = None

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
