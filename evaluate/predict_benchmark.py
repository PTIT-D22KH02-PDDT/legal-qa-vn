import json
from pathlib import Path
import re
import logging

#các hàm để chạy option 5 bên main.py
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent

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

#################
def load_benchmark(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def build_question_text(item):
    question = item.get("question", "")
    answers = item.get("answers", "")
    instruction = item.get("instruction", "")
    return f"{instruction}\nCâu hỏi: {question}\n{answers}"

# lấy ra predict đúng từ answer của llm
def extract_predict(raw_answer: str) -> str:
    # Ưu tiên lấy đáp án là 1 ký tự duy nhất trên dòng
    match = re.search(r'^[ \t]*([ABCD])[ \t]*$', raw_answer, re.MULTILINE)
    if match:
        return match.group(1)
    # Nếu không có, lấy ký tự đầu tiên là A/B/C/D xuất hiện trong 10 ký tự đầu
    match = re.search(r'[ABCD]', raw_answer[:10])
    if match:
        return match.group(0)
    # Nếu vẫn không có, fallback: lấy ký tự đầu tiên
    return raw_answer.strip()[:1]

def main():
    from src.api import RemoteAPIClient
    from src.rag import RAGService

    benchmark_path = PROJECT_ROOT / "data" / "benchmark" / "loc_1_4_100.jsonl"
    output_path = PROJECT_ROOT / "data" / "evaluate" / "rag_predict_result_1_4.json"

    if not benchmark_path.exists():
        logger.error(f"Lỗi: Không tìm thấy file tại {benchmark_path}")
        return
    
    #mặc định luôn k retrieve =10, k rerank=5
    search_service = build_search_service(
        use_remote_embedding=True,
        use_rerank=True,
        use_remote_rerank=True,
    )
    api_client = RemoteAPIClient()
    rag_service = RAGService(
        search_service=search_service,
        api_client=api_client,
        top_k_retrieve=10,
        top_k_rerank=5,
        use_rerank=True,
    )

    results = []
    items = list(load_benchmark(benchmark_path))
    logger.info(f"Đánh giá {len(items)} câu hỏi...")

    for idx, item in enumerate(items, 1):
        question_text = build_question_text(item)
        logger.info(f"[{idx}/{len(items)}] Đang xử lý: {item.get('question', '')[:50]}...")
        try:
            rag_result = rag_service.answer(query=question_text)
            raw_answer = rag_result.answer
            
            predict = extract_predict(raw_answer)

            logger.info(predict)
            logger.info(raw_answer)

            log = {
                "question": question_text,
                "predict": extract_predict(raw_answer),  
                "groundtruth": item.get("ground_truth"),
                "raw_answer_rag": raw_answer,
            }
            results.append(log)
        except Exception as e:
            logger.error(f"Lỗi tại câu {idx}: {e}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu kết quả vào {output_path}")

if __name__ == "__main__":
    main()