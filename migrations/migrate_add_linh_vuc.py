"""
Migration script: Thêm cột linh_vuc vào bảng document_metadata trong SQLite.

Chạy một lần duy nhất:
    python migrate_add_linh_vuc.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "database" / "legal_documents.db"

def migrate():
    if not DB_PATH.exists():
        print(f"[ERROR] DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Kiểm tra cột đã tồn tại chưa
    cursor.execute("PRAGMA table_info(document_metadata)")
    columns = [row[1] for row in cursor.fetchall()]

    if "linh_vuc" in columns:
        print("[SKIP] Column 'linh_vuc' already exists.")
    else:
        cursor.execute("ALTER TABLE document_metadata ADD COLUMN linh_vuc VARCHAR(255)")
        conn.commit()
        print("[OK] Column 'linh_vuc' added to document_metadata.")

    conn.close()

if __name__ == "__main__":
    migrate()
