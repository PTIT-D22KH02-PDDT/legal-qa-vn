"""
Migration: Thêm cột 'trang_thai' vào bảng document_metadata (SQLite).

- trang_thai = 1 : Còn hiệu lực  (mặc định cho toàn bộ bản ghi hiện tại)
- trang_thai = 0 : Hết hiệu lực

Chạy: uv run migrations/add_trang_thai_sqlite.py
"""

import os
import sys
import logging

# Để import được các module trong src/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Cấu hình ──────────────────────────────────────────────────────────────────
DB_PATH = "database/legal_documents.db"   # Sửa lại nếu file .db nằm chỗ khác
# ──────────────────────────────────────────────────────────────────────────────


def migrate(db_path: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        # Kiểm tra xem cột đã tồn tại chưa để tránh chạy lại bị lỗi
        result = conn.execute(text("PRAGMA table_info(document_metadata)"))
        columns = [row[1] for row in result.fetchall()]

        if "trang_thai" in columns:
            logger.info("Cột 'trang_thai' đã tồn tại trong bảng document_metadata. Bỏ qua.")
            return

        logger.info("Đang thêm cột 'trang_thai' vào bảng document_metadata ...")

        # Bước 1: Thêm cột với giá trị mặc định NULL
        conn.execute(text(
            "ALTER TABLE document_metadata ADD COLUMN trang_thai INTEGER DEFAULT 1"
        ))

        # Bước 2: Cập nhật toàn bộ bản ghi hiện có thành 1 (Còn hiệu lực)
        result = conn.execute(text(
            "UPDATE document_metadata SET trang_thai = 1 WHERE trang_thai IS NULL"
        ))
        conn.commit()

        logger.info("✓ Đã thêm cột và cập nhật %d bản ghi thành trang_thai=1.", result.rowcount)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        logger.error("Không tìm thấy file database: %s", DB_PATH)
        sys.exit(1)

    migrate(DB_PATH)
    logger.info("Migration SQLite hoàn tất.")
