from enum import Enum

class RelationType(str, Enum):
    """
    Mối quan hệ giữa các văn bản luật
    """
    # Pho bien
    huong_dan_thi_hanh = "huong_dan_thi_hanh"  # NĐ/TT/NQ hướng dẫn Luật
    sua_doi_bo_sung    = "sua_doi_bo_sung"      # sửa một phần VB khác
    thay_the           = "thay_the"             # thay thế toàn bộ VB cũ
    bai_bo             = "bai_bo"               # bãi bỏ hoàn toàn VB cũ
    dinh_chi_hieu_luc  = "dinh_chi_hieu_luc"   # tạm đình chỉ

    # Đặc thù Nghị quyết
    tam_thoi_ap_dung   = "tam_thoi_ap_dung"    # thí điểm cơ chế chưa có trong Luật
    giai_thich         = "giai_thich"           # QH giải thích chính thức điều khoản Luật

    # Chung
    lien_quan          = "lien_quan"            # tham chiếu nhau, không trực tiếp
    #Quan he giua cac dieu/khoan trong van ban
    tham_chieu         = "tham_chieu"

class ChunkType(str, Enum):
    """
    Loại chunk trong tài liệu
    """
    phan="phan"
    chuong="chuong"
    muc="muc"
    dieu="dieu"
    khoan="khoan"
    diem="diem"
    phu_luc="phu_luc"
    phu_luc_phan="phu_luc_phan"