import re

_LOAI_MAP = {
    "BỘ LUẬT"            : "bo_luat",
    "LUẬT"               : "luat",
    "NGHỊ ĐỊNH"          : "nghi_dinh",
    "THÔNG TƯ LIÊN TỊCH" : "thong_tu_lien_tich",
    "THÔNG TƯ"           : "thong_tu",
    "NGHỊ QUYẾT"         : "nghi_quyet",
    "QUYẾT ĐỊNH"         : "quyet_dinh",
    "CHỈ THỊ"            : "chi_thi",
}

_LOAI_DISPLAY = {v: k for k, v in _LOAI_MAP.items()}

_CO_QUAN_LIST = [
    ("QUỐC HỘI",                       "Quốc Hội"),
    ("ỦY BAN THƯỜNG VỤ QUỐC HỘI",      "Ủy Ban Thường Vụ Quốc Hội"),
    ("THỦ TƯỚNG CHÍNH PHỦ",            "Thủ Tướng Chính Phủ"),
    ("BỘ TÀI CHÍNH",                    "Bộ Tài Chính"),
    ("BỘ TƯ PHÁP",                      "Bộ Tư Pháp"),
    ("BỘ CÔNG AN",                      "Bộ Công An"),
    ("BỘ QUỐC PHÒNG",                   "Bộ Quốc Phòng"),
    ("BỘ Y TẾ",                         "Bộ Y Tế"),
    ("BỘ GIÁO DỤC VÀ ĐÀO TẠO",         "Bộ Giáo Dục Và Đào Tạo"),
    ("BỘ KẾ HOẠCH VÀ ĐẦU TƯ",          "Bộ Kế Hoạch Và Đầu Tư"),
    ("BỘ CÔNG THƯƠNG",                  "Bộ Công Thương"),
    ("BỘ LAO ĐỘNG",                     "Bộ Lao Động - Thương Binh Và Xã Hội"),
    ("BỘ NÔNG NGHIỆP",                  "Bộ Nông Nghiệp Và Phát Triển Nông Thôn"),
    ("BỘ GIAO THÔNG VẬN TẢI",          "Bộ Giao Thông Vận Tải"),
    ("BỘ XÂY DỰNG",                     "Bộ Xây Dựng"),
    ("BỘ TÀI NGUYÊN VÀ MÔI TRƯỜNG",    "Bộ Tài Nguyên Và Môi Trường"),
    ("BỘ THÔNG TIN VÀ TRUYỀN THÔNG",   "Bộ Thông Tin Và Truyền Thông"),
    ("BỘ NGOẠI GIAO",                   "Bộ Ngoại Giao"),
    ("BỘ NỘI VỤ",                       "Bộ Nội Vụ"),
    ("BỘ VĂN HÓA",                      "Bộ Văn Hóa, Thể Thao Và Du Lịch"),
    ("BỘ KHOA HỌC VÀ CÔNG NGHỆ",       "Bộ Khoa Học Và Công Nghệ"),
    ("CHÍNH PHỦ",                       "Chính Phủ"),
    ("NGÂN HÀNG NHÀ NƯỚC",             "Ngân Hàng Nhà Nước"),
    ("KIỂM TOÁN NHÀ NƯỚC",             "Kiểm Toán Nhà Nước"),
    ("VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO", "Viện Kiểm Sát Nhân Dân Tối Cao"),
    ("TÒA ÁN NHÂN DÂN TỐI CAO",        "Tòa Án Nhân Dân Tối Cao"),
    ("ỦY BAN NHÂN DÂN",                "Ủy Ban Nhân Dân"),
    ("HỘI ĐỒNG NHÂN DÂN",              "Hội Đồng Nhân Dân"),
]

_STOP_STRUCTURE = {"PHẦN", "CHƯƠNG", "MỤC", "ĐIỀU", "CĂN CỨ"}

_RE_DIEU_THI_HANH = re.compile(
    r"^Điều\s+\d+[a-z]?\.\s+"
    r"(?:"
        r"(?:Điều\s+khoản\s+)?[Hh]iệu\s+lực\s+thi\s+hành"
        r"|(?:Điều\s+khoản\s+)?[Hh]iệu\s+lực\s+v[àa]\s+(?:\w+\s+)?thi\s+hành"
        r"|Điều\s+khoản\s+thi\s+hành"
        r"|Tổ\s+chức\s+thực\s+hiện"
        r"|Trách\s+nhiệm\s+thi\s+hành"
    r")"
    r"[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)

_DATE_PAT = r"\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})"

_HIEU_LUC_PREFIXES = [
    r"có\s+hiệu\s+lực\s+(?:thi\s+hành\s+)?(?:từ\s+ngày|kể\s+từ\s+ngày)",
    r"hiệu\s+lực\s+(?:từ\s+ngày|kể\s+từ\s+ngày)",
    r"(?:thi\s+hành|áp\s+dụng)\s+(?:từ\s+ngày|kể\s+từ\s+ngày)",
]

VIETNAMESE_NUM_MAP = {
    'nhất': '1', 'một': '1',
    'hai': '2',
    'ba': '3',
    'bốn': '4', 'tư': '4',
    'năm': '5',
    'sáu': '6',
    'bảy': '7',
    'tám': '8',
    'chín': '9',
    'mười': '10',
    'mười một': '11',
    'mười hai': '12',
    'mười ba': '13',
    'mười bốn': '14',
    'mười năm': '15',
    'mười sáu': '16',
    'mười bảy': '17',
    'mười tám': '18',
    'mười chín': '19',
    'hai mươi': '20',
    'ba mươi': '30',
    'bốn mươi': '40',
    'tư mươi': '40',
    'năm mươi': '50',
    'sáu mươi': '60',
    'bảy mươi': '70',
    'tám mươi': '80',
    'chín mươi': '90',
}

ROMAN_NUM_MAP = {
    'i': '1', 'I': '1',
    'ii': '2', 'II': '2',
    'iii': '3', 'III': '3',
    'iv': '4', 'IV': '4',
    'v': '5', 'V': '5',
    'vi': '6', 'VI': '6',
    'vii': '7', 'VII': '7',
    'viii': '8', 'VIII': '8',
    'ix': '9', 'IX': '9',
    'x': '10', 'X': '10',   
}

BOUNDARY_SECTION_PATTERNS = {
    'phu_luc': r'(?i)^phụ\s+lục\s+(?:(i{1,3}|[a-zđ]|\d+))?(?:\s*[\.\:\)]|$)',
    'muc_luc': r'(?i)^mục\s+lục(?:\s*[\.\:\)]|$)',
    'tu_viet_tat': r'(?i)^(?:danh\s+mục\s+)?(?:từ|chữ)\s+viết\s+tắt(?:\s*[\.\:\)]|$)',
    'noi_nhan': r'(?i)^nơi\s+nhận\s*[\:\.]?$',
    'chu_ky': r'(?i)^(?:kt\.|kí\s+tên|chữ\s+ký)(?:\s|$)',
}

STOP_HEADING_TYPES = {'phu_luc', 'muc_luc', 'tu_viet_tat', 'noi_nhan', 'chu_ky'}