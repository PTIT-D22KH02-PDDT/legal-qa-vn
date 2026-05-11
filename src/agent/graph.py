from __future__ import annotations
from langgraph.graph import START, END, StateGraph
from langgraph.types import Send
from src.agent.schemas import Intent
from src.agent.state import AgentState
from src.agent.nodes import(
    make_analyze_node,
    make_fallback_node,
    # make_doc_retrieve_node,
    make_legal_query_node,
    make_general_node,
    make_doc_relation_node,
    make_evaluate_chunks_node,
    make_merge_results_node,
    make_generate_response_node,
)
import logging
from typing import Any

logger = logging.getLogger(__name__)

def route_intent(state: AgentState):
    """
    Hàm định tuyến (Router) dựa trên intent từ node analyze.
    Sử dụng Send API để thực hiện Map-Reduce (chạy song song các intent).
    """
    sub_questions = state.get("sub_questions", [])
    
    if not sub_questions:
        return [Send("fallback", {"current_sub_question": None})]
        
    sends = []
    for sq in sub_questions:
        intent = sq.intent
        
        # Chuyển đổi intent sang tên node tương ứng.
        # if intent == Intent.DOC_RETRIEVE:
        #     sends.append(Send("doc_retrieve", {"current_sub_question": sq}))
        # elif intent == Intent.LEGAL_QUERY:
        if intent == Intent.LEGAL_QUERY:
            sends.append(Send("legal_query", {"current_sub_question": sq}))
        elif intent == Intent.GENERAL:
            sends.append(Send("general", {"current_sub_question": sq}))
        elif intent == Intent.DOC_RELATION:
            sends.append(Send("doc_relation", {"current_sub_question": sq}))
        else:
            sends.append(Send("fallback", {"current_sub_question": sq}))
            
    return sends

def build_graph(
    llm: Any,
    db_client: Any,
    retriever: Any,
    doc_retriever: Any
) -> StateGraph:

    workflow = StateGraph(AgentState)
    
    # 1. Thêm các node với tham số đã được căn chỉnh khớp với definitions trong nodes.py
    workflow.add_node("analyze", make_analyze_node(llm))
    workflow.add_node("fallback", make_fallback_node(llm))
    # workflow.add_node("doc_retrieve", make_doc_retrieve_node(retriever))
    workflow.add_node("legal_query", make_legal_query_node(retriever, llm))
    workflow.add_node("general", make_general_node(retriever, llm))
    workflow.add_node("doc_relation", make_doc_relation_node(retriever, llm))
    workflow.add_node("evaluate_chunks", make_evaluate_chunks_node(llm))
    workflow.add_node("merge_results", make_merge_results_node())
    workflow.add_node("generate_response", make_generate_response_node(retriever, llm))

    # 2. Luồng thực thi: Bắt đầu -> Analyze
    workflow.add_edge(START, "analyze")

    # 3. Phân nhánh: Analyze -> 5 nhánh dựa vào hàm route_intent
    workflow.add_conditional_edges(
        "analyze",
        route_intent,
        [
            # "doc_retrieve", 
            "legal_query", 
            "general", 
            "doc_relation", 
            "fallback"
        ]
    )

    # 4. Gom các nhánh về node merge_results để tổ chức context:
    # - legal_query, doc_relation, general: tìm kiếm song song → gom vào merge_results
    # - merge_results: tổ chức context theo từng sub_question → truyền sang generate_response
    # workflow.add_edge("doc_retrieve", "merge_results")
    workflow.add_edge("legal_query", "merge_results")
    workflow.add_edge("doc_relation", "merge_results")
    
    # general node qua evaluate_chunks để lọc chunks -> sau đó qua merge_results
    workflow.add_edge("general", "evaluate_chunks")
    workflow.add_edge("evaluate_chunks", "merge_results")

    # Nhánh fallback (câu hỏi không rõ ràng) trả về answer luôn và đi thẳng tới END
    workflow.add_edge("fallback", END)

    # 5. merge_results -> generate_response -> END
    workflow.add_edge("merge_results", "generate_response")
    workflow.add_edge("generate_response", END)

    compiled = workflow.compile()
    return compiled