"""
Example: Save DocumentMetadata và DocumentRelation vào database
"""

import logging
from pathlib import Path

from src.system.relationship_builder import build_relationships
from .db_respository import init_database
from .db_service import DocumentDatabaseService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_save_to_database():
    """
    Example: Scan folder structure, build relations, lưu vào database
    """
    logger.info("\n" + "="*70)
    logger.info("Step 1: Initialize Database")
    logger.info("="*70)

    db_manager = init_database()  # ✅ Đã gọi create_tables() bên trong
    logger.info("✓ Database initialized")

    logger.info("\n" + "="*70)
    logger.info("Step 2: Scan Folders & Build Relationships")
    logger.info("="*70)
    
    parent_folder = Path(r"C:\Users\LAPTOP HP\Downloads\data_raw_law\dan_su")
    
    if not parent_folder.exists():
        logger.error(f"Folder không tồn tại: {parent_folder}")
        return
    
    # Scan folder structure
    docs, relations = build_relationships(
        parent_folder=parent_folder,
        extract_metadata=True,
        index_documents=False  # Có thể set True để index vào ChromaDB
    )
    
    logger.info(f"✓ Found {len(docs)} documents")
    logger.info(f"✓ Found {len(relations)} relations")
    
    # Step 3: Save to Database
    logger.info("\n" + "="*70)
    logger.info("Step 3: Save to Database")
    logger.info("="*70)
    
    # Lấy session từ db_manager được tạo ở Step 1
    session = db_manager.get_session()
    service = DocumentDatabaseService(session=session)
    
    # Save documents
    saved_docs, saved_so_hieu = service.save_documents(documents=docs)
    logger.info(f"✓ Saved {saved_docs}/{len(docs)} documents to database")
    
    # Save relations
    saved_rels, skipped_rels = service.save_relations(relations)
    logger.info(f"✓ Saved {saved_rels} relations (skipped {skipped_rels})")
    
    #Step 4: Query Database
    logger.info("\n" + "="*70)
    logger.info("Step 4: Query Database")
    logger.info("="*70)
    
    # Get stats
    stats = service.get_stats()
    logger.info(f"Database Stats:")
    logger.info(f"  Total Documents: {stats['total_documents']}")
    logger.info(f"  Indexed Documents: {stats['indexed_documents']}")
    logger.info(f"  Total Relations: {stats['total_relations']}")
    
    # Get specific document
    if saved_so_hieu:
        first_so_hieu = saved_so_hieu[0]
        logger.info(f"\n✓ Example: Get document & relations for {first_so_hieu}")
        
        related = service.get_related_documents(first_so_hieu)
        if related:
            logger.info(f"  Document: {related['document']['ten_van_ban']}")
            logger.info(f"  Type: {related['document']['loai']}")
            logger.info(f"  Related From: {len(related['related_from'])} relations")
            logger.info(f"  Related To: {len(related['related_to'])} relations")
            
            # Print some relations
            for rel in related['related_from'][:3]:
                logger.info(f"    → {rel['source']} --[{rel['type']}]--> {rel['target']}")
    
    # Get all documents of a type
    logger.info(f"\n✓ Example: Get all 'Luật' documents")
    luat_docs = service.get_documents_by_type("Luật")
    logger.info(f"  Found {len(luat_docs)} Luật documents")
    for doc in luat_docs[:3]:
        logger.info(f"    - {doc['so_hieu']}: {doc['ten_van_ban']}")
    
    # Get all relations
    logger.info(f"\n✓ Example: Get all relations")
    all_relations = service.get_all_relations(limit=5)
    logger.info(f"  Total relations: {len(all_relations)} (showing first 5)")
    for rel in all_relations:
        logger.info(f"    {rel['entity_start']} --[{rel['type']}]--> {rel['entity_end']}")
    
    service.close()
    db_manager.close()
    
    logger.info("\n" + "="*70)
    logger.info("✓ Done! Database saved at: legal_documents.db")
    logger.info("="*70)


if __name__ == "__main__":
    example_save_to_database()
