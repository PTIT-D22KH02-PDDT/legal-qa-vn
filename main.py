import logging
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "search_config.yaml"


def load_config(config_path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    """Load runtime config from YAML."""
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_project_path(value: str | None) -> str | None:
    """Resolve relative paths from project root."""
    if value is None:
        return None

    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


APP_CONFIG = load_config()


def build_chroma_store(app_config: dict[str, Any] | None = None):
    """Build ChromaStore."""
    from src.indexing.vector_store import ChromaConfig
    from src.indexing.vector_store.chroma_store import ChromaStore

    config_data = (app_config or APP_CONFIG)["vector_store"]
    config = ChromaConfig(
        collection_name=config_data["collection_name"],
        persist_directory=resolve_project_path(config_data.get("persist_directory")),
        distance_metric=config_data["distance_metric"],
        is_persist=config_data["is_persist"],
    )

    return ChromaStore(config=config)


def build_local_embedding_model(app_config: dict[str, Any] | None = None):
    """Build local ONNX embedding model."""
    from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel

    config_data = (app_config or APP_CONFIG)["embedding"]
    return OnnxEmbeddingModel(
        model_dir=resolve_project_path(config_data["model_dir"]),
        pooling=config_data["pooling"],
        max_length=config_data["max_length"],
        normalize=config_data["normalize"],
        onnx_path=resolve_project_path(config_data.get("onnx_path")),
    )


def build_remote_embedding_model(api_client):
    """Build remote embedding model."""
    from src.indexing.embedding import RemoteEmbeddingModel

    return RemoteEmbeddingModel(api_client)


def build_local_reranker(app_config: dict[str, Any] | None = None):
    """Build local cross-encoder reranker."""
    from src.search import CrossEncoderReranker

    config_data = (app_config or APP_CONFIG)["reranker"]
    return CrossEncoderReranker(
        model_name=config_data["model_dir"],
        max_length=config_data["max_length"],
        device=config_data.get("device"),
        batch_size=config_data["batch_size"],
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
    app_config: dict[str, Any] | None = None,
):
    """Build SearchService from selected runtime options."""
    from src.api import RemoteAPIClient
    from src.search import SearchService

    app_config = app_config or APP_CONFIG
    chroma_store = build_chroma_store(app_config)

    api_client = RemoteAPIClient() if (use_remote_embedding or use_remote_rerank) else None

    if use_remote_embedding:
        embedding_model = build_remote_embedding_model(api_client)
    else:
        embedding_model = build_local_embedding_model(app_config)

    reranker = None

    if use_rerank:
        if use_remote_rerank:
            if api_client is None:
                api_client = RemoteAPIClient()
            reranker = build_remote_reranker(api_client)
        else:
            reranker = build_local_reranker(app_config)

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

        if result.distance is not None:
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
            config_path=CONFIG_PATH,
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
            config_path=CONFIG_PATH,
        )

        logger.info("Indexing result: %s", result)

    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)


def handle_search_local():
    """Search using local embedding and optional local reranker."""
    logger.info("[LOCAL SEARCH]")

    query = input("Enter query: ").strip()
    if not query:
        logger.warning("No query provided.")
        return

    search_config = APP_CONFIG["search"]["local"]
    top_k_retrieve = search_config["top_k_retrieve"]
    top_k_rerank = search_config["top_k_rerank"]
    use_rerank = search_config["use_rerank"]

    try:
        search_service = build_search_service(
            use_remote_embedding=False,
            use_rerank=use_rerank,
            use_remote_rerank=False,
            app_config=APP_CONFIG,
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


def handle_search_remote_rerank():
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

    search_config = APP_CONFIG["search"]["remote"]
    top_k_retrieve = search_config["top_k_retrieve"]
    top_k_rerank = search_config["top_k_rerank"]
    use_remote_embedding = search_config["use_remote_embedding"]
    use_rerank = search_config["use_rerank"]
    use_remote_rerank = search_config["use_remote_rerank"]

    try:
        search_service = build_search_service(
            use_remote_embedding=use_remote_embedding,
            use_rerank=use_rerank,
            use_remote_rerank=use_remote_rerank,
            app_config=APP_CONFIG,
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


def handle_rag():
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

    rag_config = APP_CONFIG["rag"]
    top_k_retrieve = rag_config["top_k_retrieve"]
    top_k_rerank = rag_config["top_k_rerank"]
    use_rerank = rag_config["use_rerank"]
    use_remote_embedding = rag_config["use_remote_embedding"]
    use_remote_rerank = rag_config["use_remote_rerank"]

    try:
        search_service = build_search_service(
            use_remote_embedding=use_remote_embedding,
            use_rerank=use_rerank,
            use_remote_rerank=use_remote_rerank,
            app_config=APP_CONFIG,
        )

        api_client = RemoteAPIClient()

        rag_service = RAGService(
            search_service=search_service,
            api_client=api_client,
            top_k_retrieve=top_k_retrieve,
            top_k_rerank=top_k_rerank,
            use_rerank=use_rerank,
            prompt_template_path=resolve_project_path(rag_config["prompt_template_path"]),
            max_context_length=rag_config["max_context_length"],
            max_answer_length=rag_config["max_answer_length"],
            temperature=rag_config["temperature"],
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


def main():
    """Interactive CLI."""
    logger.info("=" * 70)
    logger.info("Legal Document Search System")
    logger.info("=" * 70)

    while True:
        logger.info("")
        logger.info("Options:")
        logger.info("  1. Index document with local embedding")
        logger.info("  2. Index document with remote embedding")
        logger.info("  3. Search with local embedding/local rerank")
        logger.info("  4. Search with optional remote embedding + remote rerank")
        logger.info("  5. Full RAG")
        logger.info("  0. Exit")

        choice = input("\nChoose option (0-5): ").strip()

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
        else:
            logger.warning("Invalid option.")


if __name__ == "__main__":
    main()
