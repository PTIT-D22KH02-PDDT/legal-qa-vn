import re
from pathlib import Path
from src.core.models import DocumentMetadata
from src.indexing.ingestion import extract_file
from .legal_parser import ParseLegal
from .constants import _LOAI_MAP, _LOAI_DISPLAY, _STOP_STRUCTURE, _RE_DIEU_THI_HANH, _HIEU_LUC_PREFIXES, _DATE_PAT, _CO_QUAN_LIST
from .schemas import ProcessResult


class Extractor:
    """Extract metadata and build document tree from legal text."""
    
    def __init__(self, max_chunk=2000, min_chunk=50):
        self.max_chunk = max_chunk
        self.min_chunk = min_chunk
        self.parser = ParseLegal()

    # Extractors

    def _extract_loai(self, text: str) -> str:
        """
        Tìm dòng loại VB đầu tiên
        - Chỉ check dòng SHORT (< 50 ký tự) - vì "NGHỊ ĐỊNH", "BỘ LUẬT", v.v luôn ngắn
        - Dùng word boundary (\b) để match từ hoàn chỉnh, không substring
        - Bỏ dòng nội dung dài (> 50 ký tự)
        """
        lines = text[:3000].split('\n')
        
        # Order matters: kiểm tra chi tiết trước rồi đến chung chung
        check_order = [
            (r'\bNGHỊ\s+ĐỊNH\b', "nghi_dinh"),
            (r'\bNGHỊ\s+QUYẾT\b', "nghi_quyet"),
            (r'\bTHÔNG\s+TƯ\s+LIÊN\s+TỊCH\b', "thong_tu_lien_tich"),
            (r'\bTHÔNG\s+TƯ\b', "thong_tu"),
            (r'\bQUYẾT\s+ĐỊNH\b', "quyet_dinh"),
            (r'\bCHỈ\s+THỊ\b', "chi_thi"),
            (r'\bBỘ\s+LUẬT\b', "bo_luat"),
            (r'\bLUẬT\b', "luat"),
        ]
        
        # Tìm dòng đầu tiên chứa một loại VB
        for line in lines:
            line_stripped = line.strip()
            line_upper = line_stripped.upper()
            
            # Bỏ dòng trống hoặc quá dài (dòng nội dung thường dài)
            if not line_stripped or len(line_stripped) > 50:
                continue
            
            # Kiểm tra từng pattern theo thứ tự ưu tiên
            for pattern, loai_code in check_order:
                if re.search(pattern, line_upper):
                    return loai_code
        
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
            # return m.group(1).strip().rstrip(".")
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
          BỘ LUẬT → DÂN SỰ   =>  "BỘ LUẬT DÂN SỰ"
          LUẬT    → DOANH NGHIỆP  =>  "LUẬT DOANH NGHIỆP"
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

    # Main
    
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
        Process document: extract text, metadata, and build tree.
        extract_file handles .doc/.docx/.pdf conversion.
        
        Returns: ProcessResult with metadata, tree, md_text
        """
        doc_path = Path(file_path).resolve()
        if not doc_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {doc_path}")

        # Extract text (extract_file handles all formats)
        md_text = extract_file(str(doc_path))
        
        # Extract metadata
        result = ProcessResult()
        result.metadata = self._extract_metadata_doc(
            md_text=md_text,
            file_path=str(doc_path),
            md_path=""
        )
        
        # Generate document id
        doc_id = result.metadata.so_hieu or doc_path.stem
        if not doc_id:
            raise ValueError(f"Không tạo được document id cho {doc_path}")
        result.metadata.so_hieu = doc_id
        
        # Build document tree
        tree = self.parser.build_json_tree(doc_id=doc_id, text=md_text)
        result.tree = tree
        
        return result

    def process_batch(self, file_paths: list[str]) -> list[ProcessResult]:
        """Process multiple files. Individual errors don't stop batch processing."""
        results = []
        for fp in file_paths:
            try:
                results.append(self.process_document(fp))
            except Exception:
                results.append(ProcessResult())
        return results