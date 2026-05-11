# RUN

Hướng dẫn nhanh để tạo môi trường và chạy `main.py` của dự án.

## Chạy `main.py`

Sau khi cài đặt dependencies và kích hoạt venv, chạy:

```bash
python main.py
```

Nếu `main.py` yêu cầu biến môi trường hoặc tham số khác, hãy kiểm tra các cấu hình trong code.

## Các chế độ (modes) — menu tương ứng trong `main.py`

Chạy `python main.py` sẽ hiển thị menu tương tác với 5 chế độ chính (0 để thoát). Mô tả từng chế độ:

- **1 — Index document with local embedding**: Nhập đường dẫn file để index; sử dụng embedding cục bộ (ONNX) và lưu vào Chroma local.
- **2 — Index document with remote embedding**: Nhập đường dẫn file để index; dùng API embedding từ xa (nếu cấu hình sẵn) để tạo embedding rồi lưu.
- **3 — Search with local embedding/local rerank**: Tìm kiếm tương tác; nhập truy vấn, chọn `top_k` và có thể bật/tắt local reranker.
- **4 — Search with optional remote embedding + remote rerank**: Tìm kiếm có thể dùng embedding từ xa và/hoặc remote reranker; hữu ích khi indexing trước đó dùng remote embedding.
- **5 — Full RAG**: Chạy quy trình RAG (retrieve + generate). Hệ thống sẽ hỏi `Enter question:` để nhập câu hỏi.

### Nhập prompt từ file (ví dụ dùng chế độ 5)

Trong **chế độ 5 (Full RAG)**, khi chương trình hỏi `Enter question:` bạn có thể nhập trực tiếp câu hỏi hoặc sử dụng cú pháp đọc nội dung từ file:

```
@file:prompt.txt
```

Ví dụ chạy tương tác:

```powershell
python main.py
# → chọn 5
# Enter question: @file:prompt.txt
```

`prompt.txt` sẽ được đọc bằng encoding UTF-8; nội dung file sẽ được dùng làm câu hỏi đầu vào cho RAG.

Lưu ý: `main.py` hiện dùng menu tương tác; nếu bạn muốn gọi không tương tác (CLI flags như `--mode`) cần thêm wrapper hoặc sửa `main.py` để chấp nhận tham số dòng lệnh.

## Ghi chú
- Xem [README.md](README.md) để biết cấu trúc dự án.
- Xem [docs/setup.md](docs/setup.md) cho các hướng dẫn cài đặt nâng cao.
