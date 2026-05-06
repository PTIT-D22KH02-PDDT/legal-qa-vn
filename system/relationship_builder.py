import logging
from pathlib import Path
from typing import List, Dict, Tuple

from src.core.models import DocumentRelation, DocumentMetadata
from src.core.enums import RelationType
from .enums import FolderType
from .schemas import DocumentInfo, FolderTypeDetector, RelationTypeDeterminer

logger = logging.getLogger(__name__)


class DocumentRelationshipBuilder:
    """Pipeline xây dựng quan hệ giữa các tài liệu luật + indexing"""
    
    def __init__(
        self,
        extract_metadata: bool = True,
        index_documents: bool = True,
        use_remote_api: bool = False
    ):  
        self.documents: Dict[FolderType, List[DocumentInfo]] = {}
        self.relations: List[DocumentRelation] = []
        self.indexing_stats = {
            'total_files': 0,
            'indexed_files': 0,
            'failed_files': 0,
            'total_chunks': 0,
            'total_embeddings': 0,
        }
        self.extract_metadata = extract_metadata
        self.index_documents = index_documents
        self.use_remote_api = use_remote_api
    
    def _index_document(self, file_path: Path) -> Dict:
        """
        Index một document: chunk + embed + save to ChromaDB
        
        Sử dụng pipeline từ src.indexing.indexing
        
        Args:
            file_path: Đường dẫn file
        
        Returns:
            Dict với stats {success, chunks_count, embeddings_count, message}
        """
        try:
            from src.indexing.indexing import process_document
            from src.indexing.config import IndexingConfig
            
            logger.info(f"[Indexing] Processing: {file_path.name}")
            
            # Reuse process_document từ indexing.py
            config = IndexingConfig.get_default_config()
            result = process_document(
                file_path=str(file_path),
                config=config,
                use_remote_api=self.use_remote_api
            )
            
            if not result['success']:
                logger.error(f"[Indexing] Failed to process {file_path.name}: {result['message']}")
                self.indexing_stats['failed_files'] += 1
                return {
                    'success': False,
                    'error': result['message'],
                    'chunks_count': result.get('chunks_count', 0),
                    'embeddings_count': result.get('embeddings_count', 0),
                }
            
            # Update stats
            self.indexing_stats['total_chunks'] += result['chunks_count']
            self.indexing_stats['total_embeddings'] += result['embeddings_count']
            self.indexing_stats['indexed_files'] += 1
            
            logger.info(
                f"[Indexing] Success - "
                f"{result['chunks_count']} chunks, "
                f"{result['embeddings_count']} embeddings"
            )
            
            return {
                'success': True,
                'chunks_count': result['chunks_count'],
                'embeddings_count': result['embeddings_count'],
                'collection': result['collection'],
                'metadata': result.get('metadata', {})
            }
        
        except Exception as e:
            logger.error(f"[Indexing] Error processing {file_path.name}: {e}", exc_info=True)
            self.indexing_stats['failed_files'] += 1
            return {'success': False, 'error': str(e)}
    
    def scan_folder_structure(self, parent_folder: Path) -> Dict[FolderType, List[DocumentInfo]]:
        """
        Scan cấu trúc thư mục con và thu thập thông tin tài liệu
        
        Args:
            parent_folder: Đường dẫn thư mục cha chứa các thư mục con
        
        Returns:
            Dict[FolderType, List[DocumentInfo]]
        """
        parent_path = Path(parent_folder).resolve()
        
        if not parent_path.is_dir():
            logger.error(f"Folder không tồn tại: {parent_path}")
            return {}
        
        self.documents = {}
        
        # Duyệt các thư mục con
        for subfolder in parent_path.iterdir():
            if not subfolder.is_dir():
                continue
            
            folder_type = FolderTypeDetector.detect(subfolder.name)
            if folder_type == FolderType.OTHER:
                logger.warning(f"Không nhận diện thư mục: {subfolder.name}")
                continue
            
            # Tìm các file trong thư mục
            doc_files = []
            for file_path in subfolder.rglob("*"):
                # Chỉ lấy các file có extension hỗ trợ
                if file_path.is_file() and file_path.suffix.lower() in [".docx", ".doc", ".pdf"]:
                    self.indexing_stats['total_files'] += 1
                    
                    doc_info = DocumentInfo(
                        file_path=file_path,
                        folder_type=folder_type,
                        metadata={}
                    )
                    if self.extract_metadata:
                        # Extract metadata
                        from src.indexing.parsing.extract_metadata import Extractor
                        extractor=Extractor()
                        rs=extractor.process_document(str(file_path))
                        doc_info.metadata = rs.metadata.model_dump() if rs.metadata else {}
                        logger.info(f"Extracted metadata for {file_path.name}: {doc_info.metadata.get('so_hieu')}")
                    if self.index_documents:
                    # Extract metadata
                    #Pipeline xử lý dữ liệu : chunking-->embedding-->save to DB
                        result=self._index_document(file_path)
                        doc_info.metadata = result.get('metadata', {})
                        logger.info(f"Process file {doc_info.file_path.name}: {doc_info.metadata.get('so_hieu')}")
                    doc_files.append(doc_info)
            
            if doc_files:
                self.documents[folder_type] = doc_files
                logger.info(f"Folder [{folder_type.value}]: {len(doc_files)} file(s)")
        
        return self.documents
    
    def build_relations(self) -> List[DocumentRelation]:
        """
        Xây dựng quan hệ giữa các tài liệu
        
        Mỗi tài liệu trong folder khác "luật" sẽ có quan hệ với tất cả tài liệu trong folder "luật"
        
        Returns:
            List[DocumentRelation]
        """
        self.relations = []
        
        if FolderType.LUAT not in self.documents:
            logger.warning("Không tìm thấy folder 'luat'")
            return self.relations
        
        luat_docs = self.documents[FolderType.LUAT]
        
        # Xây dựng quan hệ từ các folder khác tới folder "luật"
        for folder_type, docs in self.documents.items():
            if folder_type == FolderType.LUAT:
                continue
            
            relation_type = RelationTypeDeterminer.get_relation_type(
                source_folder=folder_type,
                target_folder=FolderType.LUAT
            )
            
            if not relation_type:
                logger.debug(f"Bỏ qua folder {folder_type.value} (không có quan hệ với luật)")
                continue
            
            # Tạo relation giữa mỗi doc trong folder và tất cả docs trong "luật"
            for source_doc in docs:
                for target_doc in luat_docs:
                    relation = DocumentRelation(
                        entity_start=source_doc.metadata.get('so_hieu'),
                        entity_end=target_doc.metadata.get('so_hieu'),  # Fallback nếu metadata không có so_hieu
                        relation_type=relation_type,
                        description=f"{source_doc.folder_type.value} → {target_doc.folder_type.value}"
                    )
                    self.relations.append(relation)
                    logger.info(
                        f"Relation: {source_doc.metadata.get('so_hieu')} "
                        f"--[{relation_type.value}]--> {target_doc.metadata.get('so_hieu')}"
                    )
        
        return self.relations
    
    def get_stats(self) -> Dict:
        """Lấy thống kê"""
        return {
            "total_folders": len(self.documents),
            "total_documents": sum(len(docs) for docs in self.documents.values()),
            "total_relations": len(self.relations),
            "documents_by_folder": {
                ft.value: len(docs)
                for ft, docs in self.documents.items()
            },
            "relations_by_type": {
                rt.value: len([r for r in self.relations if r.relation_type == rt])
                for rt in RelationType
            },
            "indexing": self.indexing_stats if self.index_documents else None,
        }
    
    def run(self, parent_folder: Path) -> Tuple[List[DocumentInfo], List[DocumentRelation]]:
        """
        Pipeline đầy đủ: scan → build relations
        
        Args:
            parent_folder: Đường dẫn thư mục cha
        
        Returns:
            Tuple[documents, relations]
        """
        logger.info(f"[DocumentRelationshipBuilder] Bắt đầu scan: {parent_folder}")
        
        self.scan_folder_structure(parent_folder)
        
        logger.info(f"[DocumentRelationshipBuilder] Xây dựng quan hệ...")
        self.build_relations()
        
        stats = self.get_stats()
        logger.info(f"[DocumentRelationshipBuilder] Hoàn thành:")
        logger.info(f"  Folders: {stats['total_folders']}")
        logger.info(f"  Documents: {stats['total_documents']}")
        logger.info(f"  Relations: {stats['total_relations']}")
        
        if self.index_documents and stats['indexing']:
            logger.info(f"[Indexing Stats]")
            logger.info(f"  Files processed: {stats['indexing']['total_files']}")
            logger.info(f"  Files indexed: {stats['indexing']['indexed_files']}")
            logger.info(f"  Files failed: {stats['indexing']['failed_files']}")
            logger.info(f"  Total chunks: {stats['indexing']['total_chunks']}")
            logger.info(f"  Total embeddings: {stats['indexing']['total_embeddings']}")
        
        # Flatten documents list
        all_docs = []
        for docs in self.documents.values():
            all_docs.extend(docs)
        
        return all_docs, self.relations


def build_relationships(
    parent_folder: Path,
    extract_metadata: bool = True,
    index_documents: bool = False,
    use_remote_api: bool = False
) -> Tuple[List[DocumentInfo], List[DocumentRelation]]:
    """
    Hàm tiện lợi để xây dựng quan hệ giữa các tài liệu
    
    Args:
        parent_folder: Đường dẫn thư mục cha
    
    Returns:
        Tuple[documents, relations]
    """
    builder = DocumentRelationshipBuilder(
        extract_metadata=extract_metadata,
        index_documents=index_documents,
        use_remote_api=use_remote_api
    )
    return builder.run(parent_folder)