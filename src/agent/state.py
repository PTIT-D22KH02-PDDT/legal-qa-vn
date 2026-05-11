"""
AgentState — Trạng thái trung tâm của LangGraph Agent.

State được truyền qua tất cả các Node trong graph. Mỗi Node
có thể đọc state hiện tại và trả về dict để cập nhật một phần.

Các trường dùng `Annotated[List, operator.add]` sẽ được LangGraph
*tích lũy* (append) thay vì ghi đè — phù hợp cho context và tool_outputs
được thu thập dần qua nhiều nhánh/vòng lặp.
"""
from __future__ import annotations

import operator
from typing import Annotated, List, Optional, Dict, Any

from typing_extensions import TypedDict

from .schemas import Intent, ToolOutput, SubQuestion
from src.indexing.vector_store import ChromaQueryResult


class AgentState(TypedDict, total=False):
    """
    Trạng thái Agent chạy qua LangGraph.
    - `question` được set từ đầu vào người dùng.
    - Node `analyze` điền intent, sub_questions, linh_vuc, keywords.
    - Router phân nhánh theo intent.
    - Các node tool tích lũy vào `tool_outputs` và `context_chunks`.
    - Node `generate` đọc context và tạo `answer`.
    """

    question: str
    """Câu hỏi gốc của người dùng, không được sửa đổi."""


    current_sub_question: Optional[SubQuestion]
    """Câu hỏi con hiện tại đang được xử lý bởi một nhánh cụ thể (dành cho Send API)."""

    sub_questions: List[SubQuestion]
    """
    Danh sách các câu hỏi con sau khi phân rã (decompose).
    """

    linh_vuc: Optional[str]
    """
    Lĩnh vực pháp lý được xác định (ví dụ: 'dân sự', 'hình sự', 'đất đai').
    Dùng để lọc metadata khi gọi vector_search trong nhánh GENERAL.
    """

    keywords: List[str]
    """Từ khóa chính trích xuất từ câu hỏi, dùng bổ trợ cho search."""


    tool_outputs: Annotated[List[ToolOutput], operator.add]
    """
    Danh sách ToolOutput tích lũy từ tất cả các tool đã gọi.
    Dùng Annotated[List, operator.add] để LangGraph append thay vì ghi đè.
    """

    context_text: Annotated[List[str], operator.add]
    """
    Danh sách các đoạn context text đã format, tích lũy từ tool_outputs.
    Node generate sẽ join list này để tạo context đầy đủ cho LLM.
    """
    
    context_chunks: Annotated[List[ChromaQueryResult], operator.add]
    """
    Danh sách chunks đã được đánh giá và lọc từ evaluate_chunks_node.
    Dùng trong generate_response_node để gọi _evaluate_refs và mở rộng context.
    """
    
    sub_question_contexts: Optional[Dict[str, Dict[str, Any]]]
    """
    Mapping từ mỗi sub_question query → context riêng của nó.
    Được tạo bởi merge_results_node.
    Cấu trúc: {
        "câu hỏi con 1": {"context_text": [...], "context_chunks": [...]},
        "câu hỏi con 2": {"context_text": [...], "context_chunks": [...]}
    }
    """
    
    answer: Optional[str]
    """Câu trả lời cuối cùng được tạo ra bởi LLM."""

    error: Optional[str]
    """Thông báo lỗi nếu có lỗi xảy ra trong quá trình xử lý."""


def initial_state(question: str, max_iterations: int = 2) -> AgentState:
    """
    Tạo AgentState mặc định cho một câu hỏi mới.

    Args:
        question: Câu hỏi của người dùng.
        max_iterations: Số vòng lặp search tối đa.

    Returns:
        AgentState với các giá trị mặc định.
    """
    return AgentState(
        question=question,
        current_sub_question=None,
        sub_questions=[],
        linh_vuc=None,
        keywords=[],
        tool_outputs=[],
        context_text=[],
        context_chunks=[],
        sub_question_contexts=None,
        answer=None,
        error=None,
    )
