import os
import argparse
import logging
from typing import List
from src.indexing.vector_store import ChromaStore, ChromaConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MergeChroma")

def merge_shards(shard_dirs: List[str], output_dir: str, collection_name: str):
    # 1. Khởi tạo Master DB
    master_store = ChromaStore(
        config=ChromaConfig(
            collection_name=collection_name,
            persist_directory=output_dir,
            is_persist=True
        )
    )
    
    total_merged = 0
    
    # 2. Duyệt qua từng shard
    for shard_dir in shard_dirs:
        if not os.path.exists(shard_dir):
            logger.warning(f"Shard directory {shard_dir} not found. Skipping.")
            continue
            
        logger.info(f"Merging {shard_dir}...")
        
        shard_store = ChromaStore(
            config=ChromaConfig(
                collection_name=collection_name,
                persist_directory=shard_dir,
                is_persist=True
            )
        )
        
        # Lấy TOÀN BỘ danh sách ID đã có ở Master để skip (Chroma mặc định chỉ lấy 100 cái)
        existing_ids = set()
        _offset = 0
        _limit = 10000
        while True:
            _ids = master_store.collection.get(include=[], limit=_limit, offset=_offset)["ids"]
            if not _ids: break
            existing_ids.update(_ids)
            _offset += len(_ids)
        logger.info(f"  - Master DB already has {len(existing_ids)} records.")

        import time
        offset = 0
        limit = 1000 
        
        while True:
            data = shard_store.collection.get(
                include=["embeddings", "metadatas", "documents"],
                limit=limit,
                offset=offset
            )
            
            if not data["ids"]:
                break
                
            # Lọc bỏ những ID đã tồn tại
            batch_ids = data["ids"]
            batch_embeddings = data["embeddings"]
            batch_metadatas = data["metadatas"]
            batch_documents = data["documents"]
            
            # Tìm các index của ID chưa có trong Master
            new_indices = [i for i, _id in enumerate(batch_ids) if _id not in existing_ids]
            
            if new_indices:
                filtered_ids = [batch_ids[i] for i in new_indices]
                filtered_embeddings = [batch_embeddings[i] for i in new_indices]
                filtered_metadatas = [batch_metadatas[i] for i in new_indices]
                filtered_documents = [batch_documents[i] for i in new_indices]
                
                # Dùng upsert để ghi đè nếu bản ghi cũ bị lỗi dở dang
                master_store.collection.upsert(
                    ids=filtered_ids,
                    embeddings=filtered_embeddings,
                    metadatas=filtered_metadatas,
                    documents=filtered_documents
                )
                logger.info(f"  - Added {len(filtered_ids)} new records (Batch offset {offset})")
                total_merged += len(filtered_ids)
            else:
                logger.info(f"  - Batch at offset {offset} already exists, skipping.")
            
            count = len(batch_ids)
            offset += count
            time.sleep(0.3) 
            
    logger.info(f"SUCCESS: Total {total_merged} records merged into {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", nargs="+", required=True, help="Danh sách các thư mục shard")
    parser.add_argument("--output", required=True, help="Thư mục Master DB đầu ra")
    parser.add_argument("--collection", default="legal_documents", help="Tên collection")
    
    args = parser.parse_args()
    merge_shards(args.shards, args.output, args.collection)
