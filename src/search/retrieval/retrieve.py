from typing import List, Optional, Dict, Any
from src.indexing.vector_store import (
    ChromaQueryRequest,
    ChromaQueryResult,
    ChromaConfig,
)
from src.indexing.embedding import (
    decode_section_id,
    EmbeddingRequest,
    EmbeddingResult,
    create_embedding_request,
)
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from .schemas import RetrieveQuestionRequest, RetrieveResult
from .config import RetrievalConfig


_config = RetrievalConfig.get_default_config()
_store_params = _config.get_store_params()

COLLECTION_NAME = _store_params['collection_name']
CHROMA_DB_DIR = _store_params['persist_directory']
EMBEDDING_MODEL_DIR = _config.get_embedding_params()['model_dir']


class RetrievalService:
    """Service chính để retrieve điều khoản từ ChromaDB"""
    
    def __init__(
        self, 
        chroma_store,
        embedding_model,
        collection_name: str = "legal_documents"
    ):
        """
        Args:
            chroma_store: ChromaStore instance
            embedding_model: OnnxEmbeddingModel hoặc EmbeddingModel instance
            collection_name: Tên collection trong ChromaDB
        """
        self.chroma_store = chroma_store
        self.embedding_model = embedding_model
        self.collection_name = collection_name

    def _embed_query(self, query: str) -> List[float]:
        """Embed query thành vector"""
        embedding_request = create_embedding_request(query)
        result = self.embedding_model.embed([embedding_request])
        if not result:
            raise ValueError(f"Failed to embed query: {query}")
        return result[0].vector

    def _process_chroma_results(
        self,
        chroma_results: List[ChromaQueryResult]
    ) -> List[RetrieveResult]:
        """Xử lý kết quả từ ChromaDB thành RetrieveResult"""
        results = []
        
        for chroma_result in chroma_results:
            section_id = chroma_result.chunk_id
            
            # Trả về distance từ ChromaDB
            distance = chroma_result.distance
            
            section_metadata = decode_section_id(section_id)
            section_display = section_metadata.display()
            section_type = section_metadata.get_section_type()
            
            result = RetrieveResult(
                section_id=section_id,
                section_display=section_display,
                text=chroma_result.text,
                distance=distance,
                section_type=section_type,
                metadata=chroma_result.metadata
            )
            results.append(result)
        
        return results

    def retrieve(
        self,
        request: RetrieveQuestionRequest
    ) -> List[RetrieveResult]:
        """
        Retrieve điều khoản từ ChromaDB dựa trên query
        
        Args:
            request: RetrieveQuestionRequest chứa query và các filter
            
        Returns:
            List các RetrieveResult được sắp xếp theo similarity score (giảm dần)
        """
        # 1. Embed query
        query_vector = self._embed_query(request.query)
        
        # 2. Build filter metadata nếu cần
        filter_metadata = self._build_filter_metadata(request.filter_by_type)
        
        # 3. Query ChromaDB
        chroma_request = ChromaQueryRequest(
            query_vector=query_vector,
            top_k=request.top_k,
            filter=filter_metadata
        )
        chroma_results = self.chroma_store.query(chroma_request)
        
        # 4. Process results
        results = self._process_chroma_results(chroma_results)
        
        # 5. Filter theo score threshold nếu cần
        if request.score_threshold:
            results = [
                r for r in results 
                if r.distance <= request.score_threshold
            ]
        
        # 6. Sort theo distance (tăng dần - distance nhỏ nhất sẽ ở trên)
        results.sort(key=lambda r: r.distance)
        
        return results

    def retrieve_by_query_string(
        self,
        query: str,
        top_k: int = 5,
        filter_by_type: Optional[List[str]] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrieveResult]:
        """
        Helper method để retrieve với query string đơn giản
        
        Args:
            query: Câu truy vấn
            top_k: Số lượng kết quả
            filter_by_type: Lọc theo loại
            score_threshold: Ngưỡng score
            
        Returns:
            List các RetrieveResult
        """
        request = RetrieveQuestionRequest(
            query=query,
            top_k=top_k,
            filter_by_type=filter_by_type,
            score_threshold=score_threshold
        )
        return self.retrieve(request)

    def retrieve_by_section_type(
        self,
        query: str,
        section_type: str,
        top_k: int = 5,
        score_threshold: Optional[float] = None
    ) -> List[RetrieveResult]:
        """
        Retrieve với lọc theo một loại section cụ thể
        
        Args:
            query: Câu truy vấn
            section_type: Loại section (dieu, khoan, diem, etc)
            top_k: Số lượng kết quả
            score_threshold: Ngưỡng score
            
        Returns:
            List các RetrieveResult
        """
        return self.retrieve_by_query_string(
            query=query,
            top_k=top_k,
            filter_by_type=[section_type],
            score_threshold=score_threshold
        )


def main():
    """Interactive CLI for testing retrieval."""
    from src.indexing.vector_store.chroma_store import ChromaStore
    
    print("\n" + "=" * 80)
    print("RETRIEVAL SERVICE - Interactive Test")
    print("=" * 80 + "\n")
    
    try:
        # Initialize
        print("[*] Initializing...")
        chroma_config = ChromaConfig(
            collection_name=COLLECTION_NAME,
            persist_directory=str(CHROMA_DB_DIR),
            distance_metric="ip",
            is_persist=True
        )
        chroma_store = ChromaStore(config=chroma_config)
        embedding_model = OnnxEmbeddingModel(model_dir=str(EMBEDDING_MODEL_DIR))
        
        retrieval_service = RetrievalService(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
            collection_name=COLLECTION_NAME,
        )
        
        # Check collection
        count = chroma_store.collection.count()
        if count == 0:
            print(f"[ERROR] Collection '{COLLECTION_NAME}' is empty!")
            return
        
        print(f"[OK] Collection '{COLLECTION_NAME}' has {count} documents\n")
        
        while True:
            try:
                query = input("Query (or 'exit' to quit): ").strip()
                if query.lower() in ['exit', 'quit', 'q']:
                    break
                if not query:
                    continue
                
                top_k_input = input("Top-k (default 5): ").strip()
                top_k = int(top_k_input) if top_k_input else 5
                
                if top_k < 1 or top_k > 100:
                    print("Top-k must be between 1 and 100\n")
                    continue
                
                print(f"\nSearching for: '{query}' (top-{top_k})...\n")
                results = retrieval_service.retrieve_by_query_string(query=query, top_k=top_k)
                
                if not results:
                    print("No results found\n")
                else:
                    for i, result in enumerate(results, 1):
                        print(f"{i}. {result.section_display}")
                        print(f"   ID: {result.section_id}")
                        print(f"   Type: {result.section_type}")
                        print(f"   Distance: {result.distance:.4f}")
                        print(f"   Text: {result.text[:100]}...\n")
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}\n")
    
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()