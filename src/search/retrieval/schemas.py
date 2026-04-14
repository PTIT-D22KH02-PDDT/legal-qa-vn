"""Schemas cho retrieval module."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field


class RetrieveQuestionRequest(BaseModel):
    """Yêu cầu retrieve với query là điều khoản hoặc câu hỏi pháp lý"""
    query: str = Field(..., description="Câu truy vấn (ví dụ: 'điều khoản về hợp đồng')")
    top_k: int = Field(5, ge=1, le=100, description="Số lượng kết quả trả về")
    filter_by_type: Optional[List[str]] = Field(
        None, 
        description="Lọc theo loại section (dieu, khoan, diem, etc)"
    )
    score_threshold: Optional[float] = Field(
        None,
        description="Ngưỡng score tối thiểu (0-1)"
    )


@dataclass
class RetrieveResult:
    """Kết quả một section được retrieve"""
    section_id: str              # VD: "phan_5.chuong_xxv.dieu_663.khoan_1"
    section_display: str         # VD: "Khoản 1 Điều 663 Chương XXV Phần 5"
    text: str                    # Nội dung
    distance: float              # Distance từ embedding model
    section_type: str            # VD: "khoan", "dieu"
    metadata: dict               # Metadata từ ChromaDB
    score_rerank: Optional[float] = None  # Score từ reranker (nếu có rerank)