"""
Search Pipeline - retrieval + re-ranking.

Pipeline kết hợp vector search (retrieval) với cross-encoder re-ranking
Hỗ trợ cả local models và remote API
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

from .config import PipelineConfig
from .retrieval import RetrievalService, RetrieveQuestionRequest, RetrieveResult
from .rerank import CrossEncoderReranker, RankedResult
import sys

logger = logging.getLogger(__name__)


class SearchPipeline:
    """
    Pipeline orchestrate vector search retrieval + cross-encoder re-ranking.
    
    Hỗ trợ cả local models và remote API:
    - Local embedding + local reranker (default)
    - Remote embedding + remote reranker
    - Mixed: local embedding + remote reranker, etc.
    
    Workflow:
    1. Vector search (retrieval)
    2. Cross-encoder re-ranking 
    3. Return top-k re-ranked results
    """
    
    def __init__(
        self,
        chroma_store,
        embedding_model=None,
        config_path: Optional[str] = None,
        use_remote_api: bool = False,
    ):
        """
        Khởi tạo search pipeline.
        
        Args:
            chroma_store: ChromaStore instance
            embedding_model: OnnxEmbeddingModel hoặc EmbeddingModel instance
                            Nếu None và use_remote_api=True, sẽ tạo RemoteEmbeddingModel
            config_path: Đường dẫn tới pipeline config (nếu null dùng mặc định)
            use_remote_api: Sử dụng remote embedding + reranker từ API (default: False)
        """
        from src.api import RemoteAPIClient
        from src.indexing.embedding import RemoteEmbeddingModel
        from .rerank import RemoteReranker
        
        self.config = PipelineConfig(config_path)
        self.retrieval_params = self.config.get_retrieval_params()
        self.rerank_params = self.config.get_rerank_params()
        self.reranker_params = self.config.get_reranker_params()
        self.use_remote_api = use_remote_api
        
        # Initialize embedding model
        if use_remote_api:
            if embedding_model is None:
                logger.info("Using remote embedding API")
                api_client = RemoteAPIClient()
                embedding_model = RemoteEmbeddingModel(api_client)
            self.api_client = RemoteAPIClient()
        else:
            if embedding_model is None:
                raise ValueError("embedding_model is required when use_remote_api=False")
            self.api_client = None
        
        # Initialize retrieval service
        self.retrieval_service = RetrievalService(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
        )
        
        # Initialize re-ranker nếu enabled
        if self.rerank_params['enabled']:
            if use_remote_api:
                logger.info("Using remote reranker API")
                self.reranker = RemoteReranker(self.api_client)
            else:
                self.reranker = CrossEncoderReranker(
                    model_name=self.reranker_params['model_dir'],
                    device=self.reranker_params['device'],
                    batch_size=self.reranker_params['batch_size'],
                    normalize_scores=self.reranker_params['normalize_scores'],
                    max_length=self.reranker_params['max_length'],
                )
        else:
            self.reranker = None
        
        logger.info(f"SearchPipeline initialized (use_remote_api={use_remote_api})")
    
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_by_type: Optional[List[str]] = None,
        use_rerank: Optional[bool] = None,
    ) -> List[Any]:
        """
        Tìm kiếm với retrieval + re-ranking.
        
        Args:
            query: Câu truy vấn
            top_k: Số lượng kết quả cuối cùng (mặc định từ config)
            filter_by_type: Lọc theo loại section
            use_rerank: Sử dụng re-ranking (mặc định từ config)
        
        Returns:
            List[RankedResult | RetrieveResult] - kết quả cuối cùng
        """
        if top_k is None:
            top_k = self.rerank_params['top_k']
        
        if use_rerank is None:
            use_rerank = self.rerank_params['enabled']
        
        # Step 1: Vector search (retrieval)
        print(f"\n[Step 1] Vector search: '{query}'")
        retrieval_top_k = top_k * 2 if use_rerank else top_k
        
        retrieval_results = self.retrieval_service.retrieve_by_query_string(
            query=query,
            top_k=retrieval_top_k,
            filter_by_type=filter_by_type,
        )
        
        print(f"  Retrieved {len(retrieval_results)} documents")
        
        # Step 2: Re-ranking (nếu enabled)
        if use_rerank and self.reranker and retrieval_results:
            print(f"\n[Step 2] Re-ranking with cross-encoder...")
            
            # Convert retrieval results to reranker format
            vector_search_results = {
                "ids": [r.section_id for r in retrieval_results],
                "documents": [r.text for r in retrieval_results],
                "metadatas": [r.metadata for r in retrieval_results],
                "distances": [r.distance for r in retrieval_results],
            }
            
            # Re-rank
            reranked_results = self.reranker.rerank_with_vector_search(
                query=query,
                vector_search_results=vector_search_results,
                top_k_rerank=top_k,
            )
            
            print(f"  Re-ranked: {len(reranked_results)} results")
            return reranked_results
        else:
            # Không re-rank, trả về retrieval results
            if use_rerank:
                print(f"\n[Step 2] Re-ranking: skipped (no reranker or empty results)")
            return retrieval_results[:top_k]
    
    def search_by_section_type(
        self,
        query: str,
        section_type: str,
        top_k: Optional[int] = None,
        use_rerank: Optional[bool] = None,
    ) -> List[Any]:
        """
        Tìm kiếm với lọc theo section type.
        
        Args:
            query: Câu truy vấn
            section_type: Loại section (dieu, khoan, etc)
            top_k: Số lượng kết quả
            use_rerank: Sử dụng re-ranking
        
        Returns:
            List[RankedResult | RetrieveResult]
        """
        return self.search(
            query=query,
            top_k=top_k,
            filter_by_type=[section_type],
            use_rerank=use_rerank,
        )


def main():
    """Interactive search pipeline."""
    from pathlib import Path
    
    from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
    from src.indexing.vector_store.chroma_store import ChromaStore, ChromaConfig
    
    print("="*70)
    print("SEARCH PIPELINE - LEGAL DOCUMENTS")
    print("="*70)
    
    try:
        # Load configuration
        print("\n[*] Loading configuration from search_config.yaml...")
        pipeline_config = PipelineConfig()
        vector_store_params = pipeline_config.get_vector_store_params()
        embedding_model_dir = pipeline_config.get_embedding_model_dir()
        
        CHROMA_DB_DIR = pipeline_config.chroma_db_dir
        COLLECTION_NAME = vector_store_params['collection_name']
        DISTANCE_METRIC = vector_store_params['distance_metric']
        IS_PERSIST = vector_store_params['is_persist']
        EMBEDDING_MODEL_DIR = embedding_model_dir
        
        print(f"    Collection: {COLLECTION_NAME}")
        print(f"    Distance metric: {DISTANCE_METRIC}")
        print(f"    Persist: {IS_PERSIST}")
        
        # 1. Khởi tạo ChromaStore
        print("\n[*] Initializing ChromaStore...")
        chroma_config = ChromaConfig(
            collection_name=COLLECTION_NAME,
            persist_directory=str(CHROMA_DB_DIR),
            distance_metric=DISTANCE_METRIC,
            is_persist=IS_PERSIST
        )
        chroma_store = ChromaStore(config=chroma_config)
        
        # Check collection có data không
        try:
            collection_count = chroma_store.collection.count()
            print(f"    Collection '{chroma_store.collection.name}' có {collection_count} documents")
            if collection_count == 0:
                print("[!] Warning: Collection trống! Vui lòng index dữ liệu trước.")
                return
        except Exception as e:
            print(f"[!] Error checking collection: {e}")
            return
        
        # 2. Khởi tạo embedding model
        print("\n[*] Loading embedding model...")
        print(f"    Model dir: {EMBEDDING_MODEL_DIR}")
        embedding_model = OnnxEmbeddingModel(
            model_dir=str(EMBEDDING_MODEL_DIR)
        )
        
        # 3. Khởi tạo search pipeline
        print("\n[*] Initializing search pipeline...")
        pipeline = SearchPipeline(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
        )
        print("[OK] Pipeline ready for search\n")
        
        print("="*70)
        
        while True:
            try:
                # Get query from user
                query = input("\n[?] Enter search query (or 'exit' to quit): ").strip()
                
                if query.lower() in ['exit', 'quit', 'q']:
                    print("\n[*] Exiting search pipeline...")
                    break
                
                if not query:
                    print("[!] Query cannot be empty")
                    continue
                
                # Get search parameters
                try:
                    top_k = input("[?] Number of results (default 5): ").strip()
                    top_k = int(top_k) if top_k else 5
                except ValueError:
                    top_k = 5
                
                use_rerank = input("[?] Use re-ranking? (y/n, default y): ").strip().lower()
                use_rerank = use_rerank != 'n'
                
                # Perform search
                print("\n" + "="*70)
                results = pipeline.search(
                    query=query,
                    top_k=top_k,
                    use_rerank=use_rerank,
                )
                print("="*70)
                
                # Display results
                if results:
                    print(f"\n[OK] Found {len(results)} results:\n")
                    for i, result in enumerate(results, 1):
                        print(f"{'='*70}")
                        print(f"Result #{i}")
                        print(f"{'='*70}")
                        
                        # Handle both RankedResult and RetrieveResult
                        if hasattr(result, 'section_id'):  # RetrieveResult
                            print(f"Section ID: {result.section_id}")
                            print(f"Text: {result.text[:200]}...")
                            print(f"Distance: {result.distance:.4f}")
                            if hasattr(result, 'section_type'):
                                print(f"Type: {result.section_type}")
                        else:  # RankedResult
                            print(f"Document ID: {result.ids}")
                            print(f"Text: {result.documents[:200]}...")
                            print(f"Relevance Score: {result.relevance_score:.4f}")
                            print(f"Vector Distance: {result.distances:.4f}")
                            print(f"Rank: {result.rank}")
                        
                        if hasattr(result, 'metadatas') and result.metadatas:
                            print(f"Metadata: {result.metadatas}")
                        elif hasattr(result, 'metadata') and result.metadata:
                            print(f"Metadata: {result.metadata}")
                        print()
                else:
                    print("\n[!] No results found")
            
            except KeyboardInterrupt:
                print("\n\n[*] Search interrupted by user")
                break
            except Exception as e:
                print(f"\n[ERROR] Search failed: {e}")
                import traceback
                traceback.print_exc()
    
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize pipeline: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n[*] Done!")


if __name__ == "__main__":
    main()
