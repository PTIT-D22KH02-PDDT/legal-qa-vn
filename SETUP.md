# Hướng Dẫn Cài Đặt và Cấu Hình Hệ Thống Legal-QA

Tài liệu này hướng dẫn chi tiết cách cài đặt môi trường, quản lý dependencies, cấu hình hệ thống và vận hành hệ thống Hỏi đáp Pháp lý Việt Nam (Legal-QA).

---

## Yêu Cầu Hệ Thống

*   **Hệ điều hành:** Windows 10/11, Ubuntu 20.04+, hoặc macOS.
*   **Python:** Phiên bản **3.11** trở lên.
*   **Phần cứng khuyến nghị:**
    *   **RAM:** Tối thiểu 4GB (Khuyến nghị 8GB trở lên để chạy các mô hình AI cục bộ).
    *   **Ổ cứng:** Trống tối thiểu 2GB (Dành cho việc lưu trữ cơ sở dữ liệu và tải các mô hình cục bộ).
    *   **GPU (Tùy chọn):** Card đồ họa NVIDIA hỗ trợ CUDA 11.8+ để tăng tốc độ chạy embedding và reranker nội bộ (Nếu không có GPU, hệ thống sẽ tự động chạy trên CPU).

---

## Các Bước Cài Đặt Môi Trường

Dự án hỗ trợ hai phương thức cài đặt: sử dụng công cụ quản lý hiện đại **`uv`** (khuyên dùng vì tốc độ cực nhanh và tính nhất quán cao nhờ tệp `uv.lock`) hoặc sử dụng công cụ **`pip`** truyền thống.

### Cách 1: Sử dụng công cụ `uv` (Khuyến nghị - Siêu tốc)

Nếu bạn chưa cài đặt `uv`, hãy chạy lệnh sau để cài đặt:
*   **Windows (PowerShell):**
    ```powershell
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```
*   **Linux/macOS:**
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

Sau khi cài đặt `uv`, tiến hành tạo môi trường và cài đặt dependencies tự động từ tệp `uv.lock`:
```bash
# 1. Di chuyển vào thư mục dự án
cd d:\PTIT\BTL\NLP

# 2. Tạo môi trường ảo và cài đặt dependencies tự động
uv venv --python 3.11
uv sync
```

Môi trường ảo sẽ được kích hoạt tự động khi bạn sử dụng lệnh `uv run <tên_lệnh>`. Nếu muốn kích hoạt thủ công, hãy chạy:
*   **Windows:** `.venv\Scripts\activate`
*   **Linux/macOS:** `source .venv/bin/activate`

---

### Cách 2: Sử dụng `pip` & `venv` truyền thống

Nếu bạn muốn sử dụng môi trường ảo Python mặc định:

```bash
# 1. Di chuyển vào thư mục dự án
cd d:\PTIT\BTL\NLP

# 2. Tạo môi trường ảo venv
python -m venv venv

# 3. Kích hoạt môi trường ảo
# Windows (PowerShell)
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 4. Nâng cấp pip
python -m pip install --upgrade pip

# 5. Cài đặt gói ở chế độ Editable (Đồng bộ mã nguồn cục bộ)
pip install -e .
```

---

## Tải Các Mô Hình Trí Tuệ Nhân Tạo (Models)

Hệ thống sử dụng hai mô hình học sâu cục bộ (Local Models) để tối ưu chi phí và tăng tốc độ xử lý:

1.  **Vietnamese Embedding (Mô hình nhúng cục bộ):**
    *   **Tên mô hình:** `Vietnamese_Embedding_v2` (định dạng ONNX, kích thước khoảng ~200MB, 256 chiều).
    *   **Thư mục lưu trữ:** Mô hình bắt buộc phải nằm tại thư mục `models/Vietnamese_Embedding_v2/`.
    *   **Cách tải:** Chạy thử hệ thống lần đầu hoặc chạy đoạn mã test dưới đây, hệ thống sẽ tự động tải các tệp tin cấu hình (`model.onnx`, `config.json`, `tokenizer.json`, `special_tokens_map.json`) từ Hugging Face về đúng thư mục.

2.  **Vietnamese Reranker (Mô hình tái xếp hạng cục bộ):**
    *   **Tên mô hình:** `AITeamVN/Vietnamese_Reranker` (Sử dụng Cross-Encoder của thư viện Transformers).
    *   **Cách tải:** Mô hình này sẽ được thư viện `sentence-transformers` tự động tải về thư mục cache hệ thống trong lần chạy đầu tiên.

---

## Cấu Hình Hệ Thống

### 1. Tập tin biến môi trường (`.env`)

Tạo một tệp tin `.env` nằm tại thư mục gốc của dự án và khai báo các thông số sau:

```bash
# Cấu hình địa chỉ API Server (dành cho client/frontend hoặc các script remote)
HOST_NAME="http://localhost:8000"

# API Keys cho các LLM Providers (Điền key thực tế của bạn)
GROQ_API_KEY="gsk_your_groq_api_key_here"
OPENAI_API_KEY="sk-proj-your_openai_api_key_here"
NVIDIA_API_KEY="nvapi-your_nvidia_api_key_here"

# Tùy chọn thiết bị GPU chạy CUDA (Nếu có GPU)
CUDA_VISIBLE_DEVICES="0"
```

### 2. Tập tin cấu hình runtime (`configs/search_config.yaml`)

Tập tin [configs/search_config.yaml](file:///d:/PTIT/BTL/NLP/configs/search_config.yaml) quản lý toàn bộ cấu hình hoạt động của hệ thống. Bạn có thể tối ưu hóa theo các chế độ:

#### Chế độ Nhanh (Phát triển & Phần cứng hạn chế):
```yaml
search:
  remote:
    use_remote_embedding: false
    use_remote_rerank: false
  retrieval:
    top_k_retrieve: 10          # Lấy ra ít ứng viên hơn để tăng tốc
    top_k_rerank: 3             # Chỉ giữ lại 3 kết quả tốt nhất
    distance_metric: "cosine"

rag:
  llm_provider: "groq"
  model_name: "llama3-8b-8192"  # Dùng model nhỏ để phản hồi nhanh
  temperature: 0.1
  max_tokens: 4000

embedding:
  device: "cpu"                 # Ép buộc chạy trên CPU
  batch_size: 8

reranker:
  device: "cpu"
  batch_size: 8
```

#### Chế độ Chính xác Cao (Môi trường Production & Có GPU):
```yaml
search:
  remote:
    use_remote_embedding: true  # Sử dụng API nhúng từ xa
    use_remote_rerank: true     # Sử dụng API tái xếp hạng từ xa
  retrieval:
    top_k_retrieve: 50          # Lấy sâu 50 ứng viên
    top_k_rerank: 10            # Tái xếp hạng lấy 10 bối cảnh tốt nhất
    distance_metric: "cosine"

rag:
  llm_provider: "openai"        # Sử dụng OpenAI GPT-4o
  model_name: "gpt-4o"
  temperature: 0.05             # Đặt temperature cực thấp để chống ảo tưởng
  max_tokens: 8000

embedding:
  device: "cuda"                # Sử dụng GPU CUDA
  batch_size: 64

reranker:
  device: "cuda"
  batch_size: 64
```

---

## Vận Hành Hệ Thống

### Chế độ CLI (Giao diện dòng lệnh Menu tương tác)

```bash
# Kích hoạt môi trường ảo trước khi chạy
# Chạy bằng Python tiêu chuẩn:
python main.py

# Hoặc chạy bằng uv (nếu sử dụng cách 1):
uv run main.py
```

**Các lựa chọn trong Menu CLI:**
1.  **Index Local:** Lập chỉ mục một tài liệu lẻ (.docx) sử dụng mô hình ONNX nhúng cục bộ.
2.  **Index Remote:** Lập chỉ mục tài liệu sử dụng mô hình nhúng thông qua API từ xa.
3.  **Index Folder:** Quét và lập chỉ mục hàng loạt toàn bộ tệp tin Word (.docx) trong thư mục chỉ định.
4.  **Search + Answer (Local):** Đặt câu hỏi hỏi đáp RAG sử dụng tài nguyên cục bộ.
5.  **Search + Answer (Remote):** Đặt câu hỏi hỏi đáp RAG sử dụng API mô hình từ xa.
6.  **Exit:** Thoát chương trình.

---

### Chế độ API Server (Sử dụng FastAPI)

Khởi chạy máy chủ API để phục vụ cho giao diện Frontend hoặc tích hợp hệ thống bên ngoài:

```bash
# Chạy máy chủ mặc định (lắng nghe tại http://localhost:8000)
python api_server.py

# Hoặc khởi chạy thông qua uvicorn với các tham số tối ưu hóa:
uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 4
```

*   **Tài liệu tương tác API:** Truy cập ngay `http://localhost:8000/docs` (Swagger UI) hoặc `http://localhost:8000/redoc` (ReDoc) để thử nghiệm các Endpoint trực quan.

---

## Kiểm Tra & Xác Minh Cài Đặt

Để đảm bảo hệ thống đã được cài đặt và tích hợp hoàn chỉnh tất cả các cấu phần AI, cơ sở dữ liệu, hãy chạy các dòng lệnh kiểm tra nhanh sau:

### 1. Xác minh cài đặt thư viện và Import:
```bash
python -c "import chromadb, sqlalchemy, langchain, langgraph; print('Tất cả thư viện cốt lõi đã được cài đặt thành công!')"
```

### 2. Xác minh hoạt động của Mô hình Nhúng cục bộ:
```bash
python -c "
from src.indexing.embedding.onnx_embedding import LocalONNXEmbedder
from src.search.config import SearchConfig
config = SearchConfig.from_yaml('configs/search_config.yaml')
embedder = LocalONNXEmbedder(config)
vec = embedder.embed_query('Kiểm tra nhúng câu hỏi')
print(f'Mô hình nhúng hoạt động chuẩn xác! Kích thước vector: {len(vec)}')
"
```

### 3. Kiểm tra kết nối và truy xuất cơ sở dữ liệu kép (SQLite & ChromaDB):
```bash
python -c "
from src.search.search import SearchService
from src.search.config import SearchConfig
config = SearchConfig.from_yaml('configs/search_config.yaml')
search = SearchService(config)
results = search.search('Hợp đồng lao động', top_k=2)
print(f'Kết nối cơ sở dữ liệu kép thành công! Tìm thấy {len(results)} kết quả phù hợp.')
for r in results:
    print(f'  - Chunk ID: {r.chunk_id} | Score: {r.score:.4f}')
"
```

---

## Xử Lý Sự Cố Thường Gặp (Troubleshooting)

### 1. Lỗi "ModuleNotFoundError"
*   **Nguyên nhân:** Chưa kích hoạt môi trường ảo hoặc chưa cài đặt dự án ở chế độ Editable.
*   **Khắc phục:** Chạy lệnh `pip install -e .` tại thư mục gốc của dự án hoặc đảm bảo đã gọi đúng môi trường ảo (`.venv\Scripts\activate` trên Windows).

### 2. Lỗi "CUDA out of memory" (Tràn bộ nhớ GPU)
*   **Nguyên nhân:** Card đồ họa GPU có bộ nhớ VRAM thấp nhưng cấu hình batch size lớn trong `search_config.yaml`.
*   **Khắc phục:** Giảm `batch_size: 8` tại mục `embedding` và `reranker`, hoặc ép buộc hệ thống chạy trên CPU bằng cách đặt `device: "cpu"`.

### 3. Lỗi "API key invalid hoặc Quota exceeded"
*   **Nguyên nhân:** Biến môi trường chưa nhận diện được API Key từ tệp `.env` hoặc Key bị hết hạn/hết hạn ngạch.
*   **Khắc phục:** Kiểm tra lại tệp `.env`. Đảm bảo không có khoảng trắng thừa xung quanh API Key. Bạn có thể xác minh trực tiếp key bằng Python:
    ```python
    import os
    print(os.getenv("GROQ_API_KEY"))
    ```

### 4. Lỗi "ChromaDB connection error" hoặc dữ liệu bị hỏng
*   **Nguyên nhân:** Tiến trình ghi dữ liệu bị ngắt đột ngột làm hỏng tệp tin sqlite của ChromaDB.
*   **Khắc phục:** Xóa thư mục lưu trữ `chroma_db/` và chạy lập chỉ mục lại toàn bộ thư mục tài liệu thô:
    ```bash
    # Trên Windows
    Remove-Item -Recurse -Force chroma_db
    # Chạy CLI lập chỉ mục lại (Chọn Option 3 trong main.py)
    python main.py
    ```

---

*Nếu gặp bất kỳ khó khăn nào khác trong quá trình cài đặt, vui lòng kiểm tra tệp tin nhật ký tại thư mục `logs/` hoặc tạo Issue để được hỗ trợ.*
