"""
Migration: Thêm field 'trang_thai' vào metadata của toàn bộ chunk trong ChromaDB.

- trang_thai = 1 : Còn hiệu lực  (mặc định cho toàn bộ chunk hiện tại)
- trang_thai = 0 : Hết hiệu lực

ChromaDB không hỗ trợ UPDATE trực tiếp như SQL, nên ta phải:
  1. Lấy toàn bộ chunk (get all IDs)
  2. Với mỗi batch, cập nhật metadata bằng collection.update()

Chạy: uv run migrations/add_trang_thai_chroma.py

Lưu ý: Script này có thể chạy lâu nếu ChromaDB có nhiều chunk.
        Tiến độ sẽ được in ra màn hình theo từng batch.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Cấu hình ──────────────────────────────────────────────────────────────────
CHROMA_DIR        = "chroma_db"           # Thư mục ChromaDB persist
COLLECTION_NAME   = "legal_documents"     # Tên collection
BATCH_SIZE        = 500                   # Số chunk cập nhật mỗi lần (tránh OOM)



def migrate(chroma_dir: str, collection_name: str, batch_size: int) -> None:
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(name=collection_name)

    total = collection.count()
    logger.info("Collection '%s' có %d chunks. Bắt đầu migration ...", collection_name, total)

    if total == 0:
        logger.info("Collection rỗng. Không có gì để cập nhật.")
        return

    updated = 0
    skipped = 0
    offset   = 0

    while offset < total:
        # Lấy batch theo offset (ChromaDB hỗ trợ limit/offset từ v0.4+)
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["metadatas"],
        )

        ids       = batch["ids"]
        metadatas = batch["metadatas"]

        if not ids:
            break

        # Chỉ cập nhật những chunk CHƯA có trường trang_thai
        ids_to_update      = []
        metadatas_to_update = []

        for chunk_id, meta in zip(ids, metadatas):
            if meta is None:
                meta = {}
            if "trang_thai" in meta:
                skipped += 1
                continue
            meta["trang_thai"] = 1
            ids_to_update.append(chunk_id)
            metadatas_to_update.append(meta)

        if ids_to_update:
            collection.update(
                ids=ids_to_update,
                metadatas=metadatas_to_update,
            )
            updated += len(ids_to_update)

        offset += len(ids)
        logger.info("Tiến độ: %d/%d chunks đã xử lý (updated=%d, skipped=%d).",
                    offset, total, updated, skipped)

    logger.info("✓ Migration ChromaDB hoàn tất: updated=%d, skipped=%d (đã có trang_thai).",
                updated, skipped)


if __name__ == "__main__":
    if not os.path.exists(CHROMA_DIR):
        logger.error("Không tìm thấy thư mục ChromaDB: %s", CHROMA_DIR)
        sys.exit(1)

    migrate(CHROMA_DIR, COLLECTION_NAME, BATCH_SIZE)
