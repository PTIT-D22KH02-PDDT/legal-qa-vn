from typing import List, TypedDict, Annotated, Optional

class AgentState(TypedDict):
    """Kiểu dữ liệu lưu trữ state của agent trong quá trình xử lý query"""
    retrieved_chunks: List[dict]  # Danh sách chunks đã được retrieval (có text, metadata, v.v.)
    intermediate_steps: List[str]  # Danh sách các bước trung gian (nếu có)
    final_answer: Optional[str]  # Câu trả lời cuối cùng (nếu đã có)
    query : str  # Câu hỏi gốc của người dùng
    