import logging
from src.system.database.db_respository import init_database
from src.system.database.db_service import DocumentDatabaseService

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def query_all_documents():
    """Truy xuất và in tất cả documents từ database"""
    
    logger.info("\n" + "="*70)
    logger.info("QUERY ALL DOCUMENTS FROM DATABASE")
    logger.info("="*70)
    
    try:
        # Initialize database
        db_manager = init_database()
        logger.info("✓ Database connected")
        
        # Create service
        session = db_manager.get_session()
        service = DocumentDatabaseService(session=session)
        
        # Get all documents
        logger.info("\nFetching all documents...")
        docs = service.get_all_documents(limit=1000, offset=0)
        
        if not docs:
            logger.info("No documents found in database")
            service.close()
            db_manager.close()
            return
        
        # Print statistics
        logger.info(f"\nFound {len(docs)} documents\n")
        
        # Print each document
        logger.info("─" * 70)
        for idx, doc in enumerate(docs, 1):
            logger.info(f"\n[{idx}] {doc['so_hieu']}")
            logger.info(f"    Tên: {doc['ten_van_ban']}")
            logger.info(f"    Loại: {doc['loai']}")
            logger.info(f"    Cơ quan: {doc['co_quan_ban_hanh']}")
            logger.info(f"    Ngày ban hành: {doc['ngay_ban_hanh']}")
            logger.info(f"    Ngày có hiệu lực: {doc['ngay_co_hieu_luc']}")
            logger.info(f"    Số điều: {doc['so_dieu']}")
            logger.info(f"    File: {doc['file_path']}")
            logger.info(f"    Indexed: {'Yes' if doc['indexed'] else 'No'}")
        
        logger.info("\n" + "─" * 70)
        logger.info(f"\n✓ Total: {len(docs)} documents")
        
        # Get database stats
        stats = service.get_stats()
        logger.info(f"\nDatabase Statistics:")
        logger.info(f"   Total Documents: {stats['total_documents']}")
        logger.info(f"   Indexed Documents: {stats['indexed_documents']}")
        logger.info(f"   Total Relations: {stats['total_relations']}")
        
        service.close()
        db_manager.close()
        
        logger.info("\n" + "="*70)
        logger.info("✓ Done!")
        logger.info("="*70)
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    query_all_documents()
