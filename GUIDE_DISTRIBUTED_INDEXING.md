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
    Dùng dataset tại: https://drive.google.com/drive/folders/1wxHOt3fLeyCPk4K7UytWsZgLrJicPXdC?usp=drive_link

### Bước 2: Chạy Indexing (Chọn đúng lệnh cho từng máy)

**Các tham số quan trọng:**
*   `--input` (hoặc `-i`): Đường dẫn file parquet đầu vào (tương đối hay tuyệt đối đều được). Mặc định là `data/data/content.parquet` (tính từ gốc dự án).
*   `--total-parts`: Tổng số phần (máy) chia sẻ công việc (VD: 12).
*   `--total-parts`: Tổng số phần (máy) chia sẻ công việc (VD: 9).
*   `--part-index`: Chỉ số của máy này (từ 0 đến 8).
*   `--output-dir`: Thư mục lưu kết quả (ChromaDB shard).
*   `--start-idx` (hoặc `-sid`): Vị trí bắt đầu trong shard (dùng để resume khi bị lỗi).

| Máy số | Lệnh chạy |
| :--- | :--- |
| **Máy 0** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 0 --output-dir "shard_0" --start-idx 0` |
| **Máy 1** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 1 --output-dir "shard_1" --start-idx 0` |
| **Máy 2** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 2 --output-dir "shard_2" --start-idx 0` |
| **Máy 3** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 3 --output-dir "shard_3" --start-idx 0` |
| **Máy 4** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 4 --output-dir "shard_4" --start-idx 0` |
| **Máy 5** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 5 --output-dir "shard_5" --start-idx 0` |
| **Máy 6** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 6 --output-dir "shard_6" --start-idx 0` |
| **Máy 7** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 7 --output-dir "shard_7" --start-idx 0` |
| **Máy 8** | `uv run scripts/index_parquet.py --total-parts 9 --part-index 8 --output-dir "shard_8" --start-idx 0` |

- Phân công
    - Trung: Máy 0 - 2
    - Đại: Máy 3 - 5
    - Dương: Máy 6 - 8

Sau khi chạy xong, zip các thư mục shard lại và tải lên drive/ gửi qua zalo
**Lưu ý: Nhớ HOST embedding model trước khi indexing!**
Code host: https://www.kaggle.com/code/hngphongkiu/host-nlp

### Bước 3: Hợp nhất dữ liệu (Merge) (Cái này không cần làm)
Sau khi tất cả các máy chạy xong, gom các thư mục `shard_x` về một chỗ và chạy:
```bash
uv run scripts/merge_chroma.py --shards shard_0 shard_1 shard_2 shard_3 shard_4 shard_5 shard_6 shard_7 shard_8 shard_9 shard_10 shard_11 --output "final_legal_db"
```

---

### Xử lý khi bị ngắt (Resume)
Nếu máy đang chạy mà bị ngắt (do Rate Limit ngrok, mất mạng, v.v.), bạn **không cần chạy lại từ đầu**.

1.  **Xem thông báo lỗi**: Ở cuối màn hình log, code sẽ in ra chính xác tham số cần dùng.
    *   Ví dụ: `ĐỂ TIẾP TỤC CHẠY, HÃY THÊM THAM SỐ: --start-idx 2400`
2.  **Chạy lại lệnh cũ kèm tham số resume**:
    ```bash
    uv run scripts/index_parquet.py --total-parts 12 --part-index 5 --output-dir "shard_5" --start-idx 2400
    ```
    *(Thay `2400` bằng con số mà log lỗi đã báo cho bạn)*. Dữ liệu mới sẽ được ghi tiếp vào folder cũ.
