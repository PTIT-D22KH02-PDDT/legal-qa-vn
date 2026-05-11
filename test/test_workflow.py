"""
Test workflow LangGraph — end-to-end từ question → analyze → branches → merge_results → generate_response.

Chạy:
    uv run src/agent/test_workflow.py
"""
import sys
import logging
from pathlib import Path

from src.indexing.embedding.remote_embedding import RemoteEmbeddingModel
from src.indexing.vector_store.chroma_store import ChromaStore
from src.indexing.vector_store.schemas import ChromaConfig
from src.search.reranker import RemoteReranker
from src.search.search import SearchService
from system.test.test_folder_law_local import COLLECTION_NAME

# Đảm bảo project root trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Khởi tạo dependencies
# ---------------------------------------------------------------------------
import yaml
from main import build_search_service


from system.database.db_respository import (
    DatabaseConfig,
    DatabaseManager,
    DocumentMetadataRepository,
    DocumentRelationRepository,
)
from src.agent.tools import LegalAgentTools
from src.agent.graph import build_graph
from src.agent.state import initial_state
from src.api.remote_client import RemoteAPIClient
from src.api.nvidia_api_client import OpenAICompatibleClient


COLLECTION_NAME="legal_documents"
CHROMA_DIR="chroma_db"
def setup_dependencies():
    """Khởi tạo tất cả dependencies cần cho workflow."""
    llm = OpenAICompatibleClient()
    
    # Init Chroma
    chroma_store = ChromaStore(ChromaConfig(
        collection_name=COLLECTION_NAME,
        is_persist=True,
        persist_directory=CHROMA_DIR,
        distance_metric='cosine'
    ))
    # Init DB

    api_client = RemoteAPIClient()
    embedding_model = RemoteEmbeddingModel(api_client)
    reranker = RemoteReranker(api_client)
    
    search_service = SearchService(
        chroma_store=chroma_store,
        embedding_model=embedding_model,
        reranker=reranker
    )
    


    # Database
    db_config = DatabaseConfig()
    db_manager = DatabaseManager(db_config)
    session = db_manager.get_session()
    meta_repo = DocumentMetadataRepository(session)
    relation_repo = DocumentRelationRepository(session)
    
    # Tools
    retriever = LegalAgentTools(
        search_service=search_service,
        chroma_store=chroma_store,
        meta_repo=meta_repo,
        relation_repo=relation_repo,
        api_client=api_client
    )
    
    # LLM Client
    llm = OpenAICompatibleClient()
    
    return {
        "llm": llm,
        "db_client": db_manager,
        "retriever": retriever,
        "doc_retriever": retriever,
    }


def run_workflow_test(question: str, deps: dict):
    """Chạy workflow từ đầu đến cuối."""
    print("\n" + "="*80)
    print(f"[WORKFLOW TEST] Question: {question}")
    print("="*80)
    
    # 1. Build graph
    print("\n[1] Building graph...")
    graph = build_graph(
        llm=deps["llm"],
        db_client=deps["db_client"],
        retriever=deps["retriever"],
        doc_retriever=deps["doc_retriever"],
    )
    print("✓ Graph built successfully")
    
    # 2. Khởi tạo state
    print("\n[2] Initializing state...")
    initial = initial_state(question)
    print(f"✓ Initial state created")
    print(f"   question: {initial['question']}")
    
    # 3. Chạy workflow
    print("\n[3] Running workflow...")
    try:
        result = graph.invoke(initial)
        print("✓ Workflow completed")
    except Exception as e:
        print(f"✗ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # 4. In kết quả
    print("\n[4] WORKFLOW RESULTS:")
    print("-" * 80)
    
    if result.get("answer"):
        print(f"[ANSWER]:\n{result['answer']}\n")
    else:
        print("[ANSWER]: (None)\n")
    
    if result.get("sub_questions"):
        print(f"[SUB-QUESTIONS]: {len(result['sub_questions'])} questions")
        for i, sq in enumerate(result["sub_questions"], 1):
            print(f"  {i}. {sq.query} (intent={sq.intent})")
        print()
    
    if result.get("sub_question_contexts"):
        print(f"[SUB-QUESTION CONTEXTS]: {len(result['sub_question_contexts'])} contexts")
        for query_key, ctx_data in result["sub_question_contexts"].items():
            print(f"  - '{query_key}'")
            print(f"    intent: {ctx_data.get('intent')}")
            context_len = len(ctx_data.get('formatted_context', ''))
            print(f"    context: {context_len} ký tự")
        print()
    
    if result.get("context_chunks"):
        print(f"[CONTEXT CHUNKS]: {len(result['context_chunks'])} chunks")
        for c in result["context_chunks"][:3]:
            print(f"  - {c.chunk_id}")
            text_preview = (c.metadata.get('full_text') or c.text)[:80]
            print(f"    {text_preview}...")
        print()
    
    if result.get("tool_outputs"):
        print(f"[TOOL OUTPUTS]: {len(result['tool_outputs'])} tools called")
        for to in result["tool_outputs"]:
            print(f"  - {to.tool_name}: success={to.success}")
        print()
    
    return result


SEP = "-" * 80


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_single_legal_query(deps: dict):
    """TC1: Single sub_question với intent=legal_query."""
    question = "Khoản 1 Điều 6 Nghị định 100/2019/NĐ-CP quy định mức phạt bao nhiêu?"
    result = run_workflow_test(question, deps)
    assert result is not None
    assert result.get("answer") is not None
    assert len(result.get("answer", "")) > 0
    print("[PASS] TC1: single legal_query")


def test_single_doc_relation(deps: dict):
    """TC2: Single sub_question với intent=doc_relation."""
    question = "Cho tôi thông tin cơ bản về BỘ LUẬT HÌNH SỰ"
    result = run_workflow_test(question, deps)
    assert result is not None
    assert result.get("answer") is not None
    print("[PASS] TC2: single doc_relation")


def test_single_general(deps: dict):
    """TC3: Single sub_question với intent=general."""
    question = "Cách tính lương làm thêm giờ là như thế nào?"
    result = run_workflow_test(question, deps)
    assert result is not None
    assert result.get("answer") is not None
    print("[PASS] TC3: single general")


def test_multiple_sub_questions(deps: dict):
    """TC4: Multiple sub_questions → test Send API + merge_results."""
    # Câu hỏi này sẽ được phân rã thành 2-3 sub_questions
    question = (
        "Cần phân biệt giữa hợp đồng lao động xác định thời hạn và không xác định thời hạn, "
        "và bên nào phải thanh toán bảo hiểm xã hội?"
    )
    result = run_workflow_test(question, deps)
    assert result is not None
    assert result.get("answer") is not None
    if result.get("sub_questions"):
        assert len(result["sub_questions"]) >= 2
        print(f"[INFO] Phân rã thành {len(result['sub_questions'])} sub_questions")
        if result.get("sub_question_contexts"):
            print(f"[INFO] Merge results tạo {len(result['sub_question_contexts'])} contexts")
    print("[PASS] TC4: multiple sub_questions with merge_results")


def test_chitchat_intent(deps: dict):
    """TC5: Câu hỏi không rõ ràng → fallback node."""
    question = "Cảm ơn bạn nhé!"
    result = run_workflow_test(question, deps)
    assert result is not None
    assert result.get("answer") is not None
    print("[PASS] TC5: chitchat fallback")


# ---------------------------------------------------------------------------
# Interactive Mode
# ---------------------------------------------------------------------------

def interactive_mode(deps: dict):
    """Mode nhập tự do: người dùng nhập câu hỏi và workflow trả lời."""
    print("\n" + "="*80)
    print("INTERACTIVE MODE - Nhập câu hỏi tuỳ ý")
    print("="*80)
    print("(Nhập 'quit' hoặc 'exit' để thoát)\n")
    
    while True:
        try:
            question = input("📝 Câu hỏi của bạn: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("\nTạm biệt! 👋\n")
                break
            
            if not question:
                print("⚠ Vui lòng nhập câu hỏi.\n")
                continue
            
            # Chạy workflow
            result = run_workflow_test(question, deps)
            
            if result is None:
                print("\n❌ Workflow thất bại. Vui lòng thử lại.\n")
                continue
            
            print("\n")
        
        except KeyboardInterrupt:
            print("\n\nTạm biệt! 👋\n")
            break
        except Exception as e:
            print(f"\n❌ Lỗi: {e}\n")
            import traceback
            traceback.print_exc()
            continue


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*80)
    print("WORKFLOW TESTS - LangGraph End-to-End")
    print("="*80)
    
    print("\n[SETUP] Initializing dependencies...")
    try:
        deps = setup_dependencies()
        print("✓ All dependencies initialized\n")
    except Exception as e:
        print(f"✗ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Menu lựa chọn
    print("\n" + "="*80)
    print("CHỌN CHẾ ĐỘ")
    print("="*80)
    print("1. Chạy test cases (TC1-TC5)")
    print("2. Mode tương tác (nhập câu hỏi tuỳ ý)")
    print()
    
    mode = input("Chọn chế độ (1 hoặc 2): ").strip()
    
    if mode == "2":
        # Interactive mode
        interactive_mode(deps)
    else:
        # Test cases mode (default)
        # List of tests
        tests = [
            ("TC1: Single legal_query", test_single_legal_query),
            ("TC2: Single doc_relation", test_single_doc_relation),
            ("TC3: Single general", test_single_general),
            ("TC4: Multiple sub_questions + merge_results", test_multiple_sub_questions),
            ("TC5: Fallback chitchat", test_chitchat_intent),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_fn in tests:
            try:
                print(f"\n\n{'='*80}")
                print(f"Running: {test_name}")
                print('='*80)
                test_fn(deps)
                passed += 1
            except Exception as e:
                print(f"\n[FAIL] {test_name}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
        
        # Summary
        print(f"\n\n{'='*80}")
        print(f"SUMMARY: {passed} passed / {failed} failed / {len(tests)} total")
        print(f"{'='*80}\n")
        
        sys.exit(0 if failed == 0 else 1)
