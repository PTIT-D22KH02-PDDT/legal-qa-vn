import re
import json
from dataclasses import dataclass
from pathlib import Path
import tempfile
from src.schemas import DocumentMetadata,HierarchicalChunkInput
from src.core.ingestion.extractor import extract_file
from src.core.chunker.legal_parser import ParseLegal
from src.core.ingestion.convert_doc_to_docx import convert_doc_to_docx
from typing import Union,Dict,Any,List
@dataclass
class ProcessResult:
    metadata: DocumentMetadata|None = None
    tree : Union[HierarchicalChunkInput |Dict[str, Any] | List[Dict[str, Any]], None] =None
    md_text: str = ""


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
    ("CHÍNH PHỦ",                       "Chính Phủ"),
    ("NGÂN HÀNG NHÀ NƯỚC",             "Ngân Hàng Nhà Nước"),
    ("KIỂM TOÁN NHÀ NƯỚC",             "Kiểm Toán Nhà Nước"),
    ("VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO", "Viện Kiểm Sát Nhân Dân Tối Cao"),
    ("TÒA ÁN NHÂN DÂN TỐI CAO",        "Tòa Án Nhân Dân Tối Cao"),
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
    ("ỦY BAN NHÂN DÂN",                "Ủy Ban Nhân Dân"),
    ("HỘI ĐỒNG NHÂN DÂN",              "Hội Đồng Nhân Dân"),
]

_STOP_STRUCTURE = {"PHẦN", "CHƯƠNG", "MỤC", "ĐIỀU", "CĂN CỨ"}

# Sau khi clean markdown, không còn ** nên bỏ hết \*\*
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


class Extractor:
    def __init__(self, max_chunk=2000, min_chunk=50):
        self.max_chunk = max_chunk
        self.min_chunk = min_chunk
        self.parser=ParseLegal()

        # Sau khi clean markdown, không còn ** nên bỏ hết \*{0,2}
        self.phan = re.compile(
            r"^(Phần\s+(?:thứ\s+)?(?:nhất|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|\d+))\s*$",
            re.IGNORECASE,
        )
        self.chuong = re.compile(
            r"^(Chương\s+(?:[IVXLCDM]+|\d+))\s*$",
            re.IGNORECASE,
        )
        self.muc = re.compile(
            r"^(Mục\s+\d+[a-z]?\.?\s*.+?)\s*$",
            re.IGNORECASE,
        )
        self.dieu = re.compile(
            r"^(Điều\s+(\d+[a-z]?)\.?\s*(.*))\s*$",
            re.IGNORECASE,
        )
        self.khoan = re.compile(r"^(\d+)\.\s+(.+)", re.DOTALL)
        self.diem  = re.compile(r"^([a-zđ])\)\s+(.+)", re.DOTALL)
        self.ngay  = re.compile(
            r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            re.IGNORECASE,
        )

    # -------------------------------------------------------------------------
    # Extractors
    # -------------------------------------------------------------------------

    def _extract_loai(self, text: str) -> str:
        header = text[:2000].upper()
        if "BỘ LUẬT" in header:
            return "bo_luat"
        if "LUẬT" in header:
            return "luat"
        if "THÔNG TƯ LIÊN TỊCH" in header:
            return "thong_tu_lien_tich"
        if "THÔNG TƯ" in header:
            return "thong_tu"
        if "NGHỊ ĐỊNH" in header:
            return "nghi_dinh"
        if "NGHỊ QUYẾT" in header:
            return "nghi_quyet"
        if "QUYẾT ĐỊNH" in header:
            return "quyet_dinh"
        if "CHỈ THỊ" in header:
            return "chi_thi"
        return "unknown"

    def _extract_so_hieu(self, text: str) -> str:
        """Lấy số hiệu thuần: '91/2015/QH13', '78/2015/NĐ-CP', '01/2020/TT-BTC'"""
        m = re.search(
            r"(?:Luật\s+số|Nghị\s+định\s+số|Thông\s+tư\s+số|Nghị\s+quyết\s+số"
            r"|Quyết\s+định\s+số|Chỉ\s+thị\s+số|Số)\s*[:\-]?\s*"
            r"(\d+/\d{4}/[\w\-]+)",
            text[:3000], re.IGNORECASE,
        )
        if m:
            x = m.group(1)
            s = re.sub(r"[^a-zA-Z0-9đĐ\-]+", "_", x)
            return s.lower().strip('_')
            return m.group(1).strip().rstrip(".")
        # Fallback: pattern số hiệu đứng độc lập
        m = re.search(r"\b(\d+/\d{4}/[\w\-]+)\b", text[:3000])
        if m:
            x=m.group(1)
            s = re.sub(r"[^a-zA-Z0-9đĐ\-]+", "_", x)
            return s.lower().strip('_')
        return ""

    def _extract_ten_van_ban(self, text: str, loai: str) -> str:
        """
        Text đã clean (không còn **) → tìm dòng ALL CAPS ngắn ở đầu văn bản
        ngay sau dòng khai báo loại VB.
          BỘ LUẬT → DÂN SỰ   ⟹  "BỘ LUẬT DÂN SỰ"
          LUẬT    → DOANH NGHIỆP  ⟹  "LUẬT DOANH NGHIỆP"
        """
        found_type = False
        parts = []

        for line in text[:3000].splitlines():
            bl = line.strip()
            if not bl:
                continue
            bu = bl.upper()

            # Bỏ dòng header quốc gia
            if any(kw in bu for kw in {"QUỐC HỘI", "CỘNG HÒA", "ĐỘC LẬP", "HÀ NỘI"}):
                continue

            # Gặp dòng loại VB → bật cờ
            if bu in _LOAI_MAP:
                found_type = True
                continue

            if found_type:
                # Dừng khi gặp từ khoá cấu trúc
                if any(bu.startswith(s) for s in _STOP_STRUCTURE):
                    break
                # Dừng khi tỷ lệ chữ hoa thấp (dòng nội dung thường)
                if len(bl) > 10 and sum(c.isupper() for c in bl) / len(bl) < 0.4:
                    break
                if not re.match(r'^[\-\s]+$', bl):
                    parts.append(bl)
                if len(parts) >= 2:
                    break

        ten_ngan = " ".join(parts)
        prefix = _LOAI_DISPLAY.get(loai, "")
        return f"{prefix} {ten_ngan}".strip() if prefix else ten_ngan

    def _extract_co_quan_ban_hanh(self, text: str) -> str:
        header = text[:2000].upper()
        for keyword, display in _CO_QUAN_LIST:
            if keyword in header:
                return display
        return ""

    def _parse_date_from_match(self, m: re.Match) -> str:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"

    def _extract_ngay_ban_hanh(self, text: str) -> str:
        # "Hà Nội, ngày X tháng Y năm Z"
        m = re.search(
            r"(?:Hà\s+Nội|TP\.?\s*Hồ\s+Chí\s+Minh|[A-ZĐÁÀẢÃẠ]\w+),?\s*"
            r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            text[:4000], re.IGNORECASE,
        )
        if m:
            return self._parse_date_from_match(m)
        # "thông qua ngày X..."
        m = re.search(
            r"thông\s+qua\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            text, re.IGNORECASE,
        )
        if m:
            return self._parse_date_from_match(m)
        return ""

    def _extract_ngay_co_hieu_luc(self, text: str, ngay_ban_hanh: str) -> str:
        """
        Bước 1 — Tìm Điều có tên "Hiệu lực thi hành" / "Điều khoản thi hành" / ...
                  → chỉ đọc nội dung Điều đó, tránh nhiễu từ phụ lục dài ở cuối
        Bước 2 — Fallback: tìm trong toàn văn bản
        Bước 3 — "kể từ ngày ký" → dùng ngày ban hành
        """
        # Bước 1
        for m in _RE_DIEU_THI_HANH.finditer(text):
            scope = text[m.end(): m.end() + 1000]
            for pref in _HIEU_LUC_PREFIXES:
                found = re.search(pref + _DATE_PAT, scope, re.IGNORECASE)
                if found:
                    return self._parse_date_from_match(found)

        # Bước 2
        for pref in _HIEU_LUC_PREFIXES:
            found = re.search(pref + _DATE_PAT, text, re.IGNORECASE)
            if found:
                return self._parse_date_from_match(found)

        # Bước 3
        if re.search(r"có\s+hiệu\s+lực\s+kể\s+từ\s+ngày\s+ký", text, re.IGNORECASE):
            return ngay_ban_hanh

        return ""

    def _count_so_dieu(self, text: str) -> int:
        """Đếm dòng tiêu đề Điều (text đã clean, không còn **)."""
        return len(re.findall(r'^\s*Điều\s+\d+[a-zA-Z]?\.', text, re.MULTILINE))

    # -------------------------------------------------------------------------
    # Main
    # -------------------------------------------------------------------------

    def _extract_metadata_doc(
        self, file_path: str, md_path: str, md_text: str = ""
    ) -> DocumentMetadata:
        data = DocumentMetadata(file_path=file_path, md_path=md_path)
        data.loai             = self._extract_loai(md_text)
        data.so_hieu          = self._extract_so_hieu(md_text)
        data.ten_van_ban      = self._extract_ten_van_ban(md_text, data.loai)
        data.co_quan_ban_hanh = self._extract_co_quan_ban_hanh(md_text)
        data.ngay_ban_hanh    = self._extract_ngay_ban_hanh(md_text)
        data.ngay_co_hieu_luc = self._extract_ngay_co_hieu_luc(md_text, data.ngay_ban_hanh)
        data.so_dieu          = self._count_so_dieu(md_text)
        return data

    def process_document(self, file_path: str) -> ProcessResult:
        """
        Bước 1: Convert .doc → .docx (nếu cần)
        Bước 2: Convert .docx → markdown
        Bước 3: Đọc markdown đã clean
        Bước 4: extract_metadata
        Bước 5: chunk_document
        """
        doc_path = Path(file_path).resolve()
        if not doc_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {doc_path}")

        result = ProcessResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)

            # Bước 1
            print(f"[DEBUG] Bước 1: Convert .doc → .docx (nếu cần)")
            if doc_path.suffix.lower() == ".doc":
                print(f"[DEBUG] Đang convert {doc_path.name} từ .doc sang .docx...")
                docx_path = convert_doc_to_docx(doc_path, tmp_dir)
                print(f"[DEBUG] Convert xong: {docx_path}")
            else:
                docx_path = doc_path
                print(f"[DEBUG] File đã là .docx, skip convert")
            
            # Bước 2
            print(f"[DEBUG] Bước 2: Extract text từ docx...")
            current_file=Path(__file__).resolve()
            parent_dir=current_file.parents[3]
            output_dir = parent_dir / "mark_down"
            output_dir.mkdir(parents=True, exist_ok=True)
            md_path=output_dir / (doc_path.stem + ".md")
            print(f"[DEBUG] Đang extract file: {docx_path}")
            md_text=extract_file(docx_path)
            print(f"[DEBUG] Extract thành công, lưu vào {md_path}")
            with open(str(md_path), "w", encoding="utf-8") as f:
                f.write(md_text)
                f.close()
            
            # Bước 3
            print(f"[DEBUG] Bước 3: Extract metadata...")
            result.metadata = self._extract_metadata_doc(
                md_text=md_text,
                file_path=str(doc_path),
                md_path=str(md_path),
            )
            print(f"[DEBUG] Metadata: so_hieu={result.metadata.so_hieu}, ten_van_ban={result.metadata.ten_van_ban}")
            
            # Bước 4
            print(f"[DEBUG] Bước 4: Build JSON tree...")
            tree = self.parser.build_json_tree(doc_id=result.metadata.so_hieu, text=md_text)
            print(f"[DEBUG] Tree xong, có {len(tree)} nodes")
            
            json_path = parent_dir / "json"
            json_path.mkdir(parents=True, exist_ok=True)
            json_file_path = json_path / (result.metadata.so_hieu + ".jsonl")
            
            print(f"[DEBUG] Bước 5: Lưu JSON vào {json_file_path}")
            data = {
                'metadata': result.metadata.model_dump(),
                'tree': tree,
            }
            result.tree=tree
            with open(json_file_path, "w", encoding="utf-8") as f:
                # Chuyển dict thành chuỗi JSON và thêm dấu xuống dòng \n cho đúng định dạng jsonl
                line = json.dumps(data, ensure_ascii=False)
                f.write(line + "\n")
            print(f"[DEBUG] Hoàn thành!")
        return result

    def process_batch(self, file_paths: list[str]) -> list[ProcessResult]:
        """Xử lý nhiều file. Lỗi từng file không dừng batch."""
        results = []
        for fp in file_paths:
            try:
                r = self.process_document(fp)
                m = r.metadata
                print(f"{Path(fp).name:40s} | {m.so_hieu:20s} | {m.ten_van_ban}")
                results.append(r)
            except Exception as e:
                print(f"{Path(fp).name}: {e}")
                results.append(ProcessResult())
        return results

# if __name__ == "__main__":
#     current_file=Path(__file__).resolve()
#     parent_dir=current_file.parents[3]
#     print(parent_dir)