"""
Main entry point - hỗ trợ indexing + search với local hoặc remote models
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """
    Interactive CLI để chọn chế độ indexing hoặc search
    """
    logger.info("=" * 70)
    logger.info("Legal Document Search System")
    logger.info("Support: Local models + Remote API (ngrok)")
    logger.info("=" * 70)
    
    while True:
        logger.info("\nOptions:")
        logger.info("  1. Index document (local embedding)")
        logger.info("  2. Index document (remote embedding API)")
        logger.info("  3. Search documents (local models)")
        logger.info("  4. Search documents (remote APIs)")
        logger.info("  5. Full RAG (search + generate)")
        logger.info("  0. Exit")
        
        choice = input("\nChoose option (0-5): ").strip()
        
        if choice == "0":
            logger.info("Goodbye!")
            break
        
        elif choice == "1":
            handle_index_local()
        
        elif choice == "2":
            handle_index_remote()
        
        elif choice == "3":
            handle_search_local()
        
        elif choice == "4":
            handle_search_remote()
        
        elif choice == "5":
            handle_rag_pipeline()
        
        else:
            logger.warning("Invalid option")


def handle_index_local():
    """Index document với local embedding model"""
    from src.indexing.indexing import process_document
    from src.indexing.config import IndexingConfig
    
    logger.info("\n[LOCAL INDEXING]")
    
    file_path = input("Enter file path: ").strip()
    if not file_path:
        logger.warning("No file path provided")
        return
    
    try:
        result = process_document(
            file_path=file_path,
            config=IndexingConfig.get_default_config(),
            use_remote_api=False
        )
        
        logger.info("\nIndexing Result:")
        logger.info(f"  Status: {'SUCCESS' if result['success'] else 'FAILED'}")
        logger.info(f"  Message: {result['message']}")
        if result['success']:
            logger.info(f"  Collection: {result['collection']}")
            logger.info(f"  Chunks: {result['chunks_count']}")
            logger.info(f"  Embeddings: {result['embeddings_count']}")
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


def handle_index_remote():
    """Index document với remote embedding API"""
    from src.indexing.indexing import process_document
    from src.indexing.config import IndexingConfig
    
    logger.info("\n[REMOTE INDEXING]")
    
    file_path = input("Enter file path: ").strip()
    if not file_path:
        logger.warning("No file path provided")
        return
    
    try:
        result = process_document(
            file_path=file_path,
            config=IndexingConfig.get_default_config(),
            use_remote_api=True  # Sử dụng remote API từ .env
        )
        
        logger.info("\nIndexing Result:")
        logger.info(f"  Status: {'SUCCESS' if result['success'] else 'FAILED'}")
        logger.info(f"  Message: {result['message']}")
        if result['success']:
            logger.info(f"  Collection: {result['collection']}")
            logger.info(f"  Chunks: {result['chunks_count']}")
            logger.info(f"  Embeddings: {result['embeddings_count']}")
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


def handle_search_local():
    """Search với local models (embedding + reranker)"""
    from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
    from src.indexing.vector_store.chroma_store import ChromaStore, ChromaConfig
    from src.search.pipeline import SearchPipeline
    from src.search.config import PipelineConfig
    
    logger.info("\n[LOCAL SEARCH]")
    
    query = input("Enter query: ").strip()
    if not query:
        logger.warning("No query provided")
        return
    
    try:
        # Setup
        pipeline_config = PipelineConfig()
        chroma_config = ChromaConfig(
            collection_name=pipeline_config.get_vector_store_params()['collection_name'],
            persist_directory=str(pipeline_config.chroma_db_dir),
            is_persist=True
        )
        chroma_store = ChromaStore(config=chroma_config)
        
        embedding_model = OnnxEmbeddingModel(
            model_dir=pipeline_config.get_embedding_model_dir()
        )
        
        # Create pipeline
        search_pipeline = SearchPipeline(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
            use_remote_api=False
        )
        
        # Search
        top_k = int(input("Top-k results (default 5): ").strip() or "5")
        results = search_pipeline.search(query, top_k=top_k)
        
        logger.info(f"\nFound {len(results)} results:")
        for i, result in enumerate(results, 1):
            logger.info(f"\n[{i}] {result}")
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


def handle_search_remote():
    """Search với remote APIs (embedding + reranker)"""
    from src.indexing.vector_store.chroma_store import ChromaStore, ChromaConfig
    from src.search.pipeline import SearchPipeline
    from src.search.config import PipelineConfig
    
    logger.info("\n[REMOTE SEARCH]")
    
    query = input("Enter query: ").strip()
    if not query:
        logger.warning("No query provided")
        return
    
    try:
        # Setup
        pipeline_config = PipelineConfig()
        chroma_config = ChromaConfig(
            collection_name=pipeline_config.get_vector_store_params()['collection_name'],
            persist_directory=str(pipeline_config.chroma_db_dir),
            is_persist=True,
            distance_metric='ip'
        )
        chroma_store = ChromaStore(config=chroma_config)
        
        # Create pipeline (remote APIs - must use remote embedding to match indexed embeddings)
        logger.info("Using remote embedding API...")
        search_pipeline = SearchPipeline(
            chroma_store=chroma_store,
            embedding_model=None,  # Use remote embedding
            use_remote_api=True
        )
        
        # Search
        top_k = int(input("Top-k results (default 5): ").strip() or "5")
        results = search_pipeline.search(query, top_k=top_k)
        
        logger.info(f"\nFound {len(results)} results:")
        for i, result in enumerate(results, 1):
            logger.info(f"\n[{i}] {result}")
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


def handle_rag_pipeline():
    """Full RAG: search + generate answer"""
    from src.indexing.vector_store.chroma_store import ChromaStore, ChromaConfig
    from src.search.pipeline import SearchPipeline
    from src.search.config import PipelineConfig
    from src.api import RemoteAPIClient
    from src.generate import GenerateService
    
    logger.info("\n[RAG PIPELINE]")
    
    query = input("Enter question: ").strip()
    if not query:
        logger.warning("No query provided")
        return
    
    try:
        # Setup search (using remote embedding to match indexed embeddings)
        pipeline_config = PipelineConfig()
        chroma_config = ChromaConfig(
            collection_name=pipeline_config.get_vector_store_params()['collection_name'],
            persist_directory=str(pipeline_config.chroma_db_dir),
            is_persist=True,
            distance_metric='ip'
        )
        chroma_store = ChromaStore(config=chroma_config)
        
        # Use remote embedding API for search (must match indexed embeddings from mode 2)
        logger.info("Using remote embedding API...")
        search_pipeline = SearchPipeline(
            chroma_store=chroma_store,
            embedding_model=None,  # Use remote embedding
            use_remote_api=True
        )
        
        # Setup generate (remote)
        api_client = RemoteAPIClient()
        generate_service = GenerateService(api_client)
        
        # Step 1: Search
        logger.info(f"\n[Step 1] Searching for relevant documents...")
        search_results = search_pipeline.search(query, top_k=3)
        logger.info(f"  Found {len(search_results)} results")
        
        if not search_results:
            logger.warning("No documents found")
            return
        
        # Extract context - get document text only
        context_parts = []
        for result in search_results:
            if isinstance(result, dict):
                # Result is dict format
                if 'document' in result:
                    context_parts.append(result['document'])
                elif 'text' in result:
                    context_parts.append(result['text'])
            else:
                # Result is object
                if hasattr(result, 'text'):
                    context_parts.append(result.text)
                elif hasattr(result, 'document'):
                    context_parts.append(result.document)
        
        context = "\n\n---\n\n".join(context_parts)
        
        # Step 2: Generate answer
        logger.info(f"\n[Step 2] Generating answer...")
        answer = generate_service.generate_answer(
            query=query,
            context=context,
            max_length=300,
            temperature=0.5
        )
        
        logger.info(f"\n[Final Answer]")
        logger.info(f"Question: {query}")
        logger.info(f"Answer: {answer}")
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    main()

