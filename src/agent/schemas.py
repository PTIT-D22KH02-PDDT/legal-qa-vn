"""
Pydantic schemas cho LangChain Agent
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class Intent(str, Enum):
    """Intent của câu hỏi"""
    LOOKUP = "lookup"                   # Tìm kiếm thông tin
    COMPARE = "compare"                 # So sánh
    EXPLAIN = "explain"                 # Giải thích
    VERIFY = "verify"                   # Xác minh
    CALCULATE = "calculate"             # Tính toán
    DEFINE = "define"                   # Định nghĩa


class Grade(str, Enum):
    """Kết quả chấm chất lượng retrieval"""
    SUFFICIENT = "sufficient"      # Ngữ cảnh đủ để trả lời
    INSUFFICIENT = "insufficient"  # Thiếu thông tin, cần rewrite/retry
    OFF_TOPIC = "off_topic"        # Lạc đề, cần dừng hoặc trả lời "không biết"


class ArticleBlock(BaseModel):
    """Một cụm/block thực thể article độc lập để truy xuất."""
    dieu: Optional[int] = Field(default=None, description="Số điều (nếu có)")
    khoan: Optional[int] = Field(default=None, description="Số khoản (nếu có)")
    diem: Optional[str] = Field(default=None, description="Tên điểm (nếu có): a, b, c, ...")
    chuong: Optional[int] = Field(default=None, description="Số chương (nếu có)")
    document_name: Optional[str] = Field(default=None, description="Tên tài liệu pháp luật")

    # LLM hay trả "null" / "None" / "" thay vì JSON null thật.
    # Các validator dưới ép về None để không crash kiểu.
    @field_validator("dieu", "khoan", "chuong", mode="before")
    @classmethod
    def _coerce_nullable_int(cls, v):
        if v in (None, "", "null", "None", "NULL"):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @field_validator("diem", "document_name", mode="before")
    @classmethod
    def _coerce_nullable_str(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() == "null":
            return None
        return s


class QueryAnalysisResult(BaseModel):
    """
    Kết quả phân tích câu hỏi (phiên bản gọn).

    2 tín hiệu cốt lõi dùng để định tuyến tool:
    - `in_scope`:   câu hỏi có thuộc phạm vi pháp luật Việt Nam không.
                    False → agent trả fallback "ngoài phạm vi" ngay, không gọi tool.
    - `is_specific`: câu hỏi có đề cập Điều/Khoản/Điểm/Chương hoặc văn bản cụ thể
                     không. True → ưu tiên `get_specific_article` (deterministic,
                     filter metadata). False → dùng `search_legal_documents`
                     (semantic).
    """
    # Không yêu cầu LLM output field này — caller (analyzer) tự set lại
    # sau khi parse, để tránh LLM paraphrase/sửa câu gốc.
    original_query: str = Field(default="", description="Câu hỏi gốc của người dùng")

    # --- Core routing signals ---
    in_scope: bool = Field(
        default=True,
        description="Câu hỏi thuộc phạm vi pháp luật Việt Nam / CSDL văn bản không?",
    )
    is_specific: bool = Field(
        default=False,
        description="Có đề cập tới Điều/Khoản/Điểm/Chương hoặc văn bản cụ thể không?",
    )
    extracted_blocks: List[ArticleBlock] = Field(
        default_factory=list,
        description="Các cụm (block) thực thể pháp lý cụ thể được trích xuất",
    )

    # --- Intent (giữ lại vì có giá trị cho generate prompt) ---
    intent: Intent = Field(default=Intent.LOOKUP, description="Intent của câu hỏi")

    # --- Flags phụ để router bật thêm tool ---
    needs_metadata_search: bool = Field(
        default=False,
        description="Hỏi về loại/cơ quan/ngày/danh sách → cần search_document_metadata",
    )
    needs_relationship_check: bool = Field(
        default=False,
        description="Hỏi về sửa đổi/thay thế/hiệu lực → cần find_related_documents",
    )

    # --- Context phụ ---
    keywords: List[str] = Field(default_factory=list, description="Từ khoá chính (3-7 từ)")
    reasoning: str = Field(default="", description="Giải thích ngắn (1-2 câu)")

    # ------------------------------------------------------------------
    # Validators (xử lý quirks của LLM output)
    # ------------------------------------------------------------------
    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_intent(cls, v):
        """LLM hay trả 'LOOKUP' / 'Lookup' — chuẩn hoá về lowercase cho enum."""
        if isinstance(v, str):
            v = v.strip().lower()
        return v or "lookup"

    @field_validator("keywords", mode="before")
    @classmethod
    def _clean_keywords(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        return [str(k).strip() for k in v if str(k).strip()]

    @field_validator("reasoning", mode="before")
    @classmethod
    def _truncate_reasoning(cls, v):
        return (str(v) if v else "")[:500]

    @model_validator(mode="after")
    def _sync_is_specific(self):
        """Nếu LLM trích được block thì is_specific phải True (bất kể LLM nói gì)."""
        if self.extracted_blocks and not self.is_specific:
            self.is_specific = True
        return self


class ToolExecutionResult(BaseModel):
    """Kết quả thực thi một tool"""
    tool_name: str = Field(..., description="Tên tool được thực thi")
    success: bool = Field(..., description="Có thực thi thành công không?")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Kết quả từ tool")
    error: Optional[str] = Field(default=None, description="Lỗi nếu có")
    execution_time: float = Field(default=0.0, description="Thời gian thực thi (giây)")


class AgentStep(BaseModel):
    """Một bước trong quá trình suy luận của agent"""
    step_number: int = Field(..., description="Số thứ tự bước")
    reasoning: str = Field(..., description="Lý do chọn tool này")
    tool_name: str = Field(..., description="Tên tool được sử dụng")
    tool_input: Dict[str, Any] = Field(..., description="Input của tool")
    result: Optional[ToolExecutionResult] = Field(default=None, description="Kết quả")


class AgentResponse(BaseModel):
    """Response cuối cùng từ agent"""
    query: str = Field(..., description="Câu hỏi gốc")
    analysis: QueryAnalysisResult = Field(..., description="Kết quả phân tích query")
    steps: List[AgentStep] = Field(default_factory=list, description="Các bước suy luận")
    retrieved_documents: List[Dict[str, Any]] = Field(default_factory=list, description="Tài liệu được truy xuất")
    final_answer: str = Field(..., description="Câu trả lời cuối cùng")
    sources: List[str] = Field(default_factory=list, description="Danh sách nguồn tài liệu")


class DocumentSearchResult(BaseModel):
    """Kết quả tìm kiếm tài liệu"""
    doc_id: str = Field(..., description="ID của tài liệu")
    title: str = Field(..., description="Tiêu đề")
    content: str = Field(..., description="Nội dung")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata")
    similarity_score: Optional[float] = Field(default=None, description="Điểm tương tự (0-1)")
    relevance_score: Optional[float] = Field(default=None, description="Điểm liên quan (0-1)")


class DocumentMetadataResult(BaseModel):
    """Kết quả tìm kiếm metadata tài liệu"""
    doc_id: str = Field(..., description="ID của tài liệu")
    so_hieu: str = Field(..., description="Số hiệu")
    ten_van_ban: str = Field(..., description="Tên văn bản")
    loai: str = Field(..., description="Loại văn bản")
    co_quan_ban_hanh: str = Field(..., description="Cơ quan ban hành")
    ngay_ban_hanh: str = Field(..., description="Ngày ban hành")
    ngay_co_hieu_luc: Optional[str] = Field(default=None, description="Ngày có hiệu lực")
    so_dieu: int = Field(default=0, description="Số điều")


class ToolOutput(BaseModel):
    """
    Output chuẩn cho mọi tool của LegalDocumentTools.
    Giữ cả `items` (structured, có metadata đầy đủ) và `display_text`
    (đã format sẵn để LLM đọc). Nhờ vậy downstream node vừa có thể
    chấm/trích sources từ metadata, vừa có thể đút thẳng context vào prompt.
    """
    tool_name: str = Field(..., description="Tên tool")
    success: bool = Field(default=True, description="Tool chạy thành công không")
    items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Các item kết quả (chunk/metadata/relation) với đầy đủ metadata"
    )
    display_text: str = Field(default="", description="Phiên bản text để hiển thị/đưa vào LLM")
    error: Optional[str] = Field(default=None, description="Thông báo lỗi nếu có")


class ValidationResult(BaseModel):
    """Kết quả node validate_answer (LLM-as-judge)."""
    faithful: bool = Field(..., description="Câu trả lời có bám ngữ cảnh không")
    has_citation: bool = Field(..., description="Có trích dẫn Điều/Khoản/Số hiệu không")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Điểm tổng 0-1")
    issues: List[str] = Field(default_factory=list, description="Danh sách vấn đề phát hiện")
    reasoning: str = Field(default="", description="Giải thích của judge")
 