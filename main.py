import sys
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import logging
from pathlib import Path

import os
from datetime import datetime

# Configure logging
PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Use LOG_SUFFIX from env, or default to timestamp + pid
log_suffix = os.getenv("LOG_SUFFIX", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}")
LOG_FILE = LOG_DIR / f"app_{log_suffix}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "legal_documents"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "chroma_db"
DEFAULT_EMBEDDING_MODEL_DIR = PROJECT_ROOT / "models" / "Vietnamese_Embedding_v2"
DEFAULT_RERANKER_MODEL_NAME = "AITeamVN/Vietnamese_Reranker"


def build_chroma_store():
    """Build ChromaStore."""
    from src.indexing.vector_store import ChromaConfig
    from src.indexing.vector_store.chroma_store import ChromaStore

    config = ChromaConfig(
        collection_name=DEFAULT_COLLECTION_NAME,
        persist_directory=str(DEFAULT_CHROMA_DIR),
        distance_metric="ip",
        is_persist=True,
    )

    return ChromaStore(config=config)


def build_local_embedding_model():
    """Build local ONNX embedding model."""
    from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel

    return OnnxEmbeddingModel(
        model_dir=str(DEFAULT_EMBEDDING_MODEL_DIR),
    )


def build_remote_embedding_model(api_client):
    """Build remote embedding model."""
    from src.indexing.embedding import RemoteEmbeddingModel

    return RemoteEmbeddingModel(api_client)


def build_local_reranker():
    """Build local cross-encoder reranker."""
    from src.search import CrossEncoderReranker

    return CrossEncoderReranker(
        model_name=DEFAULT_RERANKER_MODEL_NAME,
        max_length=2304,
        batch_size=32,
    )


def build_remote_reranker(api_client):
    """Build remote reranker."""
    from src.search import RemoteReranker

    return RemoteReranker(api_client=api_client)


def build_search_service(
    *,
    use_remote_embedding: bool = True,
    use_rerank: bool = True,
    use_remote_rerank: bool = True,
):
    """Build SearchService from selected runtime options."""
    from src.api import RemoteAPIClient
    from src.search import SearchService

    chroma_store = build_chroma_store()

    api_client = RemoteAPIClient() if (use_remote_embedding or use_remote_rerank) else None

    if use_remote_embedding:
        embedding_model = build_remote_embedding_model(api_client)
    else:
        embedding_model = build_local_embedding_model()

    reranker = None

    if use_rerank:
        if use_remote_rerank:
            if api_client is None:
                api_client = RemoteAPIClient()
            reranker = build_remote_reranker(api_client)
        else:
            reranker = build_local_reranker()

    if reranker is not None:
        try:
            reranker.startup()
        except Exception as exc:
            logger.warning("Failed to startup reranker: %s", exc)

    return SearchService(
        chroma_store=chroma_store,
        embedding_model=embedding_model,
        reranker=reranker,
    )


def print_search_results(results):
    """Print search results in a readable format."""
    if not results:
        logger.info("No results found.")
        return

    logger.info("Found %d results:", len(results))

    for index, result in enumerate(results, start=1):
        logger.info("=" * 70)
        logger.info("Result #%d", index)
        logger.info("Chunk ID: %s", result.chunk_id)
        logger.info("Distance: %.4f", result.distance)

        if result.score_rerank is not None:
            logger.info("Rerank score: %.4f", result.score_rerank)

        logger.info("Text: %s", result.text[:500])

        if result.metadata:
            logger.info("Metadata: %s", result.metadata)


def handle_index_local():
    """Index document using local embedding."""
    from src.indexing.indexing import process_document

    logger.info("[LOCAL INDEXING]")

    file_path = input("Enter file path: ").strip()
    if not file_path:
        logger.warning("No file path provided.")
        return

    try:
        result = process_document(
            file_path=file_path,
            use_remote_api=False,
        )

        logger.info("Indexing result: %s", result)

    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)


def handle_index_remote():
    """Index document using remote embedding API."""
    from src.indexing.indexing import process_document

    logger.info("[REMOTE INDEXING]")

    file_path = input("Enter file path: ").strip()
    if not file_path:
        logger.warning("No file path provided.")
        return

    try:
        result = process_document(
            file_path=file_path,
            use_remote_api=True,
        )

        logger.info("Indexing result: %s", result)

    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)


def handle_index_folder():
    """Index all PDF documents in a folder."""
    from src.indexing.indexing import process_document
    from pathlib import Path

    logger.info("[FOLDER INDEXING]")

    dir_path_str = input("Enter directory path: ").strip()
    if not dir_path_str:
        logger.warning("No directory path provided.")
        return

    dir_path = Path(dir_path_str)
    if not dir_path.is_dir():
        logger.error("Directory does not exist: %s", dir_path_str)
        return

    use_remote_input = input("Use remote embedding? (y/n, default n): ").strip().lower()
    use_remote = use_remote_input == "y"

    # Tìm các file DOCX
    docx_files = sorted(list(dir_path.glob("*.docx")))
    if not docx_files:
        logger.warning("No DOCX files found in %s", dir_path_str)
        return

    logger.info("Found %d DOCX files. Starting indexing...", len(docx_files))

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(docx_files, 1):
        logger.info("[%d/%d] Processing: %s", i, len(docx_files), file_path.name)
        try:
            result = process_document(
                file_path=str(file_path),
                use_remote_api=use_remote,
            )
            if result.get('success'):
                logger.info("   [OK] Success: %d chunks.", result.get('chunks_count'))
                success_count += 1
            else:
                logger.warning("   [FAIL] Error: %s", result.get('message'))
                fail_count += 1
        except Exception as exc:
            logger.error("   [ERROR] System error: %s", exc)
            fail_count += 1

    logger.info("=" * 40)
    logger.info("FOLDER INDEXING COMPLETED")
    logger.info("Total: %d, Success: %d, Failed: %d", len(docx_files), success_count, fail_count)
    logger.info("=" * 40)


def handle_index_folder_remote():
    """Index all DOCX documents in a folder using remote embedding."""
    from src.indexing.indexing import process_document
    from pathlib import Path

    logger.info("[FOLDER INDEXING - REMOTE]")

    dir_path_str = input("Enter directory path: ").strip()
    if not dir_path_str:
        logger.warning("No directory path provided.")
        return

    dir_path = Path(dir_path_str)
    if not dir_path.is_dir():
        logger.error("Directory does not exist: %s", dir_path_str)
        return

    # Force using remote embedding
    use_remote = True

    # Tìm các file DOCX
    docx_files = sorted(list(dir_path.glob("*.docx")))
    if not docx_files:
        logger.warning("No DOCX files found in %s", dir_path_str)
        return

    logger.info("Found %d DOCX files. Starting remote indexing...", len(docx_files))

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(docx_files, 1):
        logger.info("[%d/%d] Processing: %s", i, len(docx_files), file_path.name)
        try:
            result = process_document(
                file_path=str(file_path),
                use_remote_api=use_remote,
            )
            if result.get('success'):
                logger.info("   [OK] Success: %d chunks.", result.get('chunks_count'))
                success_count += 1
            else:
                logger.warning("   [FAIL] Error: %s", result.get('message'))
                fail_count += 1
        except Exception as exc:
            logger.error("   [ERROR] System error: %s", exc)
            fail_count += 1

    logger.info("=" * 40)
    logger.info("FOLDER INDEXING (REMOTE) COMPLETED")
    logger.info("Total: %d, Success: %d, Failed: %d", len(docx_files), success_count, fail_count)
    logger.info("=" * 40)


def handle_search_local():
    """Search using local embedding and optional local reranker."""
    logger.info("[LOCAL SEARCH]")

    query = input("Enter query: ").strip()
    if not query:
        logger.warning("No query provided.")
        return

    top_k_retrieve = int(input("Top-k retrieve (default 10): ").strip() or "10")
    top_k_rerank = int(input("Top-k final/rerank (default 5): ").strip() or "5")

    use_rerank_input = input("Use local rerank? (y/n, default y): ").strip().lower()
    use_rerank = use_rerank_input != "n"

    try:
        search_service = build_search_service(
            use_remote_embedding=False,
            use_rerank=use_rerank,
            use_remote_rerank=False,
        )

        results = search_service.search(
            query=query,
            top_k_retrieve=top_k_retrieve,
            top_k_rerank=top_k_rerank,
            use_rerank=use_rerank,
        )

        print_search_results(results)

    except Exception as exc:
        logger.error("Search failed: %s", exc, exc_info=True)


def handle_search_remote_rerank(search_service=None):
    """
    Search using local embedding and remote reranker.

    Lưu ý:
    embedding dùng khi search phải khớp embedding đã dùng lúc indexing.
    Nếu bạn index bằng local embedding thì search cũng nên dùng local embedding.
    Nếu bạn index bằng remote embedding thì bật use_remote_embedding=True.
    """
    logger.info("[SEARCH + REMOTE RERANK]")

    query = input("Enter query: ").strip()
    if not query:
        logger.warning("No query provided.")
        return

    top_k_retrieve = int(input("Top-k retrieve (default 10): ").strip() or "60")
    top_k_rerank = int(input("Top-k final/rerank (default 5): ").strip() or "5")

    remote_embedding_input = input("Use remote embedding? (y/n, default y): ").strip().lower()
    use_remote_embedding = remote_embedding_input != "n"

    try:
        search_service = build_search_service(
            use_remote_embedding=use_remote_embedding,
            use_rerank=True,
            use_remote_rerank=True,
        )

        results = search_service.search(
            query=query,
            top_k_retrieve=top_k_retrieve,
            top_k_rerank=top_k_rerank,
            use_rerank=True,
        )

        print_search_results(results)

    except Exception as exc:
        logger.error("Search failed: %s", exc, exc_info=True)


def handle_rag(search_service=None, api_client=None):
    """Run full RAG: search + generate answer."""
    from src.api import RemoteAPIClient
    from src.rag import RAGService

    logger.info("[RAG]")

    query = input("Enter question: ").strip()

    if query.startswith("@file:"):
        file_path = query[len("@file:"):].strip()
        try:
            query = Path(file_path).read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("Failed to read query file: %s", exc)
            return

    if not query:
        logger.warning("No question provided.")
        return

    top_k_retrieve = int(input("Top-k retrieve (default 10): ").strip() or "10")
    top_k_rerank = int(input("Top-k context/final (default 5): ").strip() or "5")

    use_rerank_input = input("Use rerank? (y/n, default y): ").strip().lower()
    use_rerank = use_rerank_input != "n"

    remote_embedding_input = input("Use remote embedding? (y/n, default y): ").strip().lower()
    use_remote_embedding = remote_embedding_input != "n"

    remote_rerank_input = input("Use remote rerank? (y/n, default y): ").strip().lower()
    use_remote_rerank = remote_rerank_input != "n"

    try:
        search_service = build_search_service(
            use_remote_embedding=use_remote_embedding,
            use_rerank=use_rerank,
            use_remote_rerank=use_remote_rerank,
        )

        if api_client is None:
            api_client = RemoteAPIClient()

        rag_service = RAGService(
            search_service=search_service,
            api_client=api_client,
            top_k_retrieve=top_k_retrieve,
            top_k_rerank=top_k_rerank,
            use_rerank=use_rerank,
        )

        result = rag_service.answer(
            query=query,
            distance_threshold=rag_config.get("distance_threshold"),
        )

        logger.info("=" * 70)
        logger.info("Question: %s", result.query)
        logger.info("Answer:\n%s", result.answer)
        logger.info("=" * 70)

    except Exception as exc:
        logger.error("RAG failed: %s", exc, exc_info=True)


def setup_workflow_dependencies():
    """Khởi tạo dependencies cho LangGraph workflow."""
    from src.indexing.embedding.remote_embedding import RemoteEmbeddingModel
    from src.indexing.vector_store.chroma_store import ChromaStore
    from src.indexing.vector_store.schemas import ChromaConfig
    from src.search.reranker import RemoteReranker
    from src.search.search import SearchService
    from system.database.db_respository import (
        DatabaseConfig,
        DatabaseManager,
        DocumentMetadataRepository,
        DocumentRelationRepository,
    )
    from src.agent.tools import LegalAgentTools
    from src.api.remote_client import RemoteAPIClient
    from src.api.nvidia_api_client import OpenAICompatibleClient

    logger.info("[Initializing Workflow Dependencies]")
    
    COLLECTION_NAME = "legal_documents"
    CHROMA_DIR = "chroma_db"
    
    try:
        # Init Chroma
        chroma_store = ChromaStore(ChromaConfig(
            collection_name=COLLECTION_NAME,
            is_persist=True,
            persist_directory=CHROMA_DIR,
            distance_metric='cosine'
        ))
        
        # Init API
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
        
        logger.info("✓ All workflow dependencies initialized")
        
        return {
            "llm": llm,
            "db_client": db_manager,
            "retriever": retriever,
            "doc_retriever": retriever,
        }
    except Exception as exc:
        logger.error("Failed to initialize workflow dependencies: %s", exc, exc_info=True)
        raise


def run_workflow_query(question: str, deps: dict):
    """Chạy workflow LangGraph cho một câu hỏi."""
    from src.agent.graph import build_graph
    from src.agent.state import initial_state
    
    logger.info("=" * 70)
    logger.info("Question: %s", question)
    logger.info("=" * 70)
    
    try:
        # Build graph
        logger.info("[1] Building graph...")
        graph = build_graph(
            llm=deps["llm"],
            db_client=deps["db_client"],
            retriever=deps["retriever"],
            doc_retriever=deps["doc_retriever"],
        )
        logger.info("✓ Graph built successfully")
        
        # Initialize state
        logger.info("[2] Initializing state...")
        initial = initial_state(question)
        logger.info("✓ Initial state created")
        
        # Run workflow
        logger.info("[3] Running workflow...")
        result = graph.invoke(initial)
        logger.info("✓ Workflow completed")
        
        # Display results
        logger.info("[4] WORKFLOW RESULTS:")
        logger.info("-" * 70)
        
        if result.get("answer"):
            logger.info("ANSWER:\n%s", result['answer'])
        else:
            logger.info("ANSWER: (None)")
        
        if result.get("sub_questions"):
            logger.info("SUB-QUESTIONS: %d", len(result['sub_questions']))
            for i, sq in enumerate(result["sub_questions"], 1):
                logger.info("  %d. %s (intent=%s)", i, sq.query, sq.intent)
        
        return result
        
    except Exception as exc:
        logger.error("Workflow failed: %s", exc, exc_info=True)
        return None


def handle_workflow_interactive(workflow_deps=None):
    """Mode tương tác: nhập câu hỏi và workflow trả lời."""
    logger.info("=" * 70)
    logger.info("WORKFLOW INTERACTIVE MODE")
    logger.info("=" * 70)
    logger.info("(Nhập 'quit', 'exit', hoặc 'q' để thoát)\n")
    
    if workflow_deps is None:
        try:
            workflow_deps = setup_workflow_dependencies()
        except Exception as exc:
            logger.error("Failed to setup dependencies: %s", exc)
            return
    
    while True:
        try:
            question = input("\n📝 Câu hỏi của bạn: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                logger.info("\nTạm biệt! 👋\n")
                break
            
            if not question:
                logger.warning("⚠ Vui lòng nhập câu hỏi.\n")
                continue
            
            # Run workflow
            result = run_workflow_query(question, workflow_deps)
            
            if result is None:
                logger.error("❌ Workflow thất bại. Vui lòng thử lại.\n")
                continue
            
            logger.info("\n")
        
        except KeyboardInterrupt:
            logger.info("\n\nTạm biệt! 👋\n")
            break
        except Exception as exc:
            logger.error("❌ Lỗi: %s", exc, exc_info=True)
            continue


def main():
    """Interactive CLI with shared dependencies."""
    logger.info("=" * 70)
    logger.info("Legal Document Search System")
    logger.info("=" * 70)

    # Setup shared dependencies once
    logger.info("\n[Initializing shared dependencies...]")
    search_service = None
    api_client = None
    workflow_deps = None
    
    try:
        from src.api import RemoteAPIClient
        
        # Initialize search service (reusable for modes 3, 4, 5)
        search_service = build_search_service(
            use_remote_embedding=True,
            use_rerank=True,
            use_remote_rerank=True,
            app_config=APP_CONFIG,
        )
        logger.info("✓ Search service initialized\n")
        
        # Initialize API client (reusable for RAG mode)
        api_client = RemoteAPIClient()
        logger.info("✓ API client initialized\n")
        
    except Exception as exc:
        logger.warning("⚠ Could not pre-initialize search service: %s", exc)
        logger.info("  (Will initialize on-demand for each search)\n")

    while True:
        logger.info("")
        logger.info("Options:")
        logger.info("  1. Index document with local embedding")
        logger.info("  2. Index document with remote embedding")
        logger.info("  3. Search with local embedding/local rerank")
        logger.info("  4. Search with optional remote embedding + remote rerank")
        logger.info("  5. Full RAG")
        logger.info("  6. Index all DOCXs in a folder")
        logger.info("  7. Index all DOCXs in a folder with remote embedding")
        logger.info("  0. Exit")

        choice = input("\nChoose option (0-7): ").strip()

        if choice == "0":
            logger.info("Goodbye!")
            break

        if choice == "1":
            handle_index_local()
        elif choice == "2":
            handle_index_remote()
        elif choice == "3":
            handle_search_local()
        elif choice == "4":
            handle_search_remote_rerank()
        elif choice == "5":
            handle_rag()
        elif choice == "6":
            handle_index_folder()
        elif choice == "7":
            handle_index_folder_remote()
        else:
            logger.warning("Invalid option.")


if __name__ == "__main__":
    main()
