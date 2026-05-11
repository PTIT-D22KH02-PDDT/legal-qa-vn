"""
Pydantic schemas cho Legal Agent (LangGraph).

Chứa các kiểu dữ liệu dùng chung giữa state, tools, và nodes:
- Intent: Loại câu hỏi của người dùng để phân nhánh.
- DocumentItem: DTO sạch để tách biệt ORM (DocumentMetadataDB) khỏi tầng Agent.
- ToolOutput: Output chuẩn trả về từ mọi tool.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# pyrefly: ignore [missing-import]
from src.indexing.vector_store import ChromaQueryResult  # re-exported từ vector_store/schemas.py

class Intent(str, Enum):
    """Intent của câu hỏi — dùng để phân nhánh trong LangGraph."""
    CHITCHAT = "chitchat"           # Hỏi thăm, chào hỏi không liên quan pháp luật hoặc câu hỏi không rõ ý
    # DOC_RETRIEVE = "doc_retrieve"   # Tra cứu, tải văn bản cụ thể, trả về chi tiết câu hỏi thuộc văn bản hoặc điều khoản cụ thể
    LEGAL_QUERY = "legal_query"     # Trả lời câu hỏi mà trong đó có đề cập đến điều khoản luật cụ thể rồi, nhiệm vụ là tìm kiếm nó chính xác theo metadata rồi lấy ra để đưa cho AI trả lời
    GENERAL = "general"             # Câu hỏi pháp lý chung chung, tìm kiếm các thông tin liên quan trong csdl để trả lời cho câu hỏi đó.
    DOC_RELATION = "doc_relation"   # Trả lời các câu hỏi liên quan đến các văn bản luật, như hiệu lực, trạng thái, hay các quan hệ thay thế, sửa đổi,.....


class SubQuestion(BaseModel):
    """Đại diện cho một câu hỏi con sau khi phân rã."""
    query: str = Field(description="Nội dung câu hỏi con đã được làm rõ ngữ nghĩa")
    intent: Intent = Field(description="Nhãn intent của câu hỏi con này")


class AnalyzerOutput(BaseModel):
    """Kết quả đầu ra của LLM sau bước Analyze."""
    sub_questions: List[SubQuestion] = Field(description="Danh sách các câu hỏi con sau khi phân rã")

class LegalCitation(BaseModel):
    """Thông tin trích xuất từ câu hỏi để tìm kiếm chính xác."""
    so_hieu: Optional[str] = Field(None, description="Số hiệu văn bản (vd: 45/2019/QH14)")
    ten_van_ban: Optional[str] = Field(None, description="Tên văn bản (vd: Luật Đất đai, Bộ luật Dân sự)")
    phan: Optional[int] = Field(None, description="Phần số mấy")
    chuong: Optional[int] = Field(None, description="Chương số mấy")
    muc: Optional[int] = Field(None, description="Mục số mấy")
    dieu: Optional[int] = Field(None, description="Điều số mấy")
    khoan: Optional[int] = Field(None, description="Khoản số mấy")
    diem: Optional[str] = Field(None, description="Điểm (chữ cái a, b, c...)")

class DocumentItem(BaseModel):
    """
    DTO đại diện một văn bản pháp luật từ SQLite.

    Lý do cần class này (thay vì dùng DocumentMetadataDB trực tiếp):
    - ORM object gắn với DB session → DetachedInstanceError khi session đóng.
    - ORM object không serialize được → không lưu vào LangGraph State.
    - Tách biệt tầng Agent khỏi tầng DB.
    """
    so_hieu: str = Field(..., description="Số hiệu văn bản")
    ten_van_ban: Optional[str] = Field(default=None, description="Tên văn bản")
    loai: Optional[str] = Field(default=None, description="Loại (Luật, Nghị định, ...)")
    linh_vuc: Optional[str] = Field(default=None, description="Lĩnh vực pháp lý. Ví dụ: 'Dân sự', 'Hình sự'")
    co_quan_ban_hanh: Optional[str] = Field(default=None, description="Cơ quan ban hành")
    ngay_ban_hanh: Optional[str] = Field(default=None, description="Ngày ban hành")
    ngay_co_hieu_luc: Optional[str] = Field(default=None, description="Ngày có hiệu lực")
    so_dieu: int = Field(default=0, description="Tổng số điều")
    trang_thai: Optional[int] = Field(default=None, description="1: Còn hiệu lực, 0: Hết hiệu lực")

    @classmethod
    def from_orm_row(cls, row: object) -> "DocumentItem":
        """Chuyển đổi từ DocumentMetadataDB ORM object sang DTO."""
        return cls(
            so_hieu=row.so_hieu or "",
            ten_van_ban=row.ten_van_ban,
            loai=row.loai,
            linh_vuc=getattr(row, "linh_vuc", None),
            co_quan_ban_hanh=row.co_quan_ban_hanh,
            ngay_ban_hanh=str(row.ngay_ban_hanh) if row.ngay_ban_hanh else None,
            ngay_co_hieu_luc=str(row.ngay_co_hieu_luc) if row.ngay_co_hieu_luc else None,
            so_dieu=row.so_dieu or 0,
            trang_thai=getattr(row, 'trang_thai', None),
        )

    def to_display(self) -> str:
        """Format thành chuỗi để đưa vào LLM Context."""
        status = "Không rõ"
        if self.trang_thai == 1:
            status = "Còn hiệu lực"
        elif self.trang_thai == 0:
            status = "Hết hiệu lực"

        parts = [
            f"Văn bản: {self.ten_van_ban or 'Không rõ tên'} (Số hiệu: {self.so_hieu})",
            f"Loại: {self.loai or 'Không rõ'} | Lĩnh vực: {self.linh_vuc or 'Không rõ'}",
            f"Cơ quan ban hành: {self.co_quan_ban_hanh or 'Không rõ'}",
            f"Ngày ban hành: {self.ngay_ban_hanh or 'Chưa rõ'} | Hiệu lực: {self.ngay_co_hieu_luc or 'Chưa rõ'}",
            f"Trạng thái: {status}",
            f"Số Điều: {self.so_dieu if self.so_dieu else 'Không rõ'}"
        ]
        return "\n".join(parts)


class RefScore(BaseModel):
    """Kết quả chấm điểm của một chunk tham chiếu do LLM đánh giá."""
    chunk_id: str = Field(description="ID của chunk tham chiếu")
    reasoning: str = Field(description="Giải thích ngắn lý do chấm điểm")
    score: float = Field(description="Điểm số từ 0.0 đến 10.0")


class RefEvaluationResult(BaseModel):
    """Tập hợp kết quả chấm điểm của nhiều chunk tham chiếu."""
    evaluations: List[RefScore] = Field(default_factory=list)

    @classmethod
    def from_llm_response(cls, raw_response: str, valid_chunk_ids: List[str]) -> "RefEvaluationResult":
        """Parse JSON từ LLM response, có fallback Regex chống LLM bọc markdown."""
        clean = raw_response.strip()
        match = re.search(r"```(?:json)?(.*?)```", clean, re.DOTALL)
        if match:
            clean = match.group(1).strip()

        json_dict = json.loads(clean)
        result = cls.model_validate(json_dict)

        # Chỉ giữ lại các đánh giá có chunk_id hợp lệ
        result.evaluations = [
            e for e in result.evaluations if e.chunk_id in valid_chunk_ids
        ]
        return result



class ChunkRelevance(BaseModel):
    """Kết quả đánh giá Yes/No cho một chunk."""
    chunk_id: str = Field(description="ID của chunk được đánh giá")
    relevant: bool = Field(description="True nếu chunk trực tiếp liên quan đến câu hỏi, False nếu không")
    reason: str = Field(description="Lý do ngắn gọn (1 câu) cho quyết định này")


class ChunkEvaluationResult(BaseModel):
    """Tập hợp kết quả đánh giá Yes/No cho danh sách chunks."""
    evaluations: List[ChunkRelevance] = Field(default_factory=list)

    @classmethod
    def from_llm_response(cls, raw_response: str, valid_chunk_ids: List[str]) -> "ChunkEvaluationResult":
        """Parse JSON từ LLM response, có fallback Regex chống LLM bọc markdown."""
        clean = raw_response.strip()
        match = re.search(r"```(?:json)?(.*?)```", clean, re.DOTALL)
        if match:
            clean = match.group(1).strip()

        json_dict = json.loads(clean)
        result = cls.model_validate(json_dict)

        # Chỉ giữ lại các đánh giá có chunk_id hợp lệ
        result.evaluations = [
            e for e in result.evaluations if e.chunk_id in valid_chunk_ids
        ]
        return result


class ToolOutput(BaseModel):

    """
    Output chuẩn trả về từ mọi tool.

    - `chunks`: List[ChromaQueryResult] — kết quả chunk từ ChromaDB.
    - `documents`: List[DocumentItem] — kết quả văn bản từ SQLite.
    - `display_text`: Context đã format để đưa thẳng vào prompt LLM.
    - `success`: Tool chạy thành công không.
    - `error`: Thông báo lỗi nếu thất bại.
    """
    tool_name: str = Field(..., description="Tên tool")
    success: bool = Field(default=True)
    chunks: List[ChromaQueryResult] = Field(
        default_factory=list,
        description="Kết quả chunk từ ChromaDB (ChromaQueryResult)"
    )
    documents: List[DocumentItem] = Field(
        default_factory=list,
        description="Kết quả văn bản từ SQLite (DocumentItem DTO)"
    )
    display_text: str = Field(default="", description="Context đã format để đưa vào LLM")
    error: Optional[str] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True
