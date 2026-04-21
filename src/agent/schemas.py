"""
Pydantic schemas cho LangChain Agent
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class QueryType(str, Enum):
    """Loại câu hỏi người dùng"""
    SEMANTIC_SEARCH = "semantic"        # Tìm kiếm tổng quát (không chỉ định điều cụ thể)
    SPECIFIC_LOOKUP = "specific"        # Tìm kiếm điều/khoản cụ thể
    COMPARATIVE = "comparative"         # So sánh các điều luật
    PROCEDURAL = "procedural"           # Tìm quy trình, cách làm
    CONTEXTUAL = "contextual"           # Tìm bối cảnh pháp lý (hiện hành, hủy bỏ, v.v.)
    METADATA_SEARCH = "metadata"        # Tìm tài liệu theo metadata (loại, cơ quan, ngày)


class Intent(str, Enum):
    """Intent của câu hỏi"""
    LOOKUP = "lookup"                   # Tìm kiếm thông tin
    COMPARE = "compare"                 # So sánh
    EXPLAIN = "explain"                 # Giải thích
    VERIFY = "verify"                   # Xác minh
    CALCULATE = "calculate"             # Tính toán
    DEFINE = "define"                   # Định nghĩa


class ArticleBlock(BaseModel):
    """Một cụm/block thực thể article độc lập để truy xuất"""
    dieu: Optional[int] = Field(default=None, description="Số điều (nếu có)")
    khoan: Optional[int] = Field(default=None, description="Số khoản (nếu có)")
    diem: Optional[str] = Field(default=None, description="Tên điểm (nếu có): a, b, c, ...")
    chuong: Optional[int] = Field(default=None, description="Số chương (nếu có)")
    document_name: Optional[str] = Field(default=None, description="Tên tài liệu pháp luật")


class QueryAnalysisResult(BaseModel):
    """Kết quả phân tích câu hỏi"""
    original_query: str = Field(..., description="Câu hỏi gốc từ người dùng")
    query_type: QueryType = Field(..., description="Loại câu hỏi")
    intent: Intent = Field(..., description="Intent của câu hỏi")
    
    # NEW: Danh sách các cụm thực thể article được trích xuất
    # Mỗi block là một cụm độc lập (dieu + khoan + diem + chuong) để truy xuất
    extracted_blocks: List[ArticleBlock] = Field(
        default_factory=list,
        description="Danh sách các block thực thể article được trích xuất"
    )
    
    # OLD: Entities được trích xuất (keep for backward compatibility)
    article_numbers: List[int] = Field(default_factory=list, description="[DEPRECATED] Số điều được đề cập")
    article_names: List[str] = Field(default_factory=list, description="[DEPRECATED] Tên khoản/điểm")
    document_types: List[str] = Field(default_factory=list, description="Loại văn bản (Luật, Nghị định, ...)")
    document_names: List[str] = Field(default_factory=list, description="Tên cụ thể của văn bản")
    keywords: List[str] = Field(default_factory=list, description="Từ khóa chính")
    
    # Context & metadata
    reasoning: str = Field(default="", description="Giải thích lý do phân loại")
    requires_metadata_search: bool = Field(default=False, description="Có cần tìm metadata không?")
    requires_relationship_check: bool = Field(default=False, description="Có cần kiểm tra mối quan hệ không?")
    confidence: float = Field(default=0.8, description="Độ tin cậy của phân tích (0-1)")


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
 