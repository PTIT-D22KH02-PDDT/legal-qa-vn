"""
Script kiểm tra nhanh: Lấy 1 chunk từ ChromaDB và in toàn bộ metadata.
Dùng để xác nhận trường 'trang_thai' đã được thêm vào hay chưa.

Chạy: uv run scripts/inspect_chunk.py
"""
import chromadb
import json

CHROMA_DIR      = "chroma_db"
COLLECTION_NAME = "legal_documents"


def main():
    client     = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(name=COLLECTION_NAME)

    total = collection.count()
    print(f"Tổng số chunks trong collection: {total}\n")

    # Lấy 1 chunk đầu tiên (limit=1)
    result = collection.get(limit=1, include=["metadatas", "documents"])

    if not result["ids"]:
        print("Collection rỗng, không có chunk nào.")
        return

    chunk_id = result["ids"][0]
    text     = result["documents"][0]
    metadata = result["metadatas"][0]

    print("=" * 60)
    print(f"  chunk_id : {chunk_id}")
    print("=" * 60)
    print(f"\n  text (100 ký tự đầu):\n  {text[:100]}...")
    print("\n  metadata:")
    for key, value in metadata.items():
        # Nếu value là JSON string (như reference), parse ra cho dễ đọc
        if isinstance(value, str) and value.startswith("["):
            try:
                value = json.loads(value)
            except Exception:
                pass
        print(f"    {key:20s} = {value}")

    print("\n" + "=" * 60)
    if "trang_thai" in metadata:
        val = metadata["trang_thai"]
        label = "Còn hiệu lực" if val == 1 else "Hết hiệu lực"
        print(f"  ✅ 'trang_thai' ĐÃ có: {val} ({label})")
    else:
        print("  ❌ 'trang_thai' CHƯA có trong metadata chunk này!")
    print("=" * 60)


if __name__ == "__main__":
    main()
