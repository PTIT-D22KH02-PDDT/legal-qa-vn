from pathlib import Path
from tqdm import tqdm
from tkinter import Tk, filedialog


def select_file_dialog() -> str:
    """
    Mở tkinter dialog để chọn file PDF/DOCX.
    
    Returns:
        str: Đường dẫn file được chọn
        
    Raises:
        ValueError: Nếu không chọn file
    """
    root = Tk()
    root.withdraw()  # Ẩn window chính
    root.attributes('-topmost', True)  # Đặt window luôn ở trên
    
    file_path = filedialog.askopenfilename(
        title="Chọn file tài liệu (PDF/DOCX)",
        filetypes=[
            ("Supported Files", "*.pdf *.docx *.doc"),
            ("PDF Files", "*.pdf"),
            ("Word Files", "*.docx *.doc"),
            ("All Files", "*.*")
        ]
    )
    
    root.destroy()
    
    if not file_path:
        raise ValueError("Không có file được chọn")
    
    return file_path


def process_document(
    file_path: str,
    config=None,
    use_remote_api: bool = False,
    **kwargs
) -> dict:
    """
    Pipeline chính để xử lý tài liệu: ingestion → parsing → chunking → embedding → vector store.

    Args:
        file_path (str): Đường dẫn file pdf/docx
        config: IndexingConfig object (nếu None, sẽ load từ configs/indexing_config.yaml)
        use_remote_api (bool): Sử dụng remote embedding API thay vì local model (default: False)
        **kwargs: Tham số bổ sung (sẽ override config từ file)
            - chunker_params: {'strategy': 'fixed_size' | 'hierarchical', ...}
            - embedding_params: {'model_dir': str, 'max_length': int, ...}
            - store_params: {'collection_name': str, 'is_persist': bool, ...}

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'collection': str (tên collection nếu success),
            'chunks_count': int,
            'embeddings_count': int
        }
    """
    from src.indexing.config import IndexingConfig
    from src.indexing.chunker import create_chunker
    from src.indexing.embedding import EmbeddingPipeline, OnnxEmbeddingModel, RemoteEmbeddingModel
    from src.indexing.vector_store import ChromaStore, VectorStorePipeline, ChromaConfig
    from src.api import RemoteAPIClient

    try:
        # Load config từ file nếu chưa được truyền vào
        if config is None:
            config = IndexingConfig.get_default_config()
        
        # Get parameters từ config, có thể override bởi kwargs
        chunker_params = {**config.get_chunker_params(), **kwargs.get('chunker_params', {})}
        embedding_params = {**config.get_embedding_params(), **kwargs.get('embedding_params', {})}
        store_params = {**config.get_store_params(), **kwargs.get('store_params', {})}
        
        # Step 1: Chunking (includes ingestion & parsing)
        chunking_strategy = chunker_params.pop('strategy', 'fixed_size')

        tqdm.write(f'[1/4] Chunking with strategy: {chunking_strategy}')
        chunker = create_chunker(strategy=chunking_strategy, **chunker_params)
        tree, chunks = chunker.create_document_node(file_path=file_path)
        chunks_count = len(chunks)
        tqdm.write(f'      Generated {chunks_count} chunks')

        # Step 2: Embedding
        tqdm.write(f'[2/4] Generating embeddings')
        batch_size = embedding_params.get('batch_size', 32)
        
        if use_remote_api:
            # Sử dụng remote embedding API
            tqdm.write(f'      Using remote embedding API')
            api_client = RemoteAPIClient()
            embedding_model = RemoteEmbeddingModel(api_client)
        else:
            # Sử dụng local ONNX model
            onnx_params = {k: v for k, v in embedding_params.items() if k != 'batch_size'}
            embedding_model = OnnxEmbeddingModel(**onnx_params)
        
        embedding_pipeline = EmbeddingPipeline(chunk_documents=chunks)
        embeddings = embedding_pipeline.run(lambda reqs: embedding_model.embed(reqs, batch_size=batch_size))
        embeddings_count = len(embeddings)
        tqdm.write(f'      Generated {embeddings_count} embeddings')

        # Step 3: Vector Store
        tqdm.write(f'[3/4] Storing in ChromaDB')
        chroma_config = ChromaConfig(**store_params)
        chroma_store = ChromaStore(chroma_config)
        vector_store_pipeline = VectorStorePipeline(embeddings=embeddings)
        vector_store_pipeline.run(chroma_store)
        tqdm.write(f'      Upserted to collection: {chroma_config.collection_name}')

        tqdm.write(f'[4/4] Pipeline completed successfully')
        
        return {
            'success': True,
            'message': 'Document processed successfully',
            'collection': chroma_config.collection_name,
            'chunks_count': chunks_count,
            'embeddings_count': embeddings_count
        }

    except Exception as e:
        import traceback
        error_msg = f"Error processing document: {str(e)}"
        tqdm.write(f"[ERROR] {error_msg}")
        tqdm.write(traceback.format_exc())
        
        return {
            'success': False,
            'message': error_msg,
            'collection': None,
            'chunks_count': 0,
            'embeddings_count': 0
        }

if __name__ == "__main__":
    from src.indexing.config import IndexingConfig
    
    try:
        # Mở file picker dialog
        file_path = select_file_dialog()
        print(f"Đã chọn file: {file_path}\n")
        
        # Load config từ file
        config = IndexingConfig.get_default_config()
        
        # Chạy pipeline
        result = process_document(file_path=file_path, config=config)
        
        print("\n" + "=" * 70)
        print("PIPELINE RESULT")
        print("=" * 70)
        print(f"Status: {'SUCCESS' if result['success'] else 'FAILED'}")
        print(f"Message: {result['message']}")
        if result['success']:
            print(f"Collection: {result['collection']}")
            print(f"Chunks: {result['chunks_count']}")
            print(f"Embeddings: {result['embeddings_count']}")
        print("=" * 70)
        
    except ValueError as e:
        print(f"[ERROR] {e}")
    except Exception as e:
        import traceback
        print(f"[ERROR] Unexpected error: {e}")
        traceback.print_exc()