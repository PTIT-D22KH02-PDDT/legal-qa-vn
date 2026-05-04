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
CONTENT_PATH = os.path.join("data", "data", "content_filtered.parquet")
COLLECTION_NAME = "legal_documents"
CHROMA_DIR = "chroma_db"

MAX_TOKENS_PER_CHUNK = 1900 
CHUNK_OVERLAP_TOKENS = 200
DOC_BATCH_SIZE = 1000 
MAX_WORKERS = 3

EMBED_BATCH_SIZE = 256 

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
        from bs4 import BeautifulSoup
        
        # 1. Sử dụng so_hieu làm ID
        doc_id = str(row.get("so_hieu", ""))
        if not doc_id or doc_id == "unknown":
            doc_id = str(row.get("id", "unknown")) # Fallback về id nếu so_hieu rỗng
        
        html_content = row.get("content_html")
        if not html_content:
            return []

        # 2. Làm sạch HTML (BeautifulSoup)
        soup = BeautifulSoup(html_content, "lxml")
        for tag in soup.find_all(['tr', 'td', 'p', 'div', 'br']):
            tag.append('\n')
        
        text = soup.get_text(separator=" ")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        if not clean_text:
            return []

        # 3. Phân tích cấu trúc và Chunking
        tree = _parser.build_json_tree(doc_id=doc_id, text=clean_text)
        nodes = _chunker.chunk(tree)
        
        results = []
        seen_ids = set() # Theo dõi ID trong nội bộ một văn bản
        
        for node in nodes:
            # Metadata bổ sung để ChromaDB có thể filter
            chunk_dict = node.model_dump()
            
            # ĐẢM BẢO ID DUY NHẤT: Nếu ID đã tồn tại, thêm hậu tố .1, .2
            base_id = node.id
            final_id = base_id
            counter = 1
            while final_id in seen_ids:
                final_id = f"{base_id}.{counter}"
                counter += 1
            seen_ids.add(final_id)
            chunk_dict["id"] = final_id

            chunk_dict.update({
                "so_hieu": row.get("so_hieu"),
                "co_quan_ban_hanh": row.get("co_quan_ban_hanh"),
                "loai_van_ban": row.get("loai_van_ban"),
                "title_goc": row.get("title")
            })

            embed_text = create_chunk_embedding_text(node)
            
            # 4. Kiểm tra độ dài và xử lý nếu chunk quá lớn (Splitting fallback)
            if len(embed_text.split()) <= 2000:
                results.append(chunk_dict)
            else:
                sub_texts = _splitter.split_text(node.content or "")
                for i, sub_content in enumerate(sub_texts):
                    sub_chunk = chunk_dict.copy()
                    sub_chunk["id"] = f"{final_id}_part_{i}"
                    sub_chunk["content"] = sub_content
                    results.append(sub_chunk)
                    
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


    def run(self, content_path: str = CONTENT_PATH, total_parts: int = 1, part_index: int = 0, limit_docs: int = None, start_idx_offset: int = 0):
        logger.info(f"Đang khởi tạo dữ liệu Parquet từ: {content_path}")
        lf_content = pl.scan_parquet(content_path)
        total_rows = lf_content.select(pl.len()).collect().item()
        
        if limit_docs:
            total_rows = min(total_rows, limit_docs)

        part_size = total_rows // total_parts
        start_row = part_index * part_size
        end_row = total_rows if part_index == total_parts - 1 else start_row + part_size
        
        # Áp dụng offset để resume
        current_start = start_row + start_idx_offset
        if current_start >= end_row:
            logger.info(f"Vị trí bắt đầu {current_start} đã vượt quá phạm vi của shard này ({end_row}). Dừng lại.")
            return

        logger.info(f"Tổng: {total_rows} dòng. Máy này xử lý Part {part_index+1}/{total_parts}: từ dòng {start_row} đến {end_row}")
        logger.info(f"=> Resume từ dòng: {current_start} (Offset: {start_idx_offset} trong shard)")

        num_workers = min(MAX_WORKERS, multiprocessing.cpu_count())
        
        # Thanh tiến trình tổng thể - Hiển thị tiến độ tuyệt đối trong Shard
        total_in_shard = end_row - start_row
        pbar = tqdm(total=total_in_shard, desc=f"Tiến độ Part {part_index+1}/{total_parts}")
        pbar.update(start_idx_offset)

        processed_in_shard = start_idx_offset
        try:
            with ProcessPoolExecutor(max_workers=num_workers, initializer=init_worker) as executor:
                for batch_start in range(current_start, end_row, DOC_BATCH_SIZE):
                    current_batch_size = min(DOC_BATCH_SIZE, end_row - batch_start)
                    
                    df_batch = lf_content.slice(batch_start, current_batch_size).collect()
                    rows = df_batch.to_dicts()
                    
                    all_nodes_data = []
                    for result_list in tqdm(executor.map(process_single_row, rows, chunksize=50), 
                                           total=len(rows), desc="Phân tích", leave=False):
                        all_nodes_data.extend(result_list)

                    # HẬU KIỂM: Loại bỏ trùng lặp ID trong toàn bộ Batch
                    unique_nodes_map = {}
                    duplicate_count = 0
                    for d in all_nodes_data:
                        cid = d.get("id")
                        if cid in unique_nodes_map:
                            duplicate_count += 1
                            # Nếu trùng giữa các văn bản, thêm hậu tố .batch.1
                            d["id"] = f"{cid}.batch.{duplicate_count}"
                        unique_nodes_map[d["id"]] = d
                    
                    if duplicate_count > 0:
                        logger.warning(f"Phát hiện và xử lý {duplicate_count} ID trùng lặp trong batch.")
                    
                    all_nodes_data = list(unique_nodes_map.values())
                    all_nodes = [DocumentNode(**d) for d in all_nodes_data]
                    
                    if not all_nodes:
                        processed_in_shard += current_batch_size
                        pbar.update(current_batch_size)
                        continue

                    logger.info(f"Đang embedding {len(all_nodes)} chunks...")
                    dummy_root = DocumentNode(id="root_dummy")
                    all_nodes.insert(0, dummy_root)

                    embedding_pipeline = EmbeddingPipeline(chunk_documents=all_nodes)
                    results = embedding_pipeline.run(lambda reqs: self.embedding_model.embed(reqs, batch_size=EMBED_BATCH_SIZE))
                    
                    logger.info(f"Đang lưu {len(results)} vector vào ChromaDB...")
                    vector_pipeline = VectorStorePipeline(embeddings=results)
                    vector_pipeline.run(self.chroma_store)
                    
                    processed_in_shard += current_batch_size
                    pbar.update(current_batch_size)

                    # Giải phóng bộ nhớ triệt để
                    del all_nodes, results, all_nodes_data, df_batch, rows
                    gc.collect()

        except Exception as e:
            pbar.close()
            resume_idx = processed_in_shard
            logger.error("\n" + "!"*60)
            logger.error(f"LỖI XẢY RA TẠI DÒNG TOÀN CỤC: {start_row + processed_in_shard}")
            logger.error(f"LỖI CHI TIẾT: {e}")
            logger.error(f"ĐỂ TIẾP TỤC CHẠY, HÃY THÊM THAM SỐ: --start-idx {resume_idx}")
            logger.error("!"*60 + "\n")
            raise e

        pbar.close()
        logger.info(f"\nHoàn thành Part {part_index+1}!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--total-parts", type=int, default=1, help="Tổng số máy tham gia")
    parser.add_argument("--part-index", type=int, default=0, help="Số thứ tự của máy này (0 đến total-parts - 1)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn tổng số dòng (để test)")
    parser.add_argument("--input", "-i", type=str, default=CONTENT_PATH, help="Đường dẫn file parquet đầu vào")
    parser.add_argument("--output-dir", type=str, default=CHROMA_DIR, help="Thư mục lưu ChromaDB")
    parser.add_argument("--start-idx", "-sid", type=int, default=0, help="Bắt đầu từ dòng thứ n trong shard này (để resume)")
    
    args = parser.parse_args()
    
    multiprocessing.freeze_support()
    
    # Xử lý đường dẫn linh hoạt (tuyệt đối/tương đối)
    input_path = args.input
    if not os.path.exists(input_path):
        # Thử tìm tương đối so với CWD
        cwd_path = os.path.join(os.getcwd(), input_path)
        if os.path.exists(cwd_path):
            input_path = cwd_path
        else:
            # Nếu vẫn không thấy, log cảnh báo và để nó lỗi ở bước sau để có traceback rõ ràng
            logger.warning(f"Cảnh báo: Không tìm thấy file tại {input_path} hoặc {cwd_path}")

    indexer = ParquetIndexer(chroma_dir=args.output_dir)
    indexer.run(
        content_path=input_path,
        total_parts=args.total_parts, 
        part_index=args.part_index, 
        limit_docs=args.limit,
        start_idx_offset=args.start_idx
    )
