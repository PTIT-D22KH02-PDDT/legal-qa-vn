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
from typing import Annotated, List, Optional

from typing_extensions import TypedDict

from .schemas import Intent, ToolOutput


class AgentState(TypedDict, total=False):
    """
    Trạng thái Agent chạy qua LangGraph.

    Lifecycle:
        1. `question` được set từ đầu vào người dùng.
        2. Node `analyze` điền intent, sub_questions, linh_vuc, keywords.
        3. Router phân nhánh theo intent.
        4. Các node tool tích lũy vào `tool_outputs` và `context_chunks`.
        5. Node `generate` đọc context và tạo `answer`.
    """

    question: str
    """Câu hỏi gốc của người dùng, không được sửa đổi."""


    intent: Optional[Intent]
    """Intent được phân loại. Dùng để router quyết định nhánh."""

    sub_questions: List[str]
    """
    Câu hỏi sau khi phân rã (decompose). Nếu câu hỏi đơn giản,
    list này chứa đúng 1 phần tử là câu hỏi gốc.
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

    iteration: int
    """Số vòng lặp search đã thực hiện. Dùng để tránh loop vô tận."""

    max_iterations: int
    """Số vòng lặp tối đa cho phép (mặc định: 2)."""

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
        intent=None,
        sub_questions=[],
        linh_vuc=None,
        keywords=[],
        tool_outputs=[],
        context_text=[],
        iteration=0,
        max_iterations=max_iterations,
        answer=None,
        error=None,
    )
