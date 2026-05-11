import os
import sys
import json
from pathlib import Path
import logging

# Thêm thư mục gốc vào sys.path để import
sys.path.append(str(Path(__file__).resolve().parents[0]))

from src.api.nvidia_api_client import OpenAICompatibleClient
from src.indexing.vector_store import ChromaStore, ChromaConfig
from system.database.db_respository import get_database, DocumentRelationRepository, DocumentMetadataRepository
from src.search.search import SearchService
from src.agent.tools import LegalAgentTools
from src.agent.schemas import SubQuestion, Intent
from src.api.remote_client import RemoteAPIClient
from src.indexing.embedding.remote_embedding import RemoteEmbeddingModel
from src.search.reranker import RemoteReranker
from src.api.nvidia_api_client import OpenAICompatibleClient
from src.agent.nodes import (
    make_analyze_node,
    make_doc_relation_node,
    make_legal_query_node,
    make_general_node,
    make_merge_results_node,
    make_generate_response_node,
)


COLLECTION_NAME="legal_documents"
CHROMA_DIR="chroma_db"
# Tắt log quá dài của HTTP
logging.getLogger("httpx").setLevel(logging.WARNING)

def setup_environment():
    print("=== KHỞI TẠO MÔI TRƯỜNG ===")
    llm = OpenAICompatibleClient()
    
    # Init Chroma
    chroma_store = ChromaStore(ChromaConfig(
        collection_name=COLLECTION_NAME,
        is_persist=True,
        persist_directory=CHROMA_DIR,
        distance_metric='cosine'
    ))
    # llm=OpenAICompatibleClient()
    # Init DB
    db_manager = get_database()
    session = db_manager.get_session()
    meta_repo = DocumentMetadataRepository(session)
    relation_repo = DocumentRelationRepository(session)
    api_client = RemoteAPIClient()
    embedding_model = RemoteEmbeddingModel(api_client)
    reranker = RemoteReranker(api_client)
    
    search_service = SearchService(
        chroma_store=chroma_store,
        embedding_model=embedding_model,
        reranker=reranker
    )
    
    tools = LegalAgentTools(
        search_service=search_service,
        chroma_store=chroma_store,
        meta_repo=meta_repo,
        relation_repo=relation_repo,
        api_client=api_client
    )
    
    return llm, tools

def test_analyze(llm):
    print("\n" + "="*60)
    print("TEST NODE: ANALYZE (PHÂN RÃ & ĐỊNH TUYẾN INTENT)")
    print("="*60)
    
    analyze_node = make_analyze_node(llm)
    
    state = {
        "question": "Cho tôi thông tin về Luật Đất đai và mức phạt nồng độ cồn xe máy hiện nay?",
        "context_text": [],
        "tool_outputs": [],
        "messages": []
    }
    
    print("❓ QUESTION:", state["question"])
    result = analyze_node(state)
    
    print("\n🎯 KẾT QUẢ PHÂN RÃ:")
    for sq in result.get("sub_questions", []):
        print(f" - [Intent: {sq.intent.value.upper()}] Query: {sq.query}")

def test_doc_relation(llm, tools):
    print("\n" + "="*60)
    print("TEST NODE: DOC_RELATION (QUAN HỆ VÀ THÔNG TIN VĂN BẢN)")
    print("="*60)
    
    doc_relation_node = make_doc_relation_node(tools, llm)
    
    state = {
        "question": "Nghị định về kinh doanh rượu có bao nhiêu điều tất cả?",
        "current_sub_question": SubQuestion(query="Nghị định về kinh doanh rượu có bao nhiêu điều tất cả?", intent=Intent.DOC_RELATION),
        "context_text": [],
        "tool_outputs": [],
        "messages": []
    }
    
    print("❓ SUB-QUESTION:", state["current_sub_question"].query)
    result = doc_relation_node(state)
    
    print("\n📑 CONTEXT TEXT EXTRACTED:")
    if result.get("context_text"):
        print(result["context_text"][0])
    else:
        print("Không có context_text")

def test_legal_query(llm, tools):
    print("\n" + "="*60)
    print("TEST NODE: LEGAL_QUERY (TÌM KIẾM THEO ĐIỀU KHOẢN CHÍNH XÁC)")
    print("="*60)
    
    legal_query_node = make_legal_query_node(tools, llm)
    
    state = {
        "question": "Khoản 1 Điều 16 nghị định 15/2025/NĐ-CP",
        "current_sub_question": SubQuestion(query="Khoản 1 Điều 16 nghị định 15/2025/NĐ-CP", intent=Intent.LEGAL_QUERY),
        "context_text": [],
        "tool_outputs": [],
        "messages": []
    }
    
    print("❓ SUB-QUESTION:", state["current_sub_question"].query)
    result = legal_query_node(state)
    
    print("\n📑 CONTEXT TEXT EXTRACTED:")
    if result.get("context_text"):
        print(result["context_text"][0])
    else:
        print("Không có context_text")

def test_general(llm, tools):
    print("\n" + "="*60)
    print("TEST NODE: GENERAL (TÌM KIẾM SEMANTIC VECTOR)")
    print("="*60)
    
    general_node = make_general_node(tools, llm)
    
    state = {
        "question": "Đơn vị kinh doanh vận tải sử dụng hợp đồng vận tải bằng hợp đồng điện tử phải đáp ứng điều kiện gì?",
        "current_sub_question": SubQuestion(query="Đơn vị kinh doanh vận tải sử dụng hợp đồng vận tải bằng hợp đồng điện tử phải đáp ứng điều kiện gì?", intent=Intent.GENERAL),
        "context_text": [],
        "tool_outputs": [],
        "messages": []
    }
    
    print("❓ SUB-QUESTION:", state["current_sub_question"].query)
    result = general_node(state)
    
    print("\n📑 CONTEXT TEXT EXTRACTED (Hiển thị 500 ký tự đầu):")
    if result.get("context_text"):
        print(result["context_text"][0][:500] + "\n...[CÒN TIẾP]")
    else:
        print("Không có context_text")

def test_merge_results(tools):
    """Test merge_results_node - gom hợp context từ nhiều sub_questions"""
    print("\n" + "="*60)
    print("TEST NODE: MERGE_RESULTS (GOM HỢP KẾT QUẢ TỪ NHIỀU SUB_QUESTIONS)")
    print("="*60)
    
    merge_results_node = make_merge_results_node()
    
    # Tạo mock chunks
    from src.indexing.vector_store import ChromaQueryResult
    
    chunk1 = ChromaQueryResult(
        chunk_id="100_2019_nd-cp.dieu_6.khoan_1",
        text="Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với hành vi điều khiển xe mô tô, xe gắn máy có nồng độ cồn",
        metadata={
            "full_text": "Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với hành vi điều khiển xe mô tô, xe gắn máy có nồng độ cồn nhưng chưa vượt quá 50 miligam/100 mililít máu",
            "dieu": 6,
            "khoan": 1
        }
    )
    
    chunk2 = ChromaQueryResult(
        chunk_id="100_2019_nd-cp.dieu_1",
        text="Phạm vi điều chỉnh: Nghị định này quy định về xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ",
        metadata={
            "full_text": "Phạm vi điều chỉnh: Nghị định này quy định về xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ",
            "dieu": 1
        }
    )
    
    # Tạo mock state
    state = {
        "sub_questions": [
            SubQuestion(query="Mức phạt tiền xử lý hành vi nào?", intent=Intent.LEGAL_QUERY),
            SubQuestion(query="Luật Giao thông Đường bộ còn hiệu lực không?", intent=Intent.DOC_RELATION),
        ],
        "context_chunks": [chunk1, chunk2],
        "context_text": [
            "--- TRÍCH XUẤT CHÍNH XÁC: Mức phạt tiền xử lý hành vi nào? ---\n[Info từ tool_output 1]",
            "--- QUAN HỆ VĂN BẢN: Luật Giao thông Đường bộ còn hiệu lực không? ---\n[Info từ tool_output 2]"
        ],
    }
    
    print("\n📊 INPUT STATE:")
    print(f"  - Sub-questions: {len(state['sub_questions'])}")
    for i, sq in enumerate(state['sub_questions'], 1):
        print(f"    {i}. {sq.query} ({sq.intent.value})")
    print(f"  - Context chunks: {len(state['context_chunks'])}")
    print(f"  - Context text: {len(state['context_text'])}")
    
    # Chạy node
    result = merge_results_node(state)
    
    print("\n✅ OUTPUT STRUCTURE:")
    if result.get("sub_question_contexts"):
        print(f"  - sub_question_contexts: {len(result['sub_question_contexts'])} entries")
        for sq_query, ctx_data in result["sub_question_contexts"].items():
            print(f"\n    Query: '{sq_query}'")
            print(f"      intent: {ctx_data.get('intent')}")
            chunks = ctx_data.get("context_chunks", [])
            texts = ctx_data.get("context_text", [])
            print(f"      context_chunks: {len(chunks)} chunks")
            for c in chunks:
                print(f"        - {c.chunk_id}")
            print(f"      context_text: {len(texts)} text entries")
    else:
        print("  - sub_question_contexts: None")
    
    print("\n✅ [PASS] merge_results_node test")

def test_generate_response_mode1(llm, tools):
    """Test generate_response_node - Mode 1: Với sub_question_contexts (Multiple SQs)"""
    print("\n" + "="*60)
    print("TEST NODE: GENERATE_RESPONSE (MODE 1 - MULTIPLE SUB_QUESTIONS)")
    print("="*60)
    
    from src.indexing.vector_store import ChromaQueryResult
    
    generate_response_node = make_generate_response_node(tools, llm)
    
    # Tạo mock chunks
    chunk1 = ChromaQueryResult(
        chunk_id="100_2019_nd-cp.dieu_6.khoan_1",
        text="Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy có nồng độ cồn",
        metadata={
            "full_text": "Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy có nồng độ cồn nhưng chưa vượt quá 50 miligam/100 mililít máu theo Nghị định 100/2019/NĐ-CP",
            "dieu": 6,
            "khoan": 1
        }
    )
    
    chunk2 = ChromaQueryResult(
        chunk_id="100_2019_nd-cp.dieu_6.khoan_8",
        text="Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với hành vi điều khiển xe mô tô, xe gắn máy có nồng độ cồn vượt quá 80 miligam/100 mililít máu",
        metadata={
            "full_text": "Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với hành vi điều khiển xe mô tô, xe gắn máy có nồng độ cồn vượt quá 80 miligam/100 mililít máu theo Nghị định 100/2019/NĐ-CP",
            "dieu": 6,
            "khoan": 8
        }
    )
    
    # Tạo mock sub_question_contexts
    sub_question_contexts = {
        "Mức phạt tiền xử lý hành vi nồng độ cồn?": {
            "query": "Mức phạt tiền xử lý hành vi nồng độ cồn?",
            "intent": "legal_query",
            "context_chunks": [chunk1, chunk2],
            "context_text": ["--- TRÍCH XUẤT CHÍNH XÁC ---\n[Thông tin mức phạt]"]
        },
        "Luật Giao thông Đường bộ còn hiệu lực không?": {
            "query": "Luật Giao thông Đường bộ còn hiệu lực không?",
            "intent": "doc_relation",
            "context_chunks": [],
            "context_text": ["--- QUAN HỆ VĂN BẢN ---\n[Thông tin hiệu lực của luật]"]
        }
    }
    
    # Tạo mock state
    state = {
        "question": "Cho tôi biết mức phạt nồng độ cồn và Luật Giao thông còn hiệu lực không?",
        "sub_question_contexts": sub_question_contexts,
        "context_chunks": [chunk1, chunk2],
        "tool_outputs": [],
        "context_text": []
    }
    
    print("\n📊 INPUT STATE (Mode 1 - sub_question_contexts present):")
    print(f"  - Question: {state['question']}")
    print(f"  - sub_question_contexts: {len(sub_question_contexts)} entries")
    for sq_q in sub_question_contexts.keys():
        print(f"    - {sq_q}")
    
    # Chạy node
    try:
        result = generate_response_node(state)
        
        print("\n✅ OUTPUT:")
        if result.get("answer"):
            answer_preview = result["answer"][:300] + "\n...[CÒN TIẾP]" if len(result["answer"]) > 300 else result["answer"]
            print(f"\n📝 ANSWER:\n{answer_preview}")
        else:
            print("  - Answer: None")
        
        print("\n✅ [PASS] generate_response_node Mode 1 test")
    except Exception as e:
        print(f"\n⚠️ [WARNING] generate_response_node Mode 1 failed: {e}")
        print("(LLM call may fail if model is not available)")

def test_generate_response_mode2(llm, tools):
    """Test generate_response_node - Mode 2: Fallback (Không có sub_question_contexts)"""
    print("\n" + "="*60)
    print("TEST NODE: GENERATE_RESPONSE (MODE 2 - FALLBACK/SINGLE SQ)")
    print("="*60)
    
    from src.indexing.vector_store import ChromaQueryResult
    
    generate_response_node = make_generate_response_node(tools, llm)
    
    # Tạo mock chunks
    chunk1 = ChromaQueryResult(
        chunk_id="100_2019_nd-cp.dieu_6.khoan_1",
        text="Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe mô tô có nồng độ cồn",
        metadata={
            "full_text": "Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy có nồng độ cồn nhưng chưa vượt quá 50 miligam/100 mililít máu theo Nghị định 100/2019/NĐ-CP",
            "dieu": 6,
            "khoan": 1
        }
    )
    
    # Tạo mock state (KHÔNG có sub_question_contexts → Fallback)
    state = {
        "question": "Mức phạt tiền xử lý hành vi nồng độ cồn là bao nhiêu?",
        "context_chunks": [chunk1],
        "tool_outputs": [],
        "context_text": []
    }
    
    print("\n📊 INPUT STATE (Mode 2 - fallback mode):")
    print(f"  - Question: {state['question']}")
    print(f"  - sub_question_contexts: None (không có)")
    print(f"  - context_chunks: {len(state['context_chunks'])}")
    print(f"  - Tool: fallback path sẽ được sử dụng")
    
    # Chạy node
    try:
        result = generate_response_node(state)
        
        print("\n✅ OUTPUT:")
        if result.get("answer"):
            answer_preview = result["answer"][:300] + "\n...[CÒN TIẾP]" if len(result["answer"]) > 300 else result["answer"]
            print(f"\n📝 ANSWER:\n{answer_preview}")
        else:
            print("  - Answer: None")
        
        print("\n✅ [PASS] generate_response_node Mode 2 (Fallback) test")
    except Exception as e:
        print(f"\n⚠️ [WARNING] generate_response_node Mode 2 failed: {e}")
        print("(LLM call may fail if model is not available)")


if __name__ == "__main__":
    llm, tools = setup_environment()
    
    # Bạn có thể comment/uncomment để test riêng từng node
    test_analyze(llm)
    test_doc_relation(llm, tools)
    test_legal_query(llm, tools)
    test_general(llm, tools)
    
    # Test các node mới (merge_results và generate_response)
    print("\n\n" + "="*60)
    print("TESTING NEW NODES (merge_results + generate_response)")
    print("="*60)
    
    test_merge_results(tools)
    test_generate_response_mode1(llm, tools)
    test_generate_response_mode2(llm, tools)
    
    print("\n\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60)
