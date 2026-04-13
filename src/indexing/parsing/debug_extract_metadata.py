"""Debug version with logging and file I/O (markdown, json output)."""
import re
import json
from pathlib import Path
import tempfile
from src.core.models import DocumentMetadata
from src.indexing.ingestion import extract_file
from .legal_parser import ParseLegal
from .constants import _LOAI_MAP, _LOAI_DISPLAY, _STOP_STRUCTURE, _RE_DIEU_THI_HANH, _HIEU_LUC_PREFIXES, _DATE_PAT, _CO_QUAN_LIST
from .schemas import ProcessResult


class DebugExtractor:
    """Debug version with verbose logging and saves md/json files."""
    
    def __init__(self, max_chunk=2000, min_chunk=50):
        self.max_chunk = max_chunk
        self.min_chunk = min_chunk
        self.parser = ParseLegal()

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
        m = re.search(r"\b(\d+/\d{4}/[\w\-]+)\b", text[:3000])
        if m:
            x = m.group(1)
            s = re.sub(r"[^a-zA-Z0-9đĐ\-]+", "_", x)
            return s.lower().strip('_')
        return ""

    def _extract_ten_van_ban(self, text: str, loai: str) -> str:
        """Tìm dòng ALL CAPS ở đầu văn bản."""
        found_type = False
        parts = []

        for line in text[:3000].splitlines():
            bl = line.strip()
            if not bl:
                continue
            bu = bl.upper()

            if any(kw in bu for kw in {"QUỐC HỘI", "CỘNG HÒA", "ĐỘC LẬP", "HÀ NỘI"}):
                continue

            if bu in _LOAI_MAP:
                found_type = True
                continue

            if found_type:
                if any(bu.startswith(s) for s in _STOP_STRUCTURE):
                    break
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
        m = re.search(
            r"(?:Hà\s+Nội|TP\.?\s*Hồ\s+Chí\s+Minh|[A-ZĐÁÀẢÃẠ]\w+),?\s*"
            r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            text[:4000], re.IGNORECASE,
        )
        if m:
            return self._parse_date_from_match(m)
        m = re.search(
            r"thông\s+qua\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            text, re.IGNORECASE,
        )
        if m:
            return self._parse_date_from_match(m)
        return ""

    def _extract_ngay_co_hieu_luc(self, text: str, ngay_ban_hanh: str) -> str:
        for m in _RE_DIEU_THI_HANH.finditer(text):
            scope = text[m.end(): m.end() + 1000]
            for pref in _HIEU_LUC_PREFIXES:
                found = re.search(pref + _DATE_PAT, scope, re.IGNORECASE)
                if found:
                    return self._parse_date_from_match(found)

        for pref in _HIEU_LUC_PREFIXES:
            found = re.search(pref + _DATE_PAT, text, re.IGNORECASE)
            if found:
                return self._parse_date_from_match(found)

        if re.search(r"có\s+hiệu\s+lực\s+kể\s+từ\s+ngày\s+ký", text, re.IGNORECASE):
            return ngay_ban_hanh

        return ""

    def _count_so_dieu(self, text: str) -> int:
        return len(re.findall(r'^\s*Điều\s+\d+[a-zA-Z]?\.', text, re.MULTILINE))

    def _extract_metadata_doc(
        self, file_path: str, md_path: str, md_text: str = ""
    ) -> DocumentMetadata:
        data = DocumentMetadata(file_path=file_path, md_path=md_path)
        data.loai = self._extract_loai(md_text)
        data.so_hieu = self._extract_so_hieu(md_text)
        data.ten_van_ban = self._extract_ten_van_ban(md_text, data.loai)
        data.co_quan_ban_hanh = self._extract_co_quan_ban_hanh(md_text)
        data.ngay_ban_hanh = self._extract_ngay_ban_hanh(md_text)
        data.ngay_co_hieu_luc = self._extract_ngay_co_hieu_luc(md_text, data.ngay_ban_hanh)
        data.so_dieu = self._count_so_dieu(md_text)
        return data

    def process_document(self, file_path: str) -> ProcessResult:
        """Debug version - saves md/json files and prints debug info."""
        doc_path = Path(file_path).resolve()
        if not doc_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {doc_path}")

        result = ProcessResult()

        # Setup output dirs
        current_file = Path(__file__).resolve()
        parent_dir = current_file.parents[3]
        
        md_dir = parent_dir / "mark_down"
        json_dir = parent_dir / "json"
        md_dir.mkdir(parents=True, exist_ok=True)
        json_dir.mkdir(parents=True, exist_ok=True)
        
        original_stem = doc_path.stem
        md_path = md_dir / f"{original_stem}.md"

        # Extract text
        print(f"[DEBUG] 1. Extract text từ {doc_path.name}...")
        md_text = extract_file(str(doc_path))
        with open(str(md_path), "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"[DEBUG]    Lưu: {md_path}")

        # Extract metadata
        print(f"[DEBUG] 2. Extract metadata...")
        result.metadata = self._extract_metadata_doc(
            md_text=md_text,
            file_path=str(doc_path),
            md_path=str(md_path),
        )
        doc_id = result.metadata.so_hieu or doc_path.stem
        if not doc_id:
            raise ValueError(f"Không tạo được document id cho {doc_path}")
        result.metadata.so_hieu = doc_id
        print(f"[DEBUG]    so_hieu={doc_id}, ten_van_ban={result.metadata.ten_van_ban}")

        # Build tree
        print(f"[DEBUG] 3. Build JSON tree...")
        tree = self.parser.build_json_tree(doc_id=doc_id, text=md_text)
        result.tree = tree
        result.md_text = md_text
        print(f"[DEBUG]    Tree có {len(tree)} root nodes")

        # Save JSON
        json_path = json_dir / f"{doc_id}.jsonl"
        data = {
            'metadata': result.metadata.model_dump(),
            'tree': tree,
        }
        with open(str(json_path), "w", encoding="utf-8") as f:
            line = json.dumps(data, ensure_ascii=False)
            f.write(line + "\n")
        print(f"[DEBUG]    Lưu: {json_path}")
        print(f"[DEBUG] ✓ Hoàn thành!")

        return result

    def process_batch(self, file_paths: list[str]) -> list[ProcessResult]:
        """Process multiple files with logging."""
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
