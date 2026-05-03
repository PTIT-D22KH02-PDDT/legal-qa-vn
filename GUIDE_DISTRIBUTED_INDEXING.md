# Hướng dẫn Indexing Phân tán (12 Máy)

### Bước 1: Chuẩn bị môi trường (Mỗi máy)
1.  **Cập nhật code:**
    ```bash
    git pull origin main
    ```
2.  **Đồng bộ thư viện:**
    ```bash
    uv sync
    ```
3.  **Tải Dataset:**
    ```bash
    uv run scripts/load_dataset.py
    ```

### Bước 2: Chạy Indexing (Chọn đúng lệnh cho từng máy)

| Máy số | Lệnh chạy |
| :--- | :--- |
| **Máy 0** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 0 --output-dir "shard_0"` |
| **Máy 1** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 1 --output-dir "shard_1"` |
| **Máy 2** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 2 --output-dir "shard_2"` |
| **Máy 3** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 3 --output-dir "shard_3"` |
| **Máy 4** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 4 --output-dir "shard_4"` |
| **Máy 5** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 5 --output-dir "shard_5"` |
| **Máy 6** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 6 --output-dir "shard_6"` |
| **Máy 7** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 7 --output-dir "shard_7"` |
| **Máy 8** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 8 --output-dir "shard_8"` |
| **Máy 9** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 9 --output-dir "shard_9"` |
| **Máy 10** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 10 --output-dir "shard_10"` |
| **Máy 11** | `uv run scripts/index_parquet.py --total-parts 12 --part-index 11 --output-dir "shard_11"` |

- Phân công
    - Phong: Máy 0 - 2
    - Trung: Máy 3 - 5
    - Đại: Máy 6 - 8
    - Lâm: Máy 9 - 11
Sau khi chạy xong, zip các thư mục shard lại và tải lên drive/ gửi qua zalo

### Bước 3: Hợp nhất dữ liệu (Merge) (Cái này không cần làm)
Sau khi tất cả các máy chạy xong, gom các thư mục `shard_x` về một chỗ và chạy:
```bash
uv run scripts/merge_chroma.py --shards shard_0 shard_1 shard_2 shard_3 shard_4 shard_5 shard_6 shard_7 shard_8 shard_9 shard_10 shard_11 --output "final_legal_db"
```
