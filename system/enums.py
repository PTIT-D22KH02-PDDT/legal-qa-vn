from enum import Enum
class FolderType(str, Enum):
    """Loại folder dựa trên tên thư mục"""
    LUAT = "luat"
    NGHI_DINH = "nghi_dinh"
    NGHI_QUYET = "nghi_quyet"
    THONG_TU = "thong_tu"
    SUA_DOI_BO_SUNG = "sua_doi_bo_sung"
    THAY_THE = "thay_the"
    BAI_BO = "bai_bo"
    DINH_CHI_HIEU_LUC = "dinh_chi_hieu_luc"
    OTHER = "other"