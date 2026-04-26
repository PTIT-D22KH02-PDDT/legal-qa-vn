import logging
from pathlib import Path
from src.system.relationship_builder import build_relationships

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # Thay đổi đường dẫn này thành thư mục cha của bạn
    # Example: parent_folder = Path("C:/Users/LAPTOP HP/Downloads/data_raw_law/luat_dan_su")
    parent_folder = Path(r"C:\Users\LAPTOP HP\Downloads\data_raw_law\hinh_su")
    
    if not parent_folder.exists():
        logger.error(f"Folder không tồn tại: {parent_folder}")
        exit(1)
    
    # Scan folder structure (không extract metadata)
    logger.info("\n" + "="*70)
    logger.info("QUICK SCAN (không extract metadata)")
    logger.info("="*70)
    docs_quick, relations_quick = build_relationships(
        parent_folder=parent_folder,
        extract_metadata=True,
        index_documents=False
    )
    
    print(f"\n📄 Documents found: {len(docs_quick)}")
    for doc in docs_quick:
        print(f"   - {doc.metadata.get('so_hieu')} ({doc.folder_type.value}) @ {doc.file_path.name}")
    
    print(f"\n🔗 Relations created: {len(relations_quick)}")
    for rel in relations_quick[:10]:  # Chỉ in 10 cái đầu
        print(f"   {rel.entity_start} --[{rel.relation_type.value}]--> {rel.entity_end}")
    if len(relations_quick) > 10:
        print(f"   ... và {len(relations_quick) - 10} relations khác")