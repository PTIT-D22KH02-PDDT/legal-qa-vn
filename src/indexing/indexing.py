from pathlib import Path
from tkinter import Tk, filedialog

import yaml
from tqdm import tqdm


def select_file_dialog() -> str:
    """Open a dialog to select a PDF/DOCX file."""
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    file_path = filedialog.askopenfilename(
        title="Chon file tai lieu (PDF/DOCX)",
        filetypes=[
            ("Supported Files", "*.pdf *.docx *.doc"),
            ("PDF Files", "*.pdf"),
            ("Word Files", "*.docx *.doc"),
            ("All Files", "*.*"),
        ],
    )

    root.destroy()

    if not file_path:
        raise ValueError("Khong co file duoc chon")

    return file_path


def process_document(
    file_path: str,
    use_remote_api: bool = False,
    config_path: str | Path | None = None,
    config: dict | None = None,
    chunker_params: dict | None = None,
    embedding_params: dict | None = None,
    store_params: dict | None = None,
    **kwargs,
) -> dict:
    """
    Process a document: ingestion -> parsing -> chunking -> embedding -> vector store.

    Optional kwargs:
        config_path: Path toi file YAML config.
        config: Dict config truyen truc tiep tu ben ngoai.
        chunker_params: {'strategy': 'fixed_size' | 'hierarchical', ...}
        embedding_params: {'model_dir': str, 'max_length': int, ...}
        store_params: {'collection_name': str, 'is_persist': bool, ...}
    """
    from src.api import RemoteAPIClient
    from src.indexing.chunker import create_chunker
    from src.indexing.embedding import EmbeddingPipeline, OnnxEmbeddingModel, RemoteEmbeddingModel
    from src.indexing.vector_store import ChromaConfig, ChromaStore, VectorStorePipeline

    try:
        root_dir = Path(__file__).resolve().parents[2]

        external_config = {}
        if config_path:
            config_file = Path(config_path)
            if not config_file.is_absolute():
                config_file = root_dir / config_file
            with config_file.open("r", encoding="utf-8") as f:
                external_config = yaml.safe_load(f) or {}
        if config:
            external_config = {**external_config, **config}

        config_chunking = external_config.get("chunking", {})
        config_embedding = external_config.get("embedding", {})
        config_vector_store = external_config.get("vector_store", {})

        chunker_overrides = chunker_params or {}
        embedding_overrides = embedding_params or {}
        store_overrides = store_params or {}

        chunker_params = {
            **{k: v for k, v in config_chunking.items() if v is not None},
            'strategy': config_chunking.get('strategy') or 'hierarchical',
            **kwargs.get('chunker_params', {}),
            **chunker_overrides,
        }

        embedding_params = {
            'model_dir': str(root_dir / "models" / "Vietnamese_Embedding_v2"),
            'max_length': 256,
            'batch_size': 32,
            'pooling': 'auto',
            'normalize': False,
            **{k: v for k, v in config_embedding.items() if v is not None},
            **kwargs.get('embedding_params', {}),
            **embedding_overrides,
        }
        store_params = {
            'collection_name': 'legal_documents',
            'is_persist': True,
            'persist_directory': str(root_dir / "chroma_db"),
            'distance_metric': 'ip',
            **{k: v for k, v in config_vector_store.items() if v is not None},
            **kwargs.get('store_params', {}),
            **store_overrides,
        }

        for path_key in ("model_dir", "onnx_path"):
            path_value = embedding_params.get(path_key)
            if path_value:
                path = Path(path_value)
                embedding_params[path_key] = str(path if path.is_absolute() else root_dir / path)

        persist_directory = store_params.get("persist_directory")
        if persist_directory:
            path = Path(persist_directory)
            store_params["persist_directory"] = str(path if path.is_absolute() else root_dir / path)

        chunking_strategy = chunker_params.pop('strategy', 'fixed_size')
        if chunking_strategy.strip().lower() == 'hierarchical':
            allowed_hierarchical = {'appendix_chunk_size', 'appendix_chunk_overlap', 'use_llm_refs', 'llm_client'}
            chunker_params = {k: v for k, v in chunker_params.items() if k in allowed_hierarchical}

        tqdm.write(f'[1/4] Chunking with strategy: {chunking_strategy}')
        chunker = create_chunker(strategy=chunking_strategy, **chunker_params)
        tree, chunks = chunker.create_document_node(file_path=file_path)
        chunks_count = len(chunks)
        tqdm.write(f'      Generated {chunks_count} chunks')

        tqdm.write('[2/4] Generating embeddings')
        batch_size = embedding_params.get('batch_size', 32)

        if use_remote_api:
            tqdm.write('      Using remote embedding API')
            api_client = RemoteAPIClient()
            embedding_model = RemoteEmbeddingModel(api_client)
        else:
            onnx_params = {k: v for k, v in embedding_params.items() if k != 'batch_size'}
            embedding_model = OnnxEmbeddingModel(**onnx_params)

        embedding_pipeline = EmbeddingPipeline(chunk_documents=chunks)
        embeddings = embedding_pipeline.run(lambda reqs: embedding_model.embed(reqs, batch_size=batch_size))
        embeddings_count = len(embeddings)
        tqdm.write(f'      Generated {embeddings_count} embeddings')

        tqdm.write('[3/4] Storing in ChromaDB')
        chroma_config = ChromaConfig(**store_params)
        chroma_store = ChromaStore(chroma_config)
        vector_store_pipeline = VectorStorePipeline(embeddings=embeddings)
        vector_store_pipeline.run(chroma_store)
        tqdm.write(f'      Upserted to collection: {chroma_config.collection_name}')

        tqdm.write('[4/4] Pipeline completed successfully')

        return {
            'success': True,
            'message': 'Document processed successfully',
            'collection': chroma_config.collection_name,
            'chunks_count': chunks_count,
            'embeddings_count': embeddings_count,
            'metadata': tree.model_dump() if hasattr(tree, 'model_dump') else tree,
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
            'embeddings_count': 0,
            'metadata': None,
        }


if __name__ == "__main__":
    try:
        file_path = select_file_dialog()
        print(f"Da chon file: {file_path}\n")

        result = process_document(file_path=file_path)

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
