"""
Example sử dụng DocumentRelationshipBuilder với indexing

Tính năng mới: Khi duyệt file, tự động index (chunk + embed + save to ChromaDB)
"""

import logging
from pathlib import Path
from src.system.relationship_builder import build_relationships
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from src.indexing.vector_store.chroma_store import ChromaStore, ChromaConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_1_quick_scan():
    """Ví dụ 1: Quick scan (không index)"""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 1: Quick scan (không index)")
    logger.info("="*70)
    
    parent_folder = Path("C:/Users/LAPTOP HP/Downloads/data_raw_law")
    
    docs, relations = build_relationships(
        parent_folder=parent_folder,
        extract_metadata=False,
        index_documents=False,
    )
    
    print(f"\n📄 Documents: {len(docs)}")
    print(f"🔗 Relations: {len(relations)}")


def example_2_extract_metadata():
    """Ví dụ 2: Extract metadata (không index)"""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 2: Extract metadata (không index)")
    logger.info("="*70)
    
    parent_folder = Path("C:/Users/LAPTOP HP/Downloads/data_raw_law")
    
    docs, relations = build_relationships(
        parent_folder=parent_folder,
        extract_metadata=True,
        index_documents=False,
    )
    
    print(f"\n📄 Documents with metadata: {len(docs)}")
    for i, doc in enumerate(docs[:5], 1):
        if doc.metadata:
            print(f"  {i}. {doc.doc_id}")
            print(f"     Title: {doc.metadata.ten_van_ban}")
            print(f"     Type: {doc.metadata.loai}")
    
    print(f"\n🔗 Relations: {len(relations)}")


def example_3_with_indexing():
    """Ví dụ 3: Đầy đủ - extract metadata + index documents"""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 3: Indexing (chunk + embed + save to ChromaDB)")
    logger.info("="*70)
    
    parent_folder = Path("C:/Users/LAPTOP HP/Downloads/data_raw_law")
    
    # Setup embedding model
    logger.info("[Setup] Initializing embedding model...")
    embedding_model = OnnxEmbeddingModel(
        model_dir="models/vietnamese-embedding"
    )
    
    # Setup ChromaDB
    logger.info("[Setup] Initializing ChromaStore...")
    chroma_config = ChromaConfig(
        collection_name="legal_documents_relations",
        persist_directory="chroma_db",
        is_persist=True
    )
    chroma_store = ChromaStore(config=chroma_config)
    
    # Run full pipeline
    logger.info("[Pipeline] Starting full indexing pipeline...")
    docs, relations = build_relationships(
        parent_folder=parent_folder,
        extract_metadata=True,
        index_documents=True,
        embedding_model=embedding_model,
        chroma_store=chroma_store,
    )
    
    print(f"\n📄 Total documents: {len(docs)}")
    print(f"🔗 Total relations: {len(relations)}")
    print(f"\nDocuments:")
    for i, doc in enumerate(docs[:10], 1):
        print(f"  {i}. {doc.doc_id} ({doc.folder_type.value})")
    
    print(f"\nRelations (first 10):")
    for i, rel in enumerate(relations[:10], 1):
        print(f"  {i}. {rel.entity_start} --[{rel.relation_type.value}]--> {rel.entity_end}")
    
    if len(relations) > 10:
        print(f"  ... và {len(relations) - 10} relations khác")


if __name__ == "__main__":
    # Chọn example nào để chạy
    
    # example_1_quick_scan()
    # example_2_extract_metadata()
    example_3_with_indexing()
