from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
from pydantic import BaseModel, Field
from src.schemas import ChromaQueryRequest, ChromaQueryResult, EmbeddingRequest, EmbeddingResult
from src.core.embedding import decode_section_id
import os, sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
CHROMA_DB_DIR = ROOT_DIR / "chroma_db"
COLLECTION_NAME = "legal_documents"
EMBEDDING_MODEL_DIR = ROOT_DIR / "models" / "Vietnamese_Embedding_v2"

class RetrieveQuestionRequest(BaseModel):
    """Yêu cầu retrieve với query là điều khoản hoặc câu hỏi pháp lý"""
    query: str = Field(..., description="Câu truy vấn (ví dụ: 'điều khoản về hợp đồng')")
    top_k: int = Field(5, ge=1, le=100, description="Số lượng kết quả trả về")
    filter_by_type: Optional[List[str]] = Field(
        None, 
        description="Lọc theo loại section (dieu, khoan, diem, etc)"
    )
    score_threshold: Optional[float] = Field(
        None,
        description="Ngưỡng score tối thiểu (0-1)"
    )


@dataclass
class RetrieveResult:
    """Kết quả một section được retrieve"""
    section_id: str              # VD: "phan_5.chuong_xxv.dieu_663.khoan_1"
    section_display: str         # VD: "Khoản 1 Điều 663 Chương XXV Phần 5"
    text: str                    # Nội dung
    distance: float              # Distance từ ChromaDB
    section_type: str            # VD: "khoan", "dieu"
    metadata: Dict[str, Any]     # Metadata từ ChromaDB


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
        embedding_request = EmbeddingRequest(
            chunk_id=None,
            text=query
        )
        result = self.embedding_model.embed([embedding_request])
        if not result:
            raise ValueError(f"Failed to embed query: {query}")
        return result[0].vector

    def _extract_section_type(self, section_id: str) -> str:
        """
        Lấy loại section từ section_id
        VD: "phan_5.chuong_xxv.dieu_663.khoan_1" -> "khoan"
        """
        parts = section_id.split('.')
        if not parts:
            return ""
        last_part = parts[-1]
        type_name = last_part.split('_')[0]
        return type_name

    def _build_filter_metadata(self, filter_by_type: Optional[List[str]]) -> Optional[Dict[str, Any]]:
        """Xây dựng filter metadata cho ChromaDB"""
        if not filter_by_type:
            return None
        
        # ChromaDB sử dụng where clauses để filter
        # VD: {"section_type": {"$in": ["dieu", "khoan"]}}
        return {
            "section_type": {"$in": filter_by_type}
        }

    def _process_chroma_results(
        self,
        chroma_results: List[ChromaQueryResult]
    ) -> List[RetrieveResult]:
        """Xử lý kết quả từ ChromaDB thành RetrieveResult"""
        results = []
        
        for chroma_result in chroma_results:
            section_id = chroma_result.chunk_id
            section_type = self._extract_section_type(section_id)
            
            # Trả về distance từ ChromaDB
            distance = chroma_result.distance
            
            result = RetrieveResult(
                section_id=section_id,
                section_display=decode_section_id(section_id),
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
                if r.distance >= request.score_threshold
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
    """
    Ứng dụng interactive để retrieve điều khoản pháp lý
    """
    from src.core.vector_store.chroma_store import ChromaStore
    from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
    from src.schemas import ChromaConfig
    
    # 1. Khởi tạo ChromaStore với collection đã được indexing
    chroma_config = ChromaConfig(
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DB_DIR),
        distance_metric="ip", 
        is_persist=True
    )
    chroma_store = ChromaStore(config=chroma_config)
    
    # 2. Khởi tạo embedding model
    embedding_model = OnnxEmbeddingModel(
        model_dir=str(EMBEDDING_MODEL_DIR)
    )
    
    # 3. Khởi tạo RetrievalService
    retrieval_service = RetrievalService(
        chroma_store=chroma_store,
        embedding_model=embedding_model,
        collection_name=COLLECTION_NAME,
    )
    
    # Kiểm tra collection có dữ liệu không
    try:
        collection_count = chroma_store.collection.count()
        print(f"Collection '{chroma_store.collection.name}' co {collection_count} documents")
        if collection_count == 0:
            print("CANH BAO: Collection trong! Vui long index du lieu truoc.")
            return
    except Exception as e:
        print(f"LỖI khi kiem tra collection: {e}")
        return
    
    print("\n" + "=" * 80)
        
    while True:        
        # Nhập query
        query = input("\nNhap truy van (hoac 'thoat' de dung): ").strip()
        if query.lower() in ['thoat', 'exit', 'quit', 'q']:
            break
        
        if not query:
            print("Truy van khong duoc de trong!")
            continue
        
        # Nhập số lượng kết quả
        try:
            top_k_input = input("Nhap top_k (mac dinh 5): ").strip()
            top_k = int(top_k_input) if top_k_input else 5
            if top_k < 1 or top_k > 100:
                print("So luong phai tu 1 den 100!")
                continue
        except ValueError:
            print("Vui long nhap so nguyen hop le!")
            continue
        
        # Thực hiện retrieve
        print(f"\nDang tim kiem...")
        try:
            results = retrieval_service.retrieve_by_query_string(
                query=query,
                top_k=top_k,
            )
        except Exception as e:
            print(f"LỖI khi retrieve: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        # Hiển thị kết quả
        if not results:
            print("CANH BAO: Khong tim thay ket qua phu hop!")
            print(f"   Dieu nay co the do:")
            print(f"   - Query khong match voi bat ky section nao trong DB")
            print(f"   - Collection chua duoc index dung cach")
            print(f"   - Metadata khong duoc luu trong ChromaDB")
            continue
        
        print(f"\nTim thay {len(results)} ket qua:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.section_display}")
            print(f"   - Section ID: {result.section_id}")
            print(f"   - Loai: {result.section_type}")
            print(f"   - Distance: {result.distance:.4f}")
            print(f"   - Noi dung: {result.text[:150]}")
            if len(result.text) > 150:
                print("      ...")
            print()


def debug_collection():
    """Kiểm tra chi tiết dữ liệu trong ChromaDB"""
    from src.core.vector_store.chroma_store import ChromaStore
    from src.schemas import ChromaConfig
    
    chroma_config = ChromaConfig(
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DB_DIR),
        distance_metric="ip",
    )
    chroma_store = ChromaStore(config=chroma_config)
    
    # Lấy một số documents từ collection
    try:
        count = chroma_store.collection.count()
        print(f"Collection '{chroma_store.collection.name}' co {count} documents\n")
        
        if count == 0:
            print("LỖI: Collection trống!")
            return
        
        # Lấy 5 documents đầu
        results = chroma_store.collection.get(limit=5)
        print("5 documents dau tien:\n")
        for i, (id, doc, metadata) in enumerate(zip(
            results['ids'], results['documents'], results['metadatas']
        ), 1):
            print(f"{i}. ID: {id}")
            print(f"   Text: {doc[:80]}...")
            print(f"   Metadata: {metadata}")
            print()
    except Exception as e:
        print(f"LỖI: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        debug_collection()
    else:
        main()

