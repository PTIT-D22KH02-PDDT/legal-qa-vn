import logging
from pathlib import Path
from system.relationship_builder import build_relationships
from system.database.db_service import DocumentDatabaseService
from src.indexing.vector_store import ChromaStore, ChromaConfig
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
COLLECTION_NAME="legal_documents"
CHROMA_DIR="chroma_db"
if __name__ == "__main__":
    chroma_store = ChromaStore(ChromaConfig(
        collection_name=COLLECTION_NAME,
        is_persist=True,
        persist_directory=CHROMA_DIR,
        distance_metric='cosine'
    ))
    # Thay đổi đường dẫn này thành thư mục cha của bạn
    # Example: parent_folder = Path("C:/Users/LAPTOP HP/Downloads/data_raw_law/luat_dan_su")
    parent_folder = Path(r"D:\project\data_raw_law\hinh_su")
    
    if not parent_folder.exists():
        logger.error(f"Folder không tồn tại: {parent_folder}")
        exit(1)
    
    # Scan folder structure (không extract metadata)
    logger.info("\n" + "="*70)
    logger.info("QUICK SCAN")
    logger.info("="*70)
    docs_quick, relations_quick = build_relationships(
        parent_folder=parent_folder,
        extract_metadata=True,
        index_documents=False
    )
    
    # Save to SQLite Database
    logger.info("\n" + "="*70)
    logger.info("SAVING TO SQLITE DATABASE")
    logger.info("="*70)
    
    # Lưu vào database chỉ bằng 2 dòng nhờ Service Pattern
    db_service = DocumentDatabaseService()
    saved_docs, saved_rels = db_service.save_document_with_relations(docs_quick, relations_quick)
    
    print(f"✅ Đã lưu {saved_docs} văn bản vào bảng document_metadata.")
    print(f"✅ Đã lưu {saved_rels} quan hệ vào bảng document_relation.")
    
    print(f"\n📄 Documents found: {len(docs_quick)}")
    for doc in docs_quick:
        print(f"   - {doc.metadata.get('so_hieu')} ({doc.folder_type.value}) @ {doc.file_path.name}")
    
    print(f"\n🔗 Relations created: {len(relations_quick)}")
    for rel in relations_quick[:10]:  # Chỉ in 10 cái đầu
        print(f"   {rel.entity_start} --[{rel.relation_type.value}]--> {rel.entity_end}")
    if len(relations_quick) > 10:
        print(f"   ... và {len(relations_quick) - 10} relations khác")