"""
Test chức năng sửa đổi / thay thế văn bản.

Chạy từ thư mục gốc:
    uv run -m system.test_amendment
"""

import logging
from pathlib import Path
from src.indexing.vector_store import ChromaStore, ChromaConfig
from system.replace_file_service import ReplaceFileService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Cấu hình test — chỉnh lại 2 giá trị này trước khi chạy ──────────────────

# Đường dẫn file văn bản mới (file cần index)
NEW_FILE_PATH = r"C:\Users\LAPTOP HP\Downloads\135_VBHN-VPQH_672275.doc"

# Số hiệu văn bản bị thay thế (phải đã có trong CSDL)
REPLACED_SO_HIEU = "100_2015_qh13"

if __name__ == "__main__":
    print("=" * 70)
    print("TEST: AmendmentService")
    print("=" * 70)
    print(f"  File mới      : {NEW_FILE_PATH}")
    print(f"  VB bị thay thế: {REPLACED_SO_HIEU}")
    print("=" * 70)

    # Kiểm tra file tồn tại trước khi chạy
    if not Path(NEW_FILE_PATH).exists():
        logger.error("File không tồn tại: %s", NEW_FILE_PATH)
        exit(1)

    COLLECTION_NAME="legal_documents"
    CHROMA_DIR="chroma_db"
    chroma_store = ChromaStore(ChromaConfig(
        collection_name=COLLECTION_NAME,
        is_persist=True,
        persist_directory=CHROMA_DIR
    ))
    svc = ReplaceFileService(chroma_store=chroma_store)
    try:
        result = svc.process(
            new_file_path=NEW_FILE_PATH,
            replaced_so_hieu=REPLACED_SO_HIEU,
        )
    finally:
        svc.close()

    print("\n" + "=" * 70)
    print("KẾT QUẢ")
    print("=" * 70)

    ok   = "✅"
    fail = "❌"

    print(f"  [1] Indexing")
    print(f"      so_hieu văn bản mới : {result['new_so_hieu'] or '(không trích xuất được)'}")
    print(f"      Số chunk đã index   : {result['chunks_indexed']}")
    print(f"      Lưu metadata SQLite : {ok if result['sqlite_saved'] else fail}")

    print(f"  [2] Vô hiệu hóa '{REPLACED_SO_HIEU}'")
    print(f"      SQLite trang_thai=0 : {ok if result['sqlite_deactivated'] else fail}")
    print(f"      Chroma chunks vô hiệu: {result['chroma_deactivated']}")

    print(f"  [3] Quan hệ thay_the    : {ok if result['relation_saved'] else fail}")
    print("=" * 70)

    all_ok = (
        result["chunks_indexed"] > 0
        and result["sqlite_saved"]
        and result["sqlite_deactivated"]
        and result["chroma_deactivated"] > 0
        and result["relation_saved"]
    )
    if all_ok:
        print("✅ Tất cả bước đều thành công!")
    else:
        print("⚠️  Một số bước chưa thành công, kiểm tra log ở trên.")
