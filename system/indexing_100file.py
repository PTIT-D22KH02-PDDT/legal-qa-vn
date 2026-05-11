from src.api.remote_client import RemoteAPIClient
from src.indexing.vector_store import ChromaStore, ChromaConfig, VectorStorePipeline
from src.indexing.embedding import RemoteEmbeddingModel
from src.indexing.chunker import create_chunker
from src.indexing.parsing.legal_parser import ParseLegal
from  src.indexing.parsing.extract_metadata import Extractor
from typing import Optional

from tqdm import tqdm
import time
from pathlib import Path
from sqlalchemy.orm import Session
from src.indexing.embedding import EmbeddingPipeline
from system.schemas import DocumentInfo
from system.database.db_respository import init_database
from system.database.db_service import DocumentDatabaseService


_DEFAULT_CHROMA_DIR = "chroma_db"
_DEFAULT_COLLECTION_NAME = "legal_documents"


class Indexing:
    def __init__(
        self,
        chroma_store: ChromaStore = None,
        session: Optional[Session] = None,
    ):
        self.api_client= RemoteAPIClient()
        self.embeddingmodel=RemoteEmbeddingModel(self.api_client)
        if chroma_store is None:
            self.chroma_store = ChromaStore(ChromaConfig(
                collection_name=_DEFAULT_COLLECTION_NAME,
                is_persist=True,
                persist_directory=_DEFAULT_CHROMA_DIR,
                distance_metric="cosine",
            ))
        else:
            self.chroma_store = chroma_store
        self.chroma_collection_name = self.chroma_store.config.collection_name
        self.parser = ParseLegal()
        self.chunker=  create_chunker(strategy="hierarchical")
        self.extractor = Extractor()
        if session is None:
            self.db_manager = init_database()
            self.session = self.db_manager.get_session()
            self._owns_session = True
        else:
            self.db_manager = None
            self.session = session
            self._owns_session = False
        self.db_service = DocumentDatabaseService(self.session, chroma_store=self.chroma_store)
    def run_single_file(self, file_path: str):
        tqdm.write(f'Indexing file: {file_path}')
        info, chunks=self.chunker.create_document_node(file_path=file_path)
        tqdm.write('Save metadata')
        doc_info=DocumentInfo(
            file_path=Path(file_path),
            metadata={}
        )
        doc_info.metadata=info.model_dump() if info else {}
        # Luu document metadata vao db
        saved_count, saved_so_hieu = self.db_service.save_documents([doc_info])
        tqdm.write(f'      Saved metadata for {saved_count} documents with so_hieu: {", ".join(saved_so_hieu)}')
        chunks_count = len(chunks)
        tqdm.write(f'      Generated {chunks_count} chunks')
        tqdm.write('[1/3] Generating embeddings')
        batch_size = 64
        embedding_pipeline=EmbeddingPipeline(chunk_documents=chunks)
        embeddings=embedding_pipeline.run(lambda reqs: self.embeddingmodel.embed(reqs, batch_size=batch_size))
        embeddings_count = len(embeddings)
        tqdm.write(f'      Generated {embeddings_count} embeddings')
        tqdm.write('[2/3] Storing in ChromaDB')
        vector_store_pipeline = VectorStorePipeline(
            embeddings=embeddings
        )
        vector_store_pipeline.run(self.chroma_store)
        tqdm.write(f'      Upserted to collection: {self.chroma_collection_name}')
        tqdm.write('[3/3] Done')
        return {
            "success": True,
            "chunks_count": chunks_count,
            "embeddings_count": embeddings_count,
            "metadata": info.model_dump() if info else {},
            "collection": self.chroma_collection_name,
            "file_path": file_path,
            "metadata_saved_count": saved_count,
        }

    def run_directory(self, directory_path: str):
        """Index tất cả file trong thư mục (không đệ quy)"""
        dir_path = Path(directory_path)
        if not dir_path.is_dir():
            tqdm.write(f'Error: {directory_path} is not a valid directory')
            return
        
        # Lấy tất cả file (bất kể extension)
        files = [f for f in dir_path.iterdir() if f.is_file()]
        total_files = len(files)
        
        if total_files == 0:
            tqdm.write(f'Warning: No files found in {directory_path}')
            return
        
        tqdm.write(f'Found {total_files} files in directory: {directory_path}')
        
        success_count = 0
        failed_files = []
        
        max_retries = 3
        for idx, file in enumerate(files, 1):
            tqdm.write(f'[{idx}/{total_files}] Processing: {file.name}')
            for attempt in range(max_retries):
                try:
                    self.run_single_file(str(file))
                    success_count += 1
                    break
                except Exception as e:
                    tqdm.write(f'      ❌ Error (Attempt {attempt + 1}/{max_retries}): {str(e)}')
                    if attempt == max_retries - 1:
                        failed_files.append(file.name)
                    else:
                        time.sleep(20)
        
        # Summary
        tqdm.write(f'\n=== Summary ===')
        tqdm.write(f'Success: {success_count}/{total_files}')
        if failed_files:
            tqdm.write(f'Failed files: {", ".join(failed_files)}')
        
        self.close()

    def close(self):
        """Đóng session chỉ khi Indexing tự tạo session (không truyền từ ngoài)."""
        if getattr(self, "_owns_session", False) and self.session:
            self.session.close()
            self.session = None
            tqdm.write('Database connection closed.')


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Indexing documents")
    parser.add_argument("-d", "--directory",type=str, required=True, help="Directory path")
    args = parser.parse_args()
    indexing = Indexing()
    # indexing.run_directory(args.directory)  
    indexing.run_single_file(args.directory)
