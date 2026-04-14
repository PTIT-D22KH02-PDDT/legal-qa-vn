ROOT_DIR = Path(__file__).resolve().parents[2]
CHROMA_DB_DIR = ROOT_DIR / "chroma_db"
COLLECTION_NAME = "legal_documents"
EMBEDDING_MODEL_DIR = ROOT_DIR / "models" / "vietnamese-embedding"
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
    
    # 3. Khởi tạo reranker
    print("Initializing reranker...")
    reranker = VietnameseReranker(
        model_name="AITeamVN/Vietnamese_Reranker",
        max_length=512,
        batch_size=32
    )
    try:
        reranker.startup()
        print("Reranker loaded successfully")
    except Exception as e:
        print(f"Reranker failed to load: {e}")
        print("   Will continue without reranking")
        reranker = None
    
    # 4. Khởi tạo RetrievalService với reranker
    retrieval_service = RetrievalService(
        chroma_store=chroma_store,
        embedding_model=embedding_model,
        collection_name=COLLECTION_NAME,
        reranker=reranker
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
    print(f"CHÚ Ý: Sẽ chỉ retrieve các node loại: {', '.join(LEAF_NODE_TYPES)}")
    print("(Bỏ qua Phần, Chương, Mục - chỉ lấy Điều, Khoản, Điểm)")
    if reranker and reranker.is_initialized:
        print("Reranking ENABLED - Kết quả sẽ được sắp xếp lại theo độ liên quan")
    else:
        print("Reranking DISABLED - Kết quả sắp xếp theo embedding score")
    print("=" * 80)
        
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
            if result.score_rerank is not None:
                print(f"   - Rerank Score: {result.score_rerank:.4f}")
            else:
                print(f"   - Embedding Distance: {result.distance:.4f}")
            print(f"   - Noi dung: {result.text[:150]}")
            if len(result.text) > 150:
                print("      ...")
            print()


def debug_retrieve():
    """Debug retrieve: test với/không filter để xem vấn đề"""
    from src.core.vector_store.chroma_store import ChromaStore
    from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
    from src.schemas import ChromaConfig
    
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
    
    query = "tài sản thế chấp"
    print(f"Query: {query}\n")
    
    # Test 1: Lấy 5 documents ngẫu nhiên từ DB
    print("=" * 80)
    print("TEST 1: Kiểm tra metadata từ DB")
    print("=" * 80)
    try:
        results = chroma_store.collection.get(limit=5)
        for i, (id, doc, metadata) in enumerate(zip(
            results['ids'], results['documents'], results['metadatas']
        ), 1):
            print(f"{i}. ID: {id}")
            print(f"   Metadata keys: {list(metadata.keys())}")
            print(f"   section_type: {metadata.get('section_type', 'NOT FOUND')}")
            print()
    except Exception as e:
        print(f"LỖI: {e}\n")
    
    # Test 2: Retrieve KHÔNG filter
    print("=" * 80)
    print("TEST 2: Retrieve KHÔNG filter (xem tất cả kết quả)")
    print("=" * 80)
    try:
        results = retrieval_service.retrieve_by_query_string(
            query=query,
            top_k=5,
            filter_by_type=None  # KHÔNG filter
        )
        print(f"Tìm được {len(results)} kết quả:\n")
        for i, result in enumerate(results[:5], 1):
            print(f"{i}. {result.section_display}")
            if result.score_rerank is not None:
                print(f"   Rerank Score: {result.score_rerank:.4f}")
            else:
                print(f"   Distance: {result.distance:.4f}")
            print(f"   Type: {result.section_type}")
            print()
    except Exception as e:
        print(f"LỖI: {e}\n")
    
    # Test 3: Retrieve CÓ filter
    print("=" * 80)
    print("TEST 3: Retrieve CÓ filter (leaf nodes only)")
    print("=" * 80)
    try:
        results = retrieval_service.retrieve_by_query_string(
            query=query,
            top_k=5,
            filter_by_type=LEAF_NODE_TYPES
        )
        print(f"Tìm được {len(results)} kết quả:\n")
        if results:
            for i, result in enumerate(results[:5], 1):
                print(f"{i}. {result.section_display}")
                if result.score_rerank is not None:
                    print(f"   Rerank Score: {result.score_rerank:.4f}")
                else:
                    print(f"   Distance: {result.distance:.4f}")
                print(f"   Type: {result.section_type}")
                print()
        else:
            print("⚠️  KÔ CÓ KẾT QUẢ - Filter có thể đã bỏ hết!\n")
    except Exception as e:
        print(f"LỖI: {e}\n")


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
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "debug":
            debug_collection()
        elif sys.argv[1] == "debug_retrieve":
            debug_retrieve()
    else:
        main()