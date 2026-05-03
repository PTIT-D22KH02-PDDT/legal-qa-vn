import os
import sys
import logging
import multiprocessing
import gc
import argparse
from typing import List, Dict, Any
from tqdm import tqdm
import polars as pl
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor

# Thêm root vào path để import các module của dự án
sys.path.append(os.getcwd())

from src.core.models import DocumentNode
from src.indexing.embedding import RemoteEmbeddingModel, EmbeddingPipeline, EmbeddingResult
from src.indexing.vector_store import ChromaStore, ChromaConfig, VectorStorePipeline

# Fix Windows console UTF-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ParquetIndexer")

# --- Cấu hình ---
CONTENT_PATH = r"D:\PTIT\BTL\NLP\data\data\content.parquet"
COLLECTION_NAME = "legal_documents"
CHROMA_DIR = "chroma_db"

MAX_TOKENS_PER_CHUNK = 1900 
CHUNK_OVERLAP_TOKENS = 200
DOC_BATCH_SIZE = 1500 
MAX_WORKERS = 3

EMBED_BATCH_SIZE = 128 

def init_worker():
    global _parser, _chunker, _splitter, BeautifulSoup, RecursiveCharacterTextSplitter, create_chunk_embedding_text
    from bs4 import BeautifulSoup
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from src.indexing.parsing.legal_parser import ParseLegal
    from src.indexing.chunker.hierarchical import HierarchicalChunker
    from src.indexing.embedding.utils import create_chunk_embedding_text
    
    _parser = ParseLegal()
    _chunker = HierarchicalChunker()
    
    def token_len(text: str) -> int:
        # Ước lượng token bằng khoảng trắng theo yêu cầu người dùng
        return len(text.split())

    _splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_TOKENS_PER_CHUNK,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        length_function=token_len,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""]
    )

def process_single_row(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        from src.indexing.embedding.utils import create_chunk_embedding_text
        doc_id = str(row["id"])
        html_content = row["content_html"]
        if not html_content:
            return []
        soup = BeautifulSoup(html_content, "lxml")
        for tag in soup.find_all(['tr', 'td', 'p', 'div', 'br']):
            tag.append('\n')
        
        text = soup.get_text(separator=" ")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        
        tree = _parser.build_json_tree(doc_id=doc_id, text=clean_text)
        nodes = _chunker.chunk(tree)
        
        results = []
        for node in nodes:
            embed_text = create_chunk_embedding_text(node)
            # Kiểm tra độ dài bằng khoảng trắng
            if len(embed_text.split()) <= 2000:
                results.append(node.model_dump())
            else:
                sub_texts = _splitter.split_text(node.content or "")
                for i, sub_content in enumerate(sub_texts):
                    sub_node = node.model_copy()
                    sub_node.id = f"{node.id}_part_{i}"
                    sub_node.content = sub_content
                    results.append(sub_node.model_dump())
        return results
    except Exception as e:
        print(f"Error processing doc {row.get('id')}: {e}")
        return []

class ParquetIndexer:
    def __init__(self, chroma_dir: str = CHROMA_DIR):
        from src.api.remote_client import RemoteAPIClient
        self.api_client = RemoteAPIClient()
        self.embedding_model = RemoteEmbeddingModel(self.api_client)
        self.chroma_store = ChromaStore(
            config=ChromaConfig(
                collection_name=COLLECTION_NAME,
                persist_directory=chroma_dir,
                is_persist=True,
                distance_metric="ip"
            )
        )


    def run(self, total_parts: int = 1, part_index: int = 0, limit_docs: int = None):
        logger.info("Đang khởi tạo dữ liệu Parquet...")
        lf_content = pl.scan_parquet(CONTENT_PATH)
        total_rows = lf_content.select(pl.len()).collect().item()
        
        if limit_docs:
            total_rows = min(total_rows, limit_docs)

        part_size = total_rows // total_parts
        start_row = part_index * part_size
        end_row = total_rows if part_index == total_parts - 1 else start_row + part_size
            
        logger.info(f"Tổng: {total_rows} dòng. Máy này xử lý Part {part_index+1}/{total_parts}: từ dòng {start_row} đến {end_row}")

        num_workers = min(MAX_WORKERS, multiprocessing.cpu_count())
        
        # Thanh tiến trình tổng thể
        pbar = tqdm(total=(end_row - start_row), desc=f"Tiến độ Part {part_index+1}/{total_parts}")

        with ProcessPoolExecutor(max_workers=num_workers, initializer=init_worker) as executor:
            for start_idx in range(start_row, end_row, DOC_BATCH_SIZE):
                current_batch_size = min(DOC_BATCH_SIZE, end_row - start_idx)
                
                df_batch = lf_content.slice(start_idx, current_batch_size).collect()
                rows = df_batch.to_dicts()
                
                all_nodes_data = []
                for result_list in tqdm(executor.map(process_single_row, rows, chunksize=50), 
                                       total=len(rows), desc="Phân tích", leave=False):
                    all_nodes_data.extend(result_list)

                all_nodes = [DocumentNode(**d) for d in all_nodes_data]
                if not all_nodes:
                    continue

                logger.info(f"Đang embedding {len(all_nodes)} chunks...")
                dummy_root = DocumentNode(id="root_dummy")
                all_nodes.insert(0, dummy_root)

                embedding_pipeline = EmbeddingPipeline(chunk_documents=all_nodes)
                # Sử dụng trực tiếp embed() của model như trong main.py
                results = embedding_pipeline.run(lambda reqs: self.embedding_model.embed(reqs, batch_size=EMBED_BATCH_SIZE))
                
                logger.info(f"Đang lưu {len(results)} vector vào ChromaDB...")
                vector_pipeline = VectorStorePipeline(embeddings=results)
                vector_pipeline.run(self.chroma_store)
                pbar.update(current_batch_size)

                # Giải phóng bộ nhớ triệt để
                del all_nodes, results, all_nodes_data, df_batch, rows
                gc.collect()

        pbar.close()
        logger.info(f"\nHoàn thành Part {part_index+1}!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--total-parts", type=int, default=1, help="Tổng số máy tham gia")
    parser.add_argument("--part-index", type=int, default=0, help="Số thứ tự của máy này (0 đến total-parts - 1)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn tổng số dòng (để test)")
    parser.add_argument("--output-dir", type=str, default=CHROMA_DIR, help="Thư mục lưu ChromaDB")
    
    args = parser.parse_args()
    
    multiprocessing.freeze_support()
    indexer = ParquetIndexer(chroma_dir=args.output_dir)
    indexer.run(total_parts=args.total_parts, part_index=args.part_index, limit_docs=args.limit)
