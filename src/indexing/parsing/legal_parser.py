import json
import logging
import re
from typing import Any
from pathlib import Path
from .constants import (
    BOUNDARY_SECTION_PATTERNS,
    ROMAN_NUM_MAP,
    STOP_HEADING_TYPES,
    VIETNAMESE_NUM_MAP,
)
from tqdm import tqdm

logger = logging.getLogger(__name__)


REF_CANDIDATE_RE = re.compile(
    r"(?i)("
    # Cụm viện dẫn cấu trúc: khoản/điểm/mục/chương/phần + id
    r"\b(?:điều|khoản|điểm|mục|chương|phần)\s+[0-9a-zđivxlcdm]+(?:\.[0-9a-zđ]+)*\b"
    r"|"
    # Văn bản pháp luật được nêu tên
    r"\b(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|quyết\s+định|nghị\s+quyết|pháp\s+lệnh)\b"
    r"|"
    # Số hiệu văn bản
    r"\bsố\s+\d+\/\d{4}\/[0-9a-zđ\/\-]+"
    r"|"
    r"\b\d+\/\d{4}\/[0-9a-zđ\/\-]+\b"
    r"|"
    # Self-ref thật sự, không match chữ 'này' trơ trọi
    r"\b(?:điều|khoản|điểm|mục|chương|phần|luật|bộ\s+luật|nghị\s+định|thông\s+tư|quyết\s+định|văn\s+bản)\s+này\b"
    r"|"
    # Cụm căn cứ thường mở đầu viện dẫn
    r"\bcăn\s+cứ\s+(?:luật|bộ\s+luật|nghị\s+định|thông\s+tư|quyết\s+định|nghị\s+quyết)\b"
    r")"
)


class ParseLegal:
    """
    Parser văn bản pháp luật Việt Nam.

    Thay đổi chính ở bản này:
    - Regex không còn là cơ chế chính để trích reference.
    - Regex chỉ dùng để lọc nhanh chunk/câu có khả năng chứa viện dẫn.
    - LLM nhẹ được dùng để trích viện dẫn có cấu trúc.
    - Regex legacy vẫn được giữ làm fallback nếu LLM lỗi hoặc chưa inject llm_client.

    llm_client cần có method:
        generate(prompt: str, max_length: int = 800, temperature: float = 0.0) -> str

    Ví dụ:
        from src.remote_api_client import RemoteAPIClient

        client = RemoteAPIClient()
        parser = ParseLegal(llm_client=client, use_llm_refs=True)
    """

    def __init__(self, max_tokens: int = 1000, llm_client: Any | None = None, use_llm_refs: bool = False):
        self.max_tokens = max_tokens
        self.vietnamese_num_map = VIETNAMESE_NUM_MAP
        self.roman_num_map = ROMAN_NUM_MAP
        self.llm_client = llm_client
        self.use_llm_refs = use_llm_refs
        self._llm_ref_pbar = None
        self._llm_ref_calls = 0

    def normalize_id(self, raw_id, only_vietnamese=False):
        """
        Chuyển đổi ID từ dạng Việt sang số.
        VD: 'nhất' -> '1', 'hai' -> '2'

        Args:
            only_vietnamese: Nếu True, chỉ normalize từ Việt, bỏ qua La Mã.
        """
        raw_id_lower = raw_id.lower().strip()
        raw_id_lower = re.sub(r"\s+", " ", raw_id_lower)

        if raw_id_lower in self.vietnamese_num_map:
            return self.vietnamese_num_map[raw_id_lower]

        if not only_vietnamese and raw_id_lower in self.roman_num_map:
            return self.roman_num_map[raw_id_lower]

        return raw_id_lower

    def parse_heading(self, line):
        """
        Phân tích dòng và xác định loại heading: Phần, Chương, Mục, Điều, Khoản, Điểm.
        """
        if not line:
            return None

        roman_1_30 = (
            r"(?:xxx|xxix|xxviii|xxvii|xxvi|xxv|xxiv|xxiii|xxii|xxi|xx|xix|xviii|xvii|"
            r"xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)"
        )
        roman_1_20_short = (
            r"(?:xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)"
        )

        phan_viet = r"nhất|một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười(?:\s+\w+)?|hai\s+mươi"
        chuong_muc_pattern = f"(?:{roman_1_30}|\\d+)"
        dieu_khoan_diem_id = r"[0-9a-zđ]+(?:\.[0-9a-zđ]+)*"

        patterns = []

        for btype, pattern in BOUNDARY_SECTION_PATTERNS.items():
            patterns.append((btype, pattern))

        patterns.extend(
            [
                ("phan", rf"(?i)^phần\s+thứ\s+({phan_viet})(?:[\.\:\)]|$|\s|,)"),
                ("phan_num", rf"(?i)^phần\s+({roman_1_20_short}|\d+)(?:[\.\:\)]|$|\s|,)"),
                ("chuong", rf"(?i)^chương\s+({chuong_muc_pattern})(?:[\.\:\)]|$|\s|,)"),
                ("muc", rf"(?i)^mục\s+({chuong_muc_pattern})(?:[\.\:\)]|$|\s)"),
                ("dieu", rf"(?i)^điều\s+({dieu_khoan_diem_id})(?:[\.\:\)\;]|$|\s)"),
                ("khoan", rf"(?i)^khoản\s+({dieu_khoan_diem_id})(?:[\.\:\)\;]|$|\s)"),
                ("diem", rf"(?i)^điểm\s+({dieu_khoan_diem_id})(?:[\.\:\)\;]|$|\s)"),
                ("so_cap_3", r"^(\d+\.\d+\.\d+)[\\\.\)]?\s*(.*)$"),
                ("so_cap_2", r"^(\d+\.\d+)[\\\.\)]?\s*(.*)$"),
                ("so_cap_1", r"^(\d+)[\\\.\)]\s*(.*)$"),
                ("chu_thuong", r"^([a-zđ])[\\\.\)\,\;]\s*(.*)$"),
            ]
        )

        for p_type, pattern in patterns:
            match = re.match(pattern, line)
            if match:
                raw_id = match.group(1).lower().strip() if match.lastindex else ""
                normalized_type = "phan" if p_type == "phan_num" else p_type

                if normalized_type == "phu_luc":
                    normalized_id = raw_id if raw_id else "1"
                elif normalized_type == "phan":
                    normalized_id = self.normalize_id(raw_id, only_vietnamese=True)
                else:
                    normalized_id = raw_id.replace(".", "_") if "." in raw_id else raw_id

                return {
                    "type": normalized_type,
                    "id_raw": normalized_id,
                    "content": line,
                }

        return None

    def chunk_text_approx(self, text):
        """
        Chia nhỏ văn bản nhưng vẫn cố giữ trọn câu.
        Hàm này chủ yếu phục vụ chunk phần mở đầu.
        """
        sentences = text.split(". ")
        chunks = []
        current_chunk = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence.split())
            if current_len + sentence_len > self.max_tokens and current_chunk:
                chunks.append(". ".join(current_chunk) + ("." if not current_chunk[-1].endswith(".") else ""))
                current_chunk = [sentence]
                current_len = sentence_len
            else:
                current_chunk.append(sentence)
                current_len += sentence_len

        if current_chunk:
            chunks.append(". ".join(current_chunk) + ("." if not current_chunk[-1].endswith(".") else ""))

        return chunks

    def build_json_tree(self, doc_id: str, text: str):
        """
        Phân tích văn bản luật thành cây JSON:
        Mở đầu > Phần > Chương > Mục > Điều > Khoản > Điểm.
        """
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        tree = []

        if self.use_llm_refs and self.llm_client is not None:
            self._start_ref_progress(total=self.count_ref_candidates_in_text(text))

        parsed_lines = []
        for line in lines:
            parsed = self.parse_heading(line)
            if parsed:
                parsed_lines.append(("heading", parsed["type"], parsed["id_raw"], line))
            else:
                parsed_lines.append(("text", None, None, line))

        mo_dau_lines = []
        i = 0
        while i < len(parsed_lines) and parsed_lines[i][0] != "heading":
            mo_dau_lines.append(parsed_lines[i][3])
            i += 1

        if mo_dau_lines:
            mo_dau_text = ". ".join(mo_dau_lines)
            chunks = self.chunk_text_approx(mo_dau_text)
            for idx, chunk in enumerate(chunks, 1):
                tree.append(
                    {
                        "type_id": f"{doc_id}.modau_{idx}",
                        "parent_id": doc_id,
                        "type": "mo_dau",
                        "content": chunk,
                        "ref": self.extract_refs(chunk, {"luat_id": doc_id}),
                    }
                )

        while i < len(parsed_lines):
            ptype, pid, praw, pline = parsed_lines[i]

            if ptype == "heading" and pid == "phan":
                phan_id = f"{doc_id}.phan_{praw}"
                phan_tieu_de_parts = [pline]
                i += 1
                phan_con = []
                phan_content = []

                while i < len(parsed_lines) and parsed_lines[i][0] == "text":
                    phan_tieu_de_parts.append(parsed_lines[i][3])
                    i += 1

                phan_tieu_de = " : ".join(phan_tieu_de_parts)

                while i < len(parsed_lines):
                    dtype, did, draw, dline = parsed_lines[i]

                    if dtype == "heading" and did == "phan":
                        break

                    if dtype == "heading" and did == "chuong":
                        chuong_id = f"{phan_id}.chuong_{draw}"
                        chuong_node, i = self._extract_chuong(parsed_lines, i, doc_id, chuong_id, phan_id)
                        phan_con.append(chuong_node)

                    elif dtype == "heading" and did == "muc":
                        muc_id = f"{phan_id}.muc_{draw}"
                        muc_node, i = self._extract_muc(parsed_lines, i, doc_id, muc_id, phan_id, phan_id=phan_id)
                        phan_con.append(muc_node)

                    elif dtype == "heading" and did == "dieu":
                        context = {"luat_id": doc_id, "phan_id": phan_id, "dieu_id": f"{phan_id}.dieu_{draw}"}
                        dieu_node = self._extract_dieu(parsed_lines, i, context, parent_id=phan_id)
                        phan_con.append(dieu_node)
                        i = dieu_node["_end_idx"]

                    else:
                        if dtype == "text":
                            phan_content.append(dline)
                        i += 1

                tree.append(
                    {
                        "type_id": phan_id,
                        "parent_id": doc_id,
                        "type": "phan",
                        "title": phan_tieu_de,
                        "content": ". ".join(phan_content),
                        "ref": self.extract_refs(f"{phan_tieu_de}. {'. '.join(phan_content)}" if phan_tieu_de else ". ".join(phan_content), {"luat_id": doc_id, "phan_id": phan_id}),
                        "con": phan_con,
                    }
                )

            elif ptype == "heading" and pid == "chuong":
                chuong_id = f"{doc_id}.chuong_{praw}"
                chuong_node, i = self._extract_chuong(parsed_lines, i, doc_id, chuong_id, doc_id)
                tree.append(chuong_node)

            elif ptype == "heading" and pid == "dieu":
                context = {"luat_id": doc_id, "dieu_id": f"{doc_id}.dieu_{praw}"}
                dieu_node = self._extract_dieu(parsed_lines, i, context, parent_id=doc_id)
                tree.append(dieu_node)
                i = dieu_node["_end_idx"]

            elif ptype == "heading" and pid == "phu_luc":
                section_id = f"{doc_id}.{pid}_{praw}" if praw else f"{doc_id}.{pid}"
                i += 1
                section_content = []

                while i < len(parsed_lines):
                    ntype, _, _, nline = parsed_lines[i]
                    if ntype == "heading":
                        break
                    if ntype == "text":
                        section_content.append(nline)
                    i += 1

                content = ". ".join(section_content)
                tree.append(
                    {
                        "type_id": section_id,
                        "parent_id": doc_id,
                        "type": pid,
                        "title": pline,
                        "content": content,
                        "ref": self.extract_refs(f"{pline}. {content}" if pline else content, {"luat_id": doc_id}),
                    }
                )

            else:
                i += 1

        self._cleanup_end_idx(tree)
        self._add_parent_context_to_tree(tree)
        self._close_ref_progress()
        return tree

    def _extract_chuong(self, parsed_lines, start_idx: int, doc_id: str, chuong_id: str, parent_id: str):
        _, _, _, chuong_line = parsed_lines[start_idx]
        i = start_idx + 1
        chuong_tieu_de_parts = [chuong_line]
        chuong_con = []
        chuong_content = []

        while i < len(parsed_lines) and parsed_lines[i][0] == "text":
            chuong_tieu_de_parts.append(parsed_lines[i][3])
            i += 1

        chuong_tieu_de = " : ".join(chuong_tieu_de_parts)

        while i < len(parsed_lines):
            etype, eid, eraw, eline = parsed_lines[i]

            if etype == "heading" and eid in ["phan", "chuong"]:
                break

            if etype == "heading" and eid == "muc":
                muc_id = f"{chuong_id}.muc_{eraw}"
                phan_id = parent_id if ".phan_" in str(parent_id) else None
                muc_node, i = self._extract_muc(
                    parsed_lines,
                    i,
                    doc_id,
                    muc_id,
                    chuong_id,
                    phan_id=phan_id,
                    chuong_id=chuong_id,
                )
                chuong_con.append(muc_node)

            elif etype == "heading" and eid == "dieu":
                context = {"luat_id": doc_id, "chuong_id": chuong_id, "dieu_id": f"{chuong_id}.dieu_{eraw}"}
                if parent_id != doc_id:
                    context["phan_id"] = parent_id
                dieu_node = self._extract_dieu(parsed_lines, i, context, parent_id=chuong_id)
                chuong_con.append(dieu_node)
                i = dieu_node["_end_idx"]

            else:
                if etype == "text":
                    chuong_content.append(eline)
                i += 1

        content = ". ".join(chuong_content)
        context = {"luat_id": doc_id, "chuong_id": chuong_id}
        if parent_id != doc_id:
            context["phan_id"] = parent_id

        return (
            {
                "type_id": chuong_id,
                "parent_id": parent_id,
                "type": "chuong",
                "title": chuong_tieu_de,
                "content": content,
                "ref": self.extract_refs(f"{chuong_tieu_de}. {content}" if chuong_tieu_de else content, context),
                "con": chuong_con,
            },
            i,
        )

    def _extract_muc(
        self,
        parsed_lines,
        start_idx: int,
        doc_id: str,
        muc_id: str,
        parent_id: str,
        phan_id: str | None = None,
        chuong_id: str | None = None,
    ):
        _, _, _, muc_line = parsed_lines[start_idx]
        i = start_idx + 1
        muc_con = []
        muc_content = []

        while i < len(parsed_lines):
            ftype, fid, fraw, fline = parsed_lines[i]

            if ftype == "heading" and fid in ["phan", "chuong", "muc"]:
                break

            if ftype == "heading" and fid == "dieu":
                context = {"luat_id": doc_id, "muc_id": muc_id, "dieu_id": f"{muc_id}.dieu_{fraw}"}
                if phan_id:
                    context["phan_id"] = phan_id
                if chuong_id:
                    context["chuong_id"] = chuong_id

                dieu_node = self._extract_dieu(parsed_lines, i, context, parent_id=muc_id)
                muc_con.append(dieu_node)
                i = dieu_node["_end_idx"]

            else:
                if ftype == "text":
                    muc_content.append(fline)
                i += 1

        content = ". ".join(muc_content)
        context = {"luat_id": doc_id, "muc_id": muc_id}
        if phan_id:
            context["phan_id"] = phan_id
        if chuong_id:
            context["chuong_id"] = chuong_id

        return (
            {
                "type_id": muc_id,
                "parent_id": parent_id,
                "type": "muc",
                "title": muc_line,
                "content": content,
                "ref": self.extract_refs(f"{muc_line}. {content}" if muc_line else content, context),
                "con": muc_con,
            },
            i,
        )

    def _extract_dieu(self, parsed_lines, start_idx: int, context: dict, parent_id: str):
        """
        Extract Điều node từ parsed_lines, bắt đầu từ start_idx.
        Return node với _end_idx để biết vị trí kế tiếp.
        """
        dieu_id = context["dieu_id"]
        _, _, _, dieu_line = parsed_lines[start_idx]
        i = start_idx + 1
        dieu_content = []
        dieu_full_text = [dieu_line]
        dieu_con = []

        khoan_type = {"khoan", "so_cap_3", "so_cap_2", "so_cap_1"}
        diem_types = {"diem", "chu_thuong"}
        khoan_pattern = None
        diem_pattern = None
        current_khoan = None
        current_diem = None

        while i < len(parsed_lines):
            ptype, pid, praw, pline = parsed_lines[i]

            if ptype == "heading" and (pid in ["phan", "chuong", "muc", "dieu"] or pid in STOP_HEADING_TYPES):
                break

            if ptype == "text":
                if current_diem is not None:
                    current_diem["lines"].append(pline)
                elif current_khoan is not None:
                    current_khoan["lines"].append(pline)
                else:
                    dieu_content.append(pline)
                dieu_full_text.append(pline)
                i += 1
                continue

            if ptype == "heading" and pid not in ["phan", "chuong", "muc", "dieu"]:
                dieu_full_text.append(pline)
                is_khoan = pid in khoan_type
                is_diem = pid in diem_types

                if is_khoan:
                    if khoan_pattern is None:
                        khoan_pattern = pid

                    if pid == khoan_pattern:
                        if current_diem is not None:
                            self._finalize_current_diem(current_diem, current_khoan, dieu_con, context, dieu_line)
                            current_diem = None

                        if current_khoan is not None:
                            self._finalize_current_khoan(current_khoan, dieu_con, context)

                        current_khoan = {
                            "type": "khoan",
                            "type_id": f"{dieu_id}.khoan_{praw}",
                            "parent_id": dieu_id,
                            "lines": [pline],
                            "full_text": [pline],
                            "con": [],
                        }
                    else:
                        if current_diem is not None:
                            current_diem["lines"].append(pline)
                        elif current_khoan is not None:
                            current_khoan["lines"].append(pline)
                            current_khoan["full_text"].append(pline)

                elif is_diem:
                    if diem_pattern is None:
                        diem_pattern = pid

                    if pid == diem_pattern:
                        if current_diem is not None:
                            self._finalize_current_diem(current_diem, current_khoan, dieu_con, context, dieu_line)

                        diem_parent_id = current_khoan["type_id"] if current_khoan is not None else dieu_id
                        current_diem = {
                            "type": "diem",
                            "type_id": f"{diem_parent_id}.diem_{praw}",
                            "parent_id": diem_parent_id,
                            "lines": [pline],
                        }
                    else:
                        if current_diem is not None:
                            current_diem["lines"].append(pline)
                        elif current_khoan is not None:
                            current_khoan["full_text"].append(pline)
                            current_khoan["lines"].append(pline)

                else:
                    if current_diem is not None:
                        current_diem["lines"].append(pline)
                    elif current_khoan is not None:
                        current_khoan["full_text"].append(pline)
                        current_khoan["lines"].append(pline)

            i += 1

        if current_diem is not None:
            self._finalize_current_diem(current_diem, current_khoan, dieu_con, context)

        if current_khoan is not None:
            self._finalize_current_khoan(current_khoan, dieu_con, context)

        dieu_text = ". ".join(dieu_content)
        dieu_node = {
            "type": "dieu",
            "type_id": dieu_id,
            "title": dieu_line,
            "parent_id": parent_id,
            "content": dieu_text,
            "full_text": ". ".join(dieu_full_text),
            "ref": self.extract_refs(f"{dieu_line}. {dieu_text}" if dieu_line else dieu_text, context),
        }

        if dieu_con is not None:
            dieu_node["con"] = dieu_con

        dieu_node["_end_idx"] = i
        return dieu_node

    def _finalize_current_diem(self, current_diem: dict, current_khoan: dict | None, dieu_con: list, context: dict, dieu_parent_context: str | None = None):
        diem_text = ". ".join(current_diem["lines"])
        current_diem["content"] = diem_text

        diem_context = dict(context)
        diem_context["diem_id"] = current_diem["type_id"]

        if current_khoan is not None:
            current_khoan["full_text"].extend(current_diem["lines"])
            diem_context["khoan_id"] = current_khoan["type_id"]

        current_diem["ref"] = self.extract_refs(diem_text, diem_context)
        del current_diem["lines"]

        if current_khoan is not None:
            current_khoan["con"].append(current_diem)
        else:
            dieu_con.append(current_diem)

    def _finalize_current_khoan(self, current_khoan: dict, dieu_con: list, context: dict):
        khoan_text = ". ".join(current_khoan["lines"])
        current_khoan["content"] = khoan_text

        khoan_context = dict(context)
        khoan_context["khoan_id"] = current_khoan["type_id"]

        current_khoan["ref"] = self.extract_refs(khoan_text, khoan_context)
        current_khoan["full_text"] = ". ".join(current_khoan["full_text"])
        del current_khoan["lines"]

        if not current_khoan["con"]:
            del current_khoan["con"]

        dieu_con.append(current_khoan)

    def _cleanup_end_idx(self, nodes):
        for node in nodes:
            if node is None:
                continue
            node.pop("_end_idx", None)
            if "con" in node:
                self._cleanup_end_idx(node["con"])

    def _add_parent_context_to_tree(self, nodes, parent_node=None):
        """
        Recursively add parent_context to all child nodes.
        parent_context = parent's parent_context + title + content.
        Dùng để giữ ngữ cảnh khi embedding node con.
        """
        for node in nodes:
            if node is None:
                continue

            if parent_node:
                context_parts = []
                if parent_node.get("parent_context"):
                    context_parts.append(parent_node["parent_context"])
                if parent_node.get("title"):
                    context_parts.append(parent_node["title"])
                if parent_node.get("content"):
                    context_parts.append(parent_node["content"])

                node["parent_context"] = "\n".join(context_parts) if context_parts else None

            if "con" in node and node["con"]:
                self._add_parent_context_to_tree(node["con"], node)

    def _format_id(self, s: str) -> str | None:
        if not s or (isinstance(s, str) and not s.strip()):
            return None

        s = str(s).strip()

        vietnamese_map = {
            "à": "a", "á": "a", "ả": "a", "ã": "a", "ạ": "a",
            "ă": "a", "ắ": "a", "ằ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
            "â": "a", "ấ": "a", "ầ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
            "è": "e", "é": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
            "ê": "e", "ế": "e", "ề": "e", "ể": "e", "ễ": "e", "ệ": "e",
            "ì": "i", "í": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
            "ò": "o", "ó": "o", "ỏ": "o", "õ": "o", "ọ": "o",
            "ô": "o", "ố": "o", "ồ": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
            "ơ": "o", "ớ": "o", "ờ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
            "ù": "u", "ú": "u", "ủ": "u", "ũ": "u", "ụ": "u",
            "ư": "u", "ứ": "u", "ừ": "u", "ử": "u", "ữ": "u", "ự": "u",
            "ỳ": "y", "ý": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
            "Đ": "d", "đ": "d",
        }

        s_normalized = []
        for ch in s.lower():
            s_normalized.append(vietnamese_map.get(ch, ch))
        s = "".join(s_normalized)

        s = re.sub(r"[^a-z0-9\-]+", "_", s)
        s = s.strip("_-")
        return s if s else None

    # ------------------------------------------------------------------
    # Reference extraction - new LLM-first flow
    # ------------------------------------------------------------------

    def count_ref_candidates_in_text(self, text: str) -> int:
        """
        Ước lượng số câu/cụm sẽ gọi LLM để hiển thị progress bar.
        Regex ở đây chỉ dùng để sàng lọc candidate, không parse reference.
        """
        if not text:
            return 0

        candidates = re.split(r"(?<=[.!?;])\s+", text)
        return sum(
            1
            for candidate in candidates
            if candidate.strip() and self.has_ref_candidate(candidate)
        )

    def _start_ref_progress(self, total: int | None = None):
        if self._llm_ref_pbar is None:
            self._llm_ref_calls = 0
            self._llm_ref_pbar = tqdm(
                total=total,
                desc="LLM reference extraction",
                unit="chunk",
                dynamic_ncols=True,
            )

    def _update_ref_progress(self):
        self._llm_ref_calls += 1
        if self._llm_ref_pbar is not None:
            self._llm_ref_pbar.update(1)

    def _close_ref_progress(self):
        if self._llm_ref_pbar is not None:
            self._llm_ref_pbar.close()
            self._llm_ref_pbar = None

    def has_ref_candidate(self, text: str) -> bool:
        """
        Cheap filter để tránh gọi LLM cho mọi chunk.
        Regex ở đây chỉ xác định khả năng có viện dẫn, không parse reference.
        """
        if not text:
            return False
        return bool(REF_CANDIDATE_RE.search(text))

    def _split_sentences_for_ref_extraction(self, text: str) -> list[str]:
        """
        Tách chunk thành câu/cụm nhỏ có khả năng chứa viện dẫn.
        Điều này giảm token, giảm hallucination và tăng độ chính xác.
        """
        if not text:
            return []

        # Giữ dấu ; vì viện dẫn pháp luật hay nằm trong cụm phân tách bằng chấm phẩy.
        candidates = re.split(r"(?<=[.!?;])\s+", text)
        return [c.strip() for c in candidates if c.strip() and self.has_ref_candidate(c)]

    def _build_ref_extraction_prompt(self, text: str, context: dict | None = None) -> str:
        context = context or {}

        if not hasattr(self, "_ref_prompt_template") or self._ref_prompt_template is None:
            prompt_path = (
                Path(__file__).resolve().parents[3]
                / "configs"
                / "prompts"
                / "legal_ref_extraction.txt"
            )

            self._ref_prompt_template = prompt_path.read_text(encoding="utf-8")

        return self._ref_prompt_template.format(
            context_json=json.dumps(context, ensure_ascii=False),
            text=text or "",
        ).strip()

    def _safe_json_loads(self, raw: str) -> dict:
        """
        Parse LLM output into {"refs": [...]}.

        Supports messy LLM outputs:
        - {"refs": [...]}
        - [...]
        - "Kết quả trả về: [...]"
        - ```json ... ```
        - extra text before/after JSON
        """
        if not raw:
            return {"refs": []}

        raw = str(raw).strip()

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        raw = re.sub(
            r"(?i)^\s*(kết\s+quả\s+trả\s+về|output|json)\s*:\s*",
            "",
            raw,
        ).strip()

        def normalize(parsed):
            if isinstance(parsed, dict):
                refs = parsed.get("refs", [])
                return {"refs": refs if isinstance(refs, list) else []}

            if isinstance(parsed, list):
                return {"refs": parsed}

            return {"refs": []}

        try:
            return normalize(json.loads(raw))
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()

        for idx, ch in enumerate(raw):
            if ch not in "{[":
                continue

            try:
                parsed, _end = decoder.raw_decode(raw[idx:])
                return normalize(parsed)
            except json.JSONDecodeError:
                continue

        logger.warning("Cannot parse LLM reference JSON: %s", raw[:800])
        return {"refs": []}

    def _normalize_target_value(self, value: Any) -> str | None:
        if value is None:
            return None

        value = str(value).strip()
        value_lower = value.lower().strip()

        if not value_lower or value_lower in {
            "none",
            "null",
            "unknown",
            "không rõ",
            "khong ro",
            "this",
            "current",
            "nay",
            "này",
            "hien_tai",
            "hiện tại",
            "hien tai",
            "same",
            "self",
        }:
            return None

        # Target ids for điều/khoản/điểm/mục/chương/phần must be compact legal indexes.
        # Drop document ids or years accidentally placed into target_ids, e.g. "108_2020_tt-btc".
        if re.search(r"[_/\-]", value_lower):
            return None
        if re.search(r"\d{4}", value_lower):
            return None

        return self._format_id(value.replace(".", "_"))



    def _looks_like_doc_level_ref(self, raw_text: str | None) -> bool:
        """
        True nếu raw_text chỉ giống viện dẫn cấp văn bản, không có Điều/Khoản/Điểm thật.
        """
        if not raw_text:
            return False

        raw = str(raw_text).lower()

        has_doc = bool(
            re.search(
                r"\b(luật|bộ\s+luật|nghị\s+định|thông\s+tư|quyết\s+định|nghị\s+quyết|pháp\s+lệnh)\b",
                raw,
            )
        )
        has_specific_target = bool(
            re.search(r"\b(điều|khoản|điểm|mục|chương|phần)\s+[0-9a-zđivxlcdm]+", raw)
        )

        return has_doc and not has_specific_target

    def _is_valid_doc_id(self, doc_id: str) -> bool:
        """
        Check if doc_id looks like a real document ID, not just a section number.
        
        Valid: "108_2020_tt-btc", "45_2017_tt-btc", "bblds_2015", "luat_dau_gia_tai_san"
        Invalid: "4", "45", "108", "dieu_4"
        """
        if not doc_id:
            return False
        
        doc_id_lower = doc_id.lower()
        
        # Reject pure numbers (1-3 digits)
        if re.fullmatch(r"\d{1,3}", doc_id_lower):
            return False
        
        # Reject numbers with optional letter (e.g., "4a", "108b")
        if re.fullmatch(r"\d{1,3}[a-z]?", doc_id_lower):
            return False
        
        # Reject if starts with structure keywords (dieu_, khoan_, diem_, etc.)
        if re.match(r"^(dieu|khoan|diem|phan|chuong|muc)_", doc_id_lower):
            return False
        
        # Valid doc IDs should contain at least one separator (_, -, /) or multiple parts
        # e.g., "108_2020_tt_btc" or "bblds_2015" or "luat-dau-gia"
        if not re.search(r"[_\-/]|[a-z].*[0-9].*[a-z]", doc_id_lower):
            return False
        
        return True

    def _is_junk_ref_id(self, ref_id: str) -> bool:
        """
        Check if ref_id is malformed and should be rejected.
        
        Invalid patterns:
        - Starts with pure number: "4.dieu_4.khoan_3"
        - First part is not a valid doc ID
        """
        if not ref_id:
            return True
        
        parts = ref_id.split(".")
        if not parts:
            return True
        
        first_part = parts[0]
        
        # First part must be a valid doc ID
        if not self._is_valid_doc_id(first_part):
            return True
        
        return False

    def _normalize_llm_ref(self, item: dict, chunk_text: str, context: dict | None = None) -> dict | None:
        context = context or {}

        raw_text = item.get("raw_text")
        ref_doc_name = item.get("ref_doc_name")
        ref_doc_id = item.get("ref_doc_id")
        is_self_ref = bool(item.get("is_self_ref"))

        target_type = str(item.get("target_type") or "").strip().lower()

        # Normalize document id.
        if ref_doc_id:
            ref_doc_id = self._format_id(ref_doc_id)

        # If no ref_doc_id from LLM, try to get from ref_doc_name
        if not ref_doc_id and ref_doc_name:
            ref_doc_id = self._format_id(ref_doc_name)

        # Fallback to context.luat_id only if LLM marks it as self-ref
        if not ref_doc_id and is_self_ref:
            ref_doc_id = context.get("luat_id")

        if not ref_doc_id:
            return None

        target_ids = item.get("target_ids") or {}
        if not isinstance(target_ids, dict):
            target_ids = {}

        phan = self._normalize_target_value(target_ids.get("phan"))
        chuong = self._normalize_target_value(target_ids.get("chuong"))
        muc = self._normalize_target_value(target_ids.get("muc"))
        dieu = self._normalize_target_value(target_ids.get("dieu"))
        khoan = self._normalize_target_value(target_ids.get("khoan"))
        diem = self._normalize_target_value(target_ids.get("diem"))


        # Nếu raw_text chỉ là viện dẫn cấp văn bản như "Thông tư số 45/2017/TT-BTC",
        # không cho phép sinh dieu/khoan/diem từ số hiệu.
        if self._looks_like_doc_level_ref(raw_text):
            phan = None
            chuong = None
            muc = None
            dieu = None
            khoan = None
            diem = None

        parts = [ref_doc_id]

        if phan:
            parts.append(f"phan_{phan}")
        if chuong:
            parts.append(f"chuong_{chuong}")
        if muc:
            parts.append(f"muc_{muc}")
        if dieu:
            parts.append(f"dieu_{dieu}")
        if khoan:
            parts.append(f"khoan_{khoan}")
        if diem:
            parts.append(f"diem_{diem}")

        ref_id = ".".join([p for p in parts if p])

        # Basic sanity check - only reject if empty
        if not ref_id:
            return None

        if "none" in ref_id.lower():
            return None

        if not re.match(r"^[a-z0-9_\.\-]+$", ref_id.lower()):
            return None

        if not self._is_valid_doc_id(ref_doc_id):
            return None

        if self._is_junk_ref_id(ref_id):
            return None

        confidence = item.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0

        return {
            "ref_id": ref_id,
            "ref_doc_name": ref_doc_name,
            "ref_doc_id": ref_doc_id,
            "raw_text": raw_text,
            "target_type": item.get("target_type", "unknown"),
            "target_ids": {
                "phan": phan,
                "chuong": chuong,
                "muc": muc,
                "dieu": dieu,
                "khoan": khoan,
                "diem": diem,
            },
            "is_self_ref": is_self_ref,
            "confidence": confidence,
        }

    def _extract_refs_structured_one_chunk(self, text: str, context: dict | None = None) -> list[dict]:
        """
        Extract references from one candidate chunk.

        Important:
        - Reference extraction is LLM-only.
        - Regex is used only for candidate filtering and output validation/normalization.
        - No regex legacy fallback is used to generate references.
        """
        if not text or not self.has_ref_candidate(text):
            return []

        if not self.use_llm_refs or self.llm_client is None:
            logger.warning(
                "LLM reference extraction is required, but use_llm_refs=False or llm_client is None. "
                "Returning no references."
            )
            return []

        prompt = self._build_ref_extraction_prompt(text, context)

        try:
            raw = self.llm_client.generate(
                prompt=prompt,
                max_length=700,
                temperature=0.3,
            )
            self._update_ref_progress()
        except Exception as exc:
            self._update_ref_progress()
            raise RuntimeError(f"LLM reference extraction failed: {exc}") from exc

        data = self._safe_json_loads(raw)
        refs = []

        for item in data.get("refs", []):
            if not isinstance(item, dict):
                continue

            normalized = self._normalize_llm_ref(item, text, context)
            if not normalized:
                continue

            if normalized["confidence"] < 0.55:
                continue

            refs.append(normalized)

        return refs

    def extract_refs_structured(self, text: str, context: dict | None = None) -> list[dict]:
        """
        API mới: trả reference có cấu trúc.

        Important:
        - Reference extraction is LLM-only.
        - Regex chỉ dùng để lọc candidate trước khi gọi LLM.
        - Không cắt window quanh anchor nữa, vì window dễ làm mất context văn bản được viện dẫn.
        - Mỗi node chỉ gọi LLM tối đa 1 lần.
        """
        if not text or not self.has_ref_candidate(text):
            return []

        if not self.use_llm_refs or self.llm_client is None:
            logger.warning(
                "LLM reference extraction is required, but use_llm_refs=False or llm_client is None. "
                "Returning no references."
            )
            return []

        context = context or {}

        candidates = self._split_sentences_for_ref_extraction(text)
        if not candidates:
            return []

        merged_text = "\n".join(candidates)

        # Không gửi phụ lục/bảng quá dài vào LLM, nhưng vẫn giữ context rộng hơn window 200 ký tự.
        if len(merged_text) > 3000:
            merged_text = merged_text[:3000]

        refs = self._extract_refs_structured_one_chunk(merged_text, context)

        results = []
        seen = set()

        for ref in refs:
            ref_id = ref.get("ref_id")
            if ref_id and ref_id not in seen:
                seen.add(ref_id)
                results.append(ref)

        return results

    def extract_refs(self, text: str, context: dict | None = None) -> list[str]:
        """
        API tương thích cũ: trả list[str].
        build_json_tree hiện vẫn gọi hàm này nên không phá pipeline hiện tại.
        """
        if self.use_llm_refs:
            refs = self.extract_refs_structured(text, context)
            return [ref["ref_id"] for ref in refs if ref.get("ref_id")]
        else:
            return self.extract_refs_regex_legacy(text, context)


    def _parse_list_items(self, prefix: str, search_text: str) -> list[str]:
        """
        Nhặt danh sách ID từ cụm như 'các khoản 1, 2 và 3'.
        """
        items = []
        id_regex = r"(?:[0-9]{1,3}[a-zđ]?|[a-zđ]{1,2})(?:\.[0-9]{1,3})*"
        id_with_boundary = rf"(?:{id_regex})(?=\s|,|;|\)|$)"
        pattern = (
            rf"(?i)(?:các\s+)?\b{prefix}\b\s+"
            rf"({id_with_boundary}(?:\s*,\s*{id_with_boundary})*(?:\s+và\s+{id_with_boundary})?)"
        )

        for m in re.finditer(pattern, search_text):
            raw_str = m.group(1)
            parts = re.split(r"\s*,\s*|\s+và\s+", raw_str)
            for p in parts:
                p = p.strip()
                if p:
                    items.append(p)

        return items

    def _build_luat_position_map(self, text: str, fallback_luat_id: str | None) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []

        self_ref_luat = re.compile(
            r"(?i)\b(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|quyết\s+định|pháp\s+lệnh)\s+này\b"
        )
        self_ref_spans = {m.span() for m in re.finditer(self_ref_luat, text)}

        def _in_self_ref(start: int) -> bool:
            return any(s <= start < e for s, e in self_ref_spans)

        doc_num_pattern = (
            r"(?i)(?:lệnh|luật|bộ\s+luật|nghị\s+quyết|nghị\s+định"
            r"|thông\s+tư|quyết\s+định)\s+.{0,60}?(?:số\s+)?([0-9]+/[0-9a-zđ/\-]+)"
        )

        seen_positions: set[int] = set()
        pos_scan = 0
        while pos_scan < len(text):
            m = re.search(doc_num_pattern, text[pos_scan:])
            if not m:
                break
            abs_start = pos_scan + m.start()
            if _in_self_ref(abs_start):
                pos_scan = abs_start + 1
                continue
            if abs_start not in seen_positions:
                luat_id = self._format_id(m.group(1))
                if luat_id:
                    entries.append((abs_start, luat_id))
                seen_positions.add(abs_start)
            pos_scan = abs_start + len(m.group())

        nam_pattern = (
            r"(?i)(bộ\s+luật|luật|nghị\s+định|thông\s+tư|nghị\s+quyết|hiến\s+pháp)\s+"
            r"([A-ZĐÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆa-zđáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệ\s]{2,70}?)"
            r"(?:\s+năm\s+(\d{4}))?"
            r"(?=\s*[,.;]|\s+của|\s+được|\s+có|\s+về|$)"
        )
        for m in re.finditer(nam_pattern, text):
            if _in_self_ref(m.start()):
                continue
            full_name = f"{m.group(1)} {m.group(2)} {m.group(3) or ''}".strip()
            luat_id = self._format_id(full_name)
            already = any(abs(pos - m.start()) < 10 for pos, _ in entries)
            if luat_id and not already:
                entries.append((m.start(), luat_id))

        entries.sort(key=lambda x: x[0])

        if not entries and fallback_luat_id:
            entries.append((0, fallback_luat_id))

        return entries

    def _assign_luat_id(self, ref_pos: int, luat_map: list[tuple[int, str]], text: str = "") -> str | None:
        if not luat_map:
            return None

        window = 120
        snippet = text[ref_pos : ref_pos + window] if text else ""
        anchor_pattern = r"(?i)\b(?:của|theo|trong|tại)\s+(?:bộ\s+)?(?:luật|nghị\s+định|thông\s+tư|quyết\s+định)"
        anchor_match = re.search(anchor_pattern, snippet)
        if anchor_match:
            anchor_abs = ref_pos + anchor_match.start()
            forward_candidates = [(pos, lid) for pos, lid in luat_map if pos >= anchor_abs]
            if forward_candidates:
                return min(forward_candidates, key=lambda x: x[0])[1]

        return min(luat_map, key=lambda x: abs(x[0] - ref_pos))[1]

    def resolve_self_refs(self, text: str, context: dict) -> list[str]:
        if not text:
            return []

        refs = []
        self_ref_patterns = [
            (r"(?i)(?:(\w+)\s+)?\b(điểm\s+này)\b", "diem_id"),
            (r"(?i)(?:(\w+)\s+)?\b(khoản\s+này)\b", "khoan_id"),
            (r"(?i)(?:(\w+)\s+)?\b(điều\s+này)\b", "dieu_id"),
            (r"(?i)(?:(\w+)\s+)?\b(mục\s+này)\b", "muc_id"),
            (r"(?i)(?:(\w+)\s+)?\b(chương\s+này)\b", "chuong_id"),
            (r"(?i)(?:(\w+)\s+)?\b(phần\s+này)\b", "phan_id"),
            (
                r"(?i)(?:(\w+)\s+)?\b(bộ\s+luật\s+này|luật\s+này|nghị\s+định\s+này"
                r"|thông\s+tư\s+này|quyết\s+định\s+này|pháp\s+lệnh\s+này)\b",
                "luat_id",
            ),
        ]

        excluded_prefixes = {
            "diem_id": {"thời", "địa", "đặc", "ưu", "nhược", "quan", "khuyết", "trọng", "nhiệm", "tiêu", "tâm", "nhận", "giao"},
            "khoan_id": {"điều", "tài"},
            "muc_id": {"danh", "hạng", "thư", "chuyên", "tiết"},
            "phan_id": {"thành", "cổ", "một", "đóng"},
            "dieu_id": set(),
            "chuong_id": set(),
            "luat_id": set(),
        }

        for pattern, context_key in self_ref_patterns:
            for match in re.finditer(pattern, text):
                if match.group(1):
                    prev_word = match.group(1).lower()
                    if prev_word in excluded_prefixes.get(context_key, set()):
                        continue
                resolved_id = context.get(context_key)
                if resolved_id and resolved_id not in refs:
                    refs.append(resolved_id)

        return refs

    def extract_refs_regex_legacy(self, text: str, context: dict | None = None) -> list[str]:
        """
        Fallback regex cũ. Không dùng làm primary nữa.
        """
        if not text:
            return []

        context = context or {}
        fallback_luat_id = context.get("luat_id")
        if not fallback_luat_id:
            for key in ["diem_id", "khoan_id", "dieu_id", "muc_id", "chuong_id", "phan_id"]:
                full_id = context.get(key)
                if full_id and "." in full_id:
                    fallback_luat_id = full_id.split(".")[0]
                    break

        current_dieu_id = context.get("dieu_id")
        current_khoan_id = context.get("khoan_id")
        luat_map = self._build_luat_position_map(text, fallback_luat_id)
        refs_with_pos: list[tuple[str, int]] = []

        for m in re.finditer(r"(?i)từ\s+(?:các\s+)?điều\s+(\d+)\s+đến\s+(?:điều\s+)?(\d+)", text):
            try:
                s, e = int(m.group(1)), int(m.group(2))
                if s <= e < s + 500:
                    for idx in range(s, e + 1):
                        refs_with_pos.append((f"dieu_{idx}", m.start()))
            except ValueError:
                pass

        for m in re.finditer(
            r"(?i)từ\s+(?:các\s+)?khoản\s+(\d+)\s+đến\s+(?:khoản\s+)?(\d+)\s+điều\s+(\d+[a-zđ]?)",
            text,
        ):
            try:
                s, e = int(m.group(1)), int(m.group(2))
                dieu_raw = m.group(3).lower()
                if s <= e < s + 100:
                    for idx in range(s, e + 1):
                        refs_with_pos.append((f"dieu_{dieu_raw}.khoan_{idx}", m.start()))
            except ValueError:
                pass

        for m in re.finditer(r"(?i)chương\s+([ivxlcdm]+|\d+)", text):
            refs_with_pos.append((f"chuong_{m.group(1).lower()}", m.start()))

        for m in re.finditer(r"(?i)mục\s+([a-zđ0-9\.]+)\s+(?:của\s+)?chương\s+([ivxlcdm]+|\d+)", text):
            refs_with_pos.append((f"chuong_{m.group(2).lower()}.muc_{m.group(1).lower()}", m.start()))

        self_ref_luat_near = re.compile(
            r"(?i)^\s*(?:của\s+)?(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư)\s+này\b"
        )

        dieu_pattern = r"(?i)điều\s+(\d+[a-zđ]?|này)"
        dieu_matches = [(m.group(1), m.start(), m.end()) for m in re.finditer(dieu_pattern, text)]
        prev_dieu_end = 0

        for dieu_value, dieu_start, dieu_end in dieu_matches:
            after_snippet = text[dieu_end : dieu_end + 60]
            is_self_luat = bool(self_ref_luat_near.match(after_snippet))

            if dieu_value.lower() == "này":
                if not current_dieu_id:
                    prev_dieu_end = dieu_end
                    continue
                dieu_ref_id = current_dieu_id
            else:
                dieu_ref_id = f"dieu_{dieu_value.lower()}"

            search_text = text[max(prev_dieu_end, dieu_start - 300) : dieu_start]
            recent_khoans = self._parse_list_items("khoản", search_text)
            recent_diems = self._parse_list_items("điểm", search_text)
            effective_pos = -2 if is_self_luat else dieu_start

            if recent_khoans and recent_diems:
                for k in recent_khoans:
                    for d in recent_diems:
                        refs_with_pos.append(
                            (f"{dieu_ref_id}.khoan_{k.replace('.', '_')}.diem_{d.replace('.', '_')}", effective_pos)
                        )
            elif recent_khoans:
                for k in recent_khoans:
                    refs_with_pos.append((f"{dieu_ref_id}.khoan_{k.replace('.', '_')}", effective_pos))
            elif recent_diems:
                for d in recent_diems:
                    refs_with_pos.append((f"{dieu_ref_id}.diem_{d.replace('.', '_')}", effective_pos))
            else:
                refs_with_pos.append((dieu_ref_id, effective_pos))

            prev_dieu_end = dieu_end

        if not dieu_matches and context:
            all_khoans = self._parse_list_items("khoản", text)
            all_diems = self._parse_list_items("điểm", text)

            has_khoan_nay = bool(re.search(r"(?i)khoản\s+này", text))
            has_diem_nay = bool(re.search(r"(?i)điểm\s+này", text))

            base_khoan = current_khoan_id if has_khoan_nay else None
            base_dieu = current_dieu_id

            if all_diems and base_khoan:
                for d in all_diems:
                    refs_with_pos.append((f"{base_khoan}.diem_{d}", -1))
            elif all_diems and base_dieu:
                for d in all_diems:
                    refs_with_pos.append((f"{base_dieu}.diem_{d}", -1))
            elif all_khoans and base_dieu:
                for k in all_khoans:
                    refs_with_pos.append((f"{base_dieu}.khoan_{k}", -1))
            elif has_khoan_nay and base_khoan:
                refs_with_pos.append((base_khoan, -1))
            elif has_diem_nay and base_dieu:
                diem_id = context.get("diem_id")
                if diem_id:
                    refs_with_pos.append((diem_id, -1))

        if context:
            high_level_self_refs = [
                (r"(?i)(?:(\w+)\s+)?\b(mục\s+này)\b", "muc_id"),
                (r"(?i)(?:(\w+)\s+)?\b(chương\s+này)\b", "chuong_id"),
                (r"(?i)(?:(\w+)\s+)?\b(phần\s+này)\b", "phan_id"),
                (
                    r"(?i)(?:(\w+)\s+)?\b(bộ\s+luật\s+này|luật\s+này|nghị\s+định\s+này"
                    r"|thông\s+tư\s+này|quyết\s+định\s+này|pháp\s+lệnh\s+này)\b",
                    "luat_id",
                ),
            ]
            excluded_prefixes = {
                "muc_id": {"danh", "hạng", "thư", "chuyên", "tiết"},
                "phan_id": {"thành", "cổ", "một", "đóng"},
                "chuong_id": set(),
                "luat_id": set(),
            }
            preceded_by_dieu = re.compile(r"(?i)điều\s+\d+[a-zđ]?\s*")

            for pattern, ctx_key in high_level_self_refs:
                for match in re.finditer(pattern, text):
                    if match.group(1) and match.group(1).lower() in excluded_prefixes.get(ctx_key, set()):
                        continue

                    if ctx_key == "luat_id":
                        before_snippet = text[max(0, match.start() - 80) : match.start()]
                        if preceded_by_dieu.search(before_snippet):
                            continue

                    resolved = context.get(ctx_key)
                    if not resolved:
                        continue

                    full_ref = (
                        f"{fallback_luat_id}.{resolved}"
                        if fallback_luat_id and not resolved.startswith(fallback_luat_id)
                        else resolved
                    )
                    if (full_ref, -1) not in refs_with_pos:
                        refs_with_pos.append((full_ref, -1))

        unique_refs = []

        for ref_str, pos in refs_with_pos:
            if not ref_str:
                continue

            if pos == -1:
                full_ref = ref_str
            elif pos == -2:
                full_ref = f"{fallback_luat_id}.{ref_str}" if fallback_luat_id and not ref_str.startswith(fallback_luat_id) else ref_str
            else:
                luat_id = self._assign_luat_id(pos, luat_map, text)
                full_ref = f"{luat_id}.{ref_str}" if luat_id and not ref_str.startswith(luat_id) else ref_str

            if full_ref and full_ref not in unique_refs:
                unique_refs.append(full_ref)

        validated_refs = []
        for ref in unique_refs:
            if "none" in ref.lower():
                continue
            if not re.match(r"^[a-z0-9_\.\-]+$", ref.lower()):
                continue
            validated_refs.append(ref)

        return validated_refs
