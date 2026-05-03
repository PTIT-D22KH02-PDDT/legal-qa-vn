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
        
        # Lấy toàn bộ dữ liệu từ shard
        # Lưu ý: get() của Chroma có thể bị giới hạn bộ nhớ nếu dữ liệu quá lớn (triệu dòng)
        # Đối với 178k dòng, ta nên lấy theo từng đợt (batch)
        
        offset = 0
        limit = 5000 # Lấy mỗi lần 5000 bản ghi để an toàn cho RAM
        
        while True:
            data = shard_store.collection.get(
                include=["embeddings", "metadatas", "documents"],
                limit=limit,
                offset=offset
            )
            
            if not data["ids"]:
                break
                
            # Add vào Master DB
            master_store.collection.add(
                ids=data["ids"],
                embeddings=data["embeddings"],
                metadatas=data["metadatas"],
                documents=data["documents"]
            )
            
            count = len(data["ids"])
            total_merged += count
            offset += count
            logger.info(f"  - Merged {offset} records from {shard_dir}")
            
    logger.info(f"SUCCESS: Total {total_merged} records merged into {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", nargs="+", required=True, help="Danh sách các thư mục shard")
    parser.add_argument("--output", required=True, help="Thư mục Master DB đầu ra")
    parser.add_argument("--collection", default="legal_documents", help="Tên collection")
    
    args = parser.parse_args()
    merge_shards(args.shards, args.output, args.collection)
