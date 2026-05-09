"""
Pydantic schemas cho Legal Agent (LangGraph).

Chứa các kiểu dữ liệu dùng chung giữa state, tools, và nodes:
- Intent: Loại câu hỏi của người dùng để phân nhánh.
- DocumentItem: DTO sạch để tách biệt ORM (DocumentMetadataDB) khỏi tầng Agent.
- ToolOutput: Output chuẩn trả về từ mọi tool.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

# pyrefly: ignore [missing-import]
from src.indexing.vector_store import ChromaQueryResult  # re-exported từ vector_store/schemas.py

class Intent(str, Enum):
    """Intent của câu hỏi — dùng để phân nhánh trong LangGraph."""
    CHITCHAT = "chitchat"           # Hỏi thăm, chào hỏi không liên quan pháp luật
    DOC_RETRIEVE = "doc_retrieve"   # Tra cứu, tải văn bản cụ thể
    LEGAL_QUERY = "legal_query"     # Trả lời trỏ điều khoản, văn bản cụ thể
    GENERAL = "general"             # Câu hỏi pháp lý chung chung
    DOC_RELATION = "doc_relation"   # Hỏi về quan hệ hiệu lực, thay thế, sửa đổi


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
        )

    def to_display(self) -> str:
        """Format để đưa vào prompt LLM."""
        lines = [f"**{self.ten_van_ban or self.so_hieu}** ({self.so_hieu})"]
        if self.loai:
            lines.append(f"- Loại: {self.loai}")
        if self.linh_vuc:
            lines.append(f"- Lĩnh vực: {self.linh_vuc}")
        if self.co_quan_ban_hanh:
            lines.append(f"- Cơ quan: {self.co_quan_ban_hanh}")
        if self.ngay_ban_hanh:
            lines.append(f"- Ngày ban hành: {self.ngay_ban_hanh}")
        if self.ngay_co_hieu_luc:
            lines.append(f"- Ngày có hiệu lực: {self.ngay_co_hieu_luc}")
        return "\n".join(lines)


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
